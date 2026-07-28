"""
backend/routers/auth.py
────────────────────────
Authentication router.

FIXES:
  - register() now auto-creates a Restaurant + 4 default Tables so that
    every AI endpoint finds a restaurant on first login. Without this,
    _get_restaurant() returned 404 and the frontend fell back to Lavy demo data.
  - Added /me endpoint returns restaurant_name so the frontend can
    personalise without an extra round-trip.
  - Added /restaurant PUT so the owner can update their name/address
    from the onboarding wizard.
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from database import get_db
import models, auth
from schemas import StrictModel
from routers.deps import get_restaurant_or_none
from rate_limit import limiter
from time_utils import utcnow
from audit import record_security_event, hash_identifier, SUCCESS, FAILURE

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Security hardening pass (2026-07-07): login had zero brute-force protection
# — no rate limiting was ever actually applied anywhere (slowapi was
# configured but no route used it), and no failed-attempt tracking existed
# at all. Both fixed together: rate limiting is the first line of defense
# (per-IP), lockout is the second (per-account, survives IP rotation).
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


# ── Request / Response schemas ────────────────────────────────────────────────

class UserCreate(StrictModel):
    email: str
    password: str
    tenant_name: str   # used as restaurant name on signup


class Token(StrictModel):
    access_token: str
    token_type: str


class LoginRequest(StrictModel):
    email: str
    password: str
    mfa_code: str | None = None   # required only when the account has MFA enabled


class MfaCode(StrictModel):
    code: str


class RestaurantUpdate(StrictModel):
    name: str | None = None
    address: str | None = None
    currency: str | None = None
    timezone: str | None = None
    owner_phone: str | None = None   # E.164, e.g. +2547...; used for WhatsApp owner routing


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=Token)
@limiter.limit("5/hour")
async def register(request: Request, user_data: UserCreate, db: Session = Depends(get_db)):
    # Enforce minimum password strength before anything else.
    auth.require_strong_password(user_data.password)

    # Guard: duplicate email
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # 1. Tenant
    tenant = models.Tenant(name=user_data.tenant_name)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # 2. User
    hashed_password = auth.get_password_hash(user_data.password)
    new_user = models.User(
        email=user_data.email,
        hashed_password=hashed_password,
        role=models.Role.ADMIN,
        tenant_id=tenant.id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. Restaurant — THE MISSING PIECE.
    #    Without this every /ai/* endpoint returns 404 and the frontend
    #    falls back to the hardcoded "Lavy" demo data.
    restaurant = models.Restaurant(
        name=user_data.tenant_name,
        address="",
        tenant_id=tenant.id,
    )
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)

    # 4. Seed 5 tables so the POS and reservations work immediately.
    for i in range(1, 6):
        db.add(models.Table(
            restaurant_id=restaurant.id,
            table_number=i,
            capacity=4,
            status=models.TableStatus.AVAILABLE,
        ))
    db.commit()

    record_security_event(
        db, request, "auth.register", SUCCESS,
        actor=new_user, restaurant_id=restaurant.id,
        target_type="user", target_ref=str(new_user.id),
        role=new_user.role.value if new_user.role else None,
    )
    db.commit()

    access_token = auth.create_access_token(
        data={"sub": new_user.email, "ver": new_user.token_version or 0}
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, login_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == login_data.email).first()

    # Lockout check FIRST, before touching the password at all — rejects
    # locked accounts without a password-verification timing signal.
    if user and user.locked_until and user.locked_until > utcnow():
        remaining = int((user.locked_until - utcnow()).total_seconds() / 60) + 1
        # Recorded on every rejected attempt, not just the one that tripped the
        # lock: repeated hits against an already-locked account is what a
        # credential-stuffing run looks like from the outside.
        record_security_event(
            db, request, "auth.login.locked_out", FAILURE,
            actor=user, minutes_remaining=remaining, commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked due to repeated failed logins. Try again in {remaining} minute(s).",
        )

    if not user or not auth.verify_password(login_data.password, user.hashed_password):
        locked_now = False
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
                locked_now = True
        # actor is None when the email has no account — the audit row still
        # records the attempt and the source IP, which is the whole point:
        # enumeration of non-existent addresses is a signal, and it is exactly
        # the case AgentAuditLog's non-null columns could not represent.
        record_security_event(
            db, request, "auth.login.failed", FAILURE,
            actor=user,
            actor_email=login_data.email if user is None else None,
            attempt=(user.failed_login_attempts if user else None),
            account_exists=user is not None,
        )
        if locked_now:
            record_security_event(
                db, request, "auth.login.account_locked", FAILURE,
                actor=user, lockout_minutes=LOCKOUT_MINUTES,
            )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Second factor: only when the account has enrolled+enabled MFA. Checked
    # AFTER the password so a missing/invalid code on a correct password doesn't
    # count toward brute-force lockout differently — but a wrong code still fails
    # the login. The client resubmits email+password+mfa_code together.
    if user.mfa_enabled:
        if not login_data.mfa_code or not auth.verify_totp(user.mfa_secret, login_data.mfa_code):
            # Password correct, second factor not — the signature of a stolen
            # or phished password meeting a factor the attacker doesn't have.
            record_security_event(
                db, request, "auth.login.mfa_failed", FAILURE,
                actor=user, code_supplied=bool(login_data.mfa_code), commit=True,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A valid authenticator code is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Successful login — reset the counter and record the login timestamp
    # (staff-activity record referenced in the DPA).
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    record_security_event(
        db, request, "auth.login.success", SUCCESS,
        actor=user, mfa_used=bool(user.mfa_enabled),
    )
    db.commit()

    access_token = auth.create_access_token(
        data={"sub": user.email, "ver": user.token_version or 0}
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Returns user info + restaurant name for personalisation."""
    restaurant = get_restaurant_or_none(db, current_user)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "restaurant_name": restaurant.name if restaurant else None,
        "restaurant_id": restaurant.id if restaurant else None,
    }


@router.post("/logout-all")
async def logout_all(
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Revoke every outstanding session for the current user by bumping
    token_version — all JWTs minted before this call (including the one used to
    make it) immediately stop validating. Use after a suspected token leak or a
    password change. Stateless-JWT logout is otherwise client-side only.
    """
    # Re-fetch in THIS session and update it there, rather than mutating the
    # current_user instance (attached to get_current_user's session) and
    # committing a different session — that only persists while the two sessions
    # happen to be the same object, an implicit coupling we don't want to rely on.
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    user.token_version = (user.token_version or 0) + 1
    record_security_event(
        db, request, "auth.sessions.revoked", SUCCESS,
        actor=user, target_type="user", target_ref=str(user.id),
        new_token_version=user.token_version,
    )
    db.commit()
    return {"status": "all_sessions_revoked", "token_version": user.token_version}


@router.post("/mfa/setup")
async def mfa_setup(
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Begin TOTP enrollment: generate a secret and return the otpauth:// URI for the
    user to scan into an authenticator app. MFA is NOT active yet — the user must
    prove they can generate a valid code via /mfa/enable. Re-calling before enable
    rotates the pending secret.
    """
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is already enabled.")
    user.mfa_secret = auth.generate_mfa_secret()
    record_security_event(
        db, request, "auth.mfa.secret_issued", SUCCESS,
        actor=user, target_type="user", target_ref=str(user.id),
    )
    db.commit()
    return {
        "secret": user.mfa_secret,
        "otpauth_uri": auth.mfa_provisioning_uri(user.email, user.mfa_secret),
    }


@router.post("/mfa/enable")
async def mfa_enable(
    body: MfaCode,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Activate MFA after verifying the first code against the pending secret."""
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user.mfa_secret:
        raise HTTPException(status_code=400, detail="Call /mfa/setup first.")
    if not auth.verify_totp(user.mfa_secret, body.code):
        record_security_event(
            db, request, "auth.mfa.enable_failed", FAILURE,
            actor=user, commit=True,
        )
        raise HTTPException(status_code=400, detail="Invalid code — try again.")
    user.mfa_enabled = True
    record_security_event(
        db, request, "auth.mfa.enabled", SUCCESS,
        actor=user, target_type="user", target_ref=str(user.id),
    )
    db.commit()
    return {"status": "mfa_enabled"}


@router.post("/mfa/disable")
async def mfa_disable(
    body: MfaCode,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Turn MFA off — requires a current valid code, so a stolen session alone
    can't strip the second factor."""
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled.")
    if not auth.verify_totp(user.mfa_secret, body.code):
        record_security_event(
            db, request, "auth.mfa.disable_failed", FAILURE,
            actor=user, commit=True,
        )
        raise HTTPException(status_code=400, detail="Invalid code.")
    user.mfa_enabled = False
    user.mfa_secret = None
    # The action an attacker holding a stolen session most wants, and until now
    # the one that left no trace whatsoever.
    record_security_event(
        db, request, "auth.mfa.disabled", SUCCESS,
        actor=user, target_type="user", target_ref=str(user.id),
    )
    db.commit()
    return {"status": "mfa_disabled"}


@router.put("/restaurant")
async def update_restaurant(
    data: RestaurantUpdate,
    request: Request,
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Onboarding wizard uses this to save restaurant profile. Admin-only."""
    restaurant = get_restaurant_or_none(db, current_user)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    if data.name is not None:
        restaurant.name = data.name
    if data.address is not None:
        restaurant.address = data.address
    if data.owner_phone is not None:
        # Normalize on write so it matches the normalized inbound WhatsApp number
        # at compare time (see routers/webhooks.py / phone_utils.py). Storing the
        # raw form silently broke owner-command matching for any non-E.164 entry.
        from phone_utils import normalize_phone
        previous_phone = restaurant.owner_phone
        restaurant.owner_phone = normalize_phone(data.owner_phone)
        # owner_phone is the number that receives WhatsApp briefings and is
        # matched for owner commands — repointing it redirects the owner channel.
        # Hashed both sides: the audit trail records THAT it changed and lets you
        # match a candidate number, without storing the numbers themselves.
        record_security_event(
            db, request, "restaurant.owner_phone.changed", SUCCESS,
            actor=current_user, restaurant_id=restaurant.id,
            target_type="restaurant", target_ref=str(restaurant.id),
            previous_ref=hash_identifier(previous_phone),
            new_ref=hash_identifier(restaurant.owner_phone),
        )
    db.commit()
    db.refresh(restaurant)
    return {
        "id": restaurant.id,
        "name": restaurant.name,
        "address": restaurant.address,
        "owner_phone": restaurant.owner_phone,
    }
