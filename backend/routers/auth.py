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

import os
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from database import get_db
import models, auth
import email_utils
from schemas import StrictModel
from pydantic import EmailStr
from routers.deps import get_restaurant_or_none
from rate_limit import limiter
from time_utils import utcnow

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Security hardening pass (2026-07-07): login had zero brute-force protection
# — no rate limiting was ever actually applied anywhere (slowapi was
# configured but no route used it), and no failed-attempt tracking existed
# at all. Both fixed together: rate limiting is the first line of defense
# (per-IP), lockout is the second (per-account, survives IP rotation).
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# Password reset / email verification (security pass 2026-07-17: neither
# existed at all — see audit). Tokens are single-use and short-lived; see
# models.AuthToken.
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "30"))
EMAIL_VERIFY_TOKEN_EXPIRE_HOURS = int(os.getenv("EMAIL_VERIFY_TOKEN_EXPIRE_HOURS", "48"))
# Base URL of the deployed frontend, used to build the links emailed to users.
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")


def _issue_auth_token(
    db: Session, user: "models.User", purpose: "models.AuthTokenPurpose", expires_delta: timedelta
) -> str:
    """Mint a single-use token, persist only its hash, return the raw value
    (which the caller emails — it is never stored or logged in full)."""
    raw = auth.generate_auth_token()
    db.add(models.AuthToken(
        user_id=user.id,
        token_hash=auth.hash_auth_token(raw),
        purpose=purpose,
        expires_at=utcnow() + expires_delta,
    ))
    db.commit()
    return raw


def _consume_auth_token(
    db: Session, raw_token: str, purpose: "models.AuthTokenPurpose"
) -> "models.User":
    """Validate a reset/verify token (right purpose, unused, unexpired) and
    mark it used. Raises 400 with a deliberately generic message on any
    failure — an attacker probing tokens shouldn't learn whether a token
    exists, was already used, or expired."""
    invalid = HTTPException(status_code=400, detail="This link is invalid or has expired.")
    token_hash = auth.hash_auth_token(raw_token)
    record = db.query(models.AuthToken).filter(
        models.AuthToken.token_hash == token_hash,
        models.AuthToken.purpose == purpose,
    ).first()
    if not record or record.used_at is not None or record.expires_at < utcnow():
        raise invalid
    user = db.query(models.User).filter(models.User.id == record.user_id).first()
    if not user:
        raise invalid
    record.used_at = utcnow()
    db.commit()
    return user


# ── Request / Response schemas ────────────────────────────────────────────────

class UserCreate(StrictModel):
    email: EmailStr
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


class PinSetBody(StrictModel):
    pin: str


class QuickSwitchBody(StrictModel):
    user_id: int
    pin: str


class QuickSwitchRosterEntry(StrictModel):
    user_id: int
    name: str
    role_title: str | None = None
    staff_role: str | None = None


class RestaurantUpdate(StrictModel):
    name: str | None = None
    address: str | None = None
    currency: str | None = None
    timezone: str | None = None
    owner_phone: str | None = None   # E.164, e.g. +2547...; used for WhatsApp owner routing
    # GPS staff check-in (migration 037) — set once so routers/attendance.py
    # has something to compare a clock-in's coordinates against. Optional:
    # leaving these unset simply means the proximity check never runs.
    latitude: float | None = None
    longitude: float | None = None


class PasswordResetRequest(StrictModel):
    email: str


class PasswordResetConfirm(StrictModel):
    token: str
    new_password: str


class ImpersonationBanner(StrictModel):
    session_id: int
    impersonator_email: str


class MeOut(StrictModel):
    id: int
    email: str
    role: str
    staff_role: str | None = None
    is_email_verified: bool
    restaurant_name: str | None = None
    restaurant_id: int | None = None
    impersonation: ImpersonationBanner | None = None


class StatusMessageOut(StrictModel):
    """Generic {"status": "..."} acknowledgement — logout-all, password-reset,
    verify-email, resend-verification, mfa enable/disable."""
    status: str
    token_version: int | None = None


class MfaSetupOut(StrictModel):
    secret: str
    otpauth_uri: str


class RestaurantOut(StrictModel):
    id: int
    name: str
    address: str | None = None
    owner_phone: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class EmailVerifyConfirm(StrictModel):
    token: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=Token, status_code=201)
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
        # A fresh signup is always the Owner of their own restaurant —
        # matches the migration 025 backfill for pre-existing ADMIN users
        # (directive 015: Owner maps 1:1 onto Role.ADMIN).
        staff_role=models.StaffRole.OWNER,
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

    # 5. Email verification link — best-effort; a mail-server hiccup must
    #    never fail the signup itself (see email_utils.send_email).
    verify_token = _issue_auth_token(
        db, new_user, models.AuthTokenPurpose.EMAIL_VERIFY,
        timedelta(hours=EMAIL_VERIFY_TOKEN_EXPIRE_HOURS),
    )
    email_utils.send_email(
        new_user.email,
        "Verify your email",
        f"Welcome to Chakula! Verify your email address here:\n"
        f"{FRONTEND_BASE_URL}/verify-email?token={verify_token}\n\n"
        f"This link expires in {EMAIL_VERIFY_TOKEN_EXPIRE_HOURS} hours.",
    )

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
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked due to repeated failed logins. Try again in {remaining} minute(s).",
        )

    if not user or not auth.verify_password(login_data.password, user.hashed_password):
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            just_locked = user.failed_login_attempts >= MAX_FAILED_ATTEMPTS
            if just_locked:
                user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            db.commit()
            # Fires exactly once, at the moment of transition into lockout —
            # the early-return above (line ~213) short-circuits every
            # subsequent attempt while already locked, so this can't re-fire
            # per retry. A possible brute-force attempt is a risk signal the
            # Owner should see in real time, not just in the audit trail.
            if just_locked:
                restaurant = get_restaurant_or_none(db, user)
                if restaurant:
                    from events.bus import emit_async, EventType
                    emit_async(EventType.ACCOUNT_LOCKED, {
                        "restaurant_id": restaurant.id,
                        "email": user.email,
                        "lockout_minutes": LOCKOUT_MINUTES,
                    })
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
    db.commit()

    access_token = auth.create_access_token(
        data={"sub": user.email, "ver": user.token_version or 0}
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=MeOut)
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
        # directive 015 — read straight from the DB on every /me call rather
        # than embedding it as a JWT claim, so a role change (or the
        # "unassigned" state) is reflected on the user's very next request
        # instead of only after their token expires/refreshes.
        "staff_role": current_user.staff_role,
        "is_email_verified": current_user.is_email_verified,
        "restaurant_name": restaurant.name if restaurant else None,
        "restaurant_id": restaurant.id if restaurant else None,
        # Real Owner impersonation (see routers/staff.py /impersonate):
        # non-null only when this request is running as the target of an
        # active session. Lets the frontend show the "Viewing as..." banner
        # without ever decoding the JWT itself.
        "impersonation": (
            {
                "session_id": current_user.impersonated_by["session_id"],
                "impersonator_email": current_user.impersonated_by["impersonator_email"],
            }
            if getattr(current_user, "impersonated_by", None) else None
        ),
    }


@router.post("/logout-all", response_model=StatusMessageOut)
async def logout_all(
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
    db.commit()
    return {"status": "all_sessions_revoked", "token_version": user.token_version}


@router.post("/password-reset/request", response_model=StatusMessageOut)
@limiter.limit("3/hour")
async def request_password_reset(
    request: Request, body: PasswordResetRequest, db: Session = Depends(get_db)
):
    """
    Always returns the same generic response whether or not the email is
    registered — an attacker probing this endpoint must not be able to tell
    a real account from a non-existent one (account-enumeration prevention).
    """
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if user and user.is_active:
        raw = _issue_auth_token(
            db, user, models.AuthTokenPurpose.PASSWORD_RESET,
            timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
        email_utils.send_email(
            user.email,
            "Reset your password",
            f"Reset your password here:\n{FRONTEND_BASE_URL}/reset-password?token={raw}\n\n"
            f"This link expires in {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes and can "
            f"only be used once. If you didn't request this, you can ignore this email.",
        )
    return {"status": "if_account_exists_a_reset_email_was_sent"}


@router.post("/password-reset/confirm", response_model=StatusMessageOut)
@limiter.limit("10/hour")
async def confirm_password_reset(
    request: Request, body: PasswordResetConfirm, db: Session = Depends(get_db)
):
    auth.require_strong_password(body.new_password)
    user = _consume_auth_token(db, body.token, models.AuthTokenPurpose.PASSWORD_RESET)

    user.hashed_password = auth.get_password_hash(body.new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    # A password reset must invalidate every outstanding session — otherwise
    # a session opened with the OLD (possibly compromised) password survives
    # the very reset meant to kill it off.
    user.token_version = (user.token_version or 0) + 1
    db.commit()

    email_utils.send_email(
        user.email,
        "Your password was changed",
        "Your password was just changed. If this wasn't you, contact support immediately.",
    )
    return {"status": "password_reset"}


@router.post("/verify-email", response_model=StatusMessageOut)
@limiter.limit("10/hour")
async def verify_email(
    request: Request, body: EmailVerifyConfirm, db: Session = Depends(get_db)
):
    user = _consume_auth_token(db, body.token, models.AuthTokenPurpose.EMAIL_VERIFY)
    user.is_email_verified = True
    db.commit()
    return {"status": "email_verified"}


@router.post("/resend-verification", response_model=StatusMessageOut)
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if user.is_email_verified:
        raise HTTPException(status_code=400, detail="Email is already verified.")
    raw = _issue_auth_token(
        db, user, models.AuthTokenPurpose.EMAIL_VERIFY,
        timedelta(hours=EMAIL_VERIFY_TOKEN_EXPIRE_HOURS),
    )
    email_utils.send_email(
        user.email,
        "Verify your email",
        f"Verify your email address here:\n{FRONTEND_BASE_URL}/verify-email?token={raw}\n\n"
        f"This link expires in {EMAIL_VERIFY_TOKEN_EXPIRE_HOURS} hours.",
    )
    return {"status": "verification_email_sent"}


@router.post("/mfa/setup", response_model=MfaSetupOut)
async def mfa_setup(
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
    db.commit()
    return {
        "secret": user.mfa_secret,
        "otpauth_uri": auth.mfa_provisioning_uri(user.email, user.mfa_secret),
    }


@router.post("/mfa/enable", response_model=StatusMessageOut)
async def mfa_enable(
    body: MfaCode,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Activate MFA after verifying the first code against the pending secret."""
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user.mfa_secret:
        raise HTTPException(status_code=400, detail="Call /mfa/setup first.")
    if not auth.verify_totp(user.mfa_secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid code — try again.")
    user.mfa_enabled = True
    db.commit()
    return {"status": "mfa_enabled"}


@router.post("/mfa/disable", response_model=StatusMessageOut)
async def mfa_disable(
    body: MfaCode,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Turn MFA off — requires a current valid code, so a stolen session alone
    can't strip the second factor."""
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled.")
    if not auth.verify_totp(user.mfa_secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid code.")
    user.mfa_enabled = False
    user.mfa_secret = None
    db.commit()
    return {"status": "mfa_disabled"}


# ── Shared-device quick-switch (audit remediation, Tier 5 item 12) ──────────
# No PIN/badge login existed at all — every staff account needed a full
# email+password re-auth, friction on a POS/KDS tablet passed between waiters
# mid-shift. This is opt-in (a user sets their own PIN), teammate-visible only
# to people already authenticated at the same tenant, and reuses the exact
# lockout mechanism /login already has (MAX_FAILED_ATTEMPTS/LOCKOUT_MINUTES)
# rather than inventing a second one — a 4-6 digit PIN needs that protection
# more than a real password does, not less.

@router.post("/pin/set", response_model=StatusMessageOut)
async def pin_set(
    body: PinSetBody,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Self-service opt-in: set or change your own quick-switch PIN. Requires
    only being logged in already — same trust level as changing your own MFA
    enrollment, no separate re-auth demanded."""
    auth.require_valid_pin_format(body.pin)
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    user.hashed_pin = auth.get_pin_hash(body.pin)
    db.commit()
    return {"status": "pin_set"}


@router.post("/pin/clear", response_model=StatusMessageOut)
async def pin_clear(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Opt back out — removes you from every teammate's quick-switch roster."""
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    user.hashed_pin = None
    db.commit()
    return {"status": "pin_cleared"}


@router.get("/quick-switch/roster", response_model=list[QuickSwitchRosterEntry])
async def quick_switch_roster(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Teammates at the same tenant who've opted into a PIN — the picker list
    for a shared device. Excludes the caller (switching to yourself is a
    no-op) and anyone without a PIN set (they still need a full login)."""
    rows = (
        db.query(models.StaffMember, models.User)
        .join(models.User, models.StaffMember.user_id == models.User.id)
        .filter(
            models.User.tenant_id == current_user.tenant_id,
            models.User.hashed_pin.isnot(None),
            models.User.is_active == True,  # noqa: E712 - SQLAlchemy filter
            models.User.id != current_user.id,
        )
        .all()
    )
    return [
        {
            "user_id": u.id,
            "name": m.name,
            "role_title": m.role_title,
            "staff_role": u.staff_role.value if u.staff_role else None,
        }
        for m, u in rows
    ]


@router.post("/quick-switch", response_model=Token)
@limiter.limit("10/minute")
async def quick_switch(
    request: Request,
    body: QuickSwitchBody,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Swap the device's session to `user_id` after verifying their PIN — no
    password re-entry. Being authenticated as ANYONE at the tenant is what
    establishes trust that this is a legitimate shared device, not an
    open door: the target must belong to the same tenant as the caller, have
    already opted in with a PIN, and pass the same lockout gate /login uses.
    """
    target = db.query(models.User).filter(
        models.User.id == body.user_id,
        models.User.tenant_id == current_user.tenant_id,
    ).first()
    if not target or not target.hashed_pin or not target.is_active:
        raise HTTPException(status_code=404, detail="Not available for quick switch.")

    if target.locked_until and target.locked_until > utcnow():
        remaining = int((target.locked_until - utcnow()).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account temporarily locked due to repeated failed PIN attempts. Try again in {remaining} minute(s).",
        )

    if not auth.verify_pin(body.pin, target.hashed_pin):
        target.failed_login_attempts = (target.failed_login_attempts or 0) + 1
        just_locked = target.failed_login_attempts >= MAX_FAILED_ATTEMPTS
        if just_locked:
            target.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect PIN")

    target.failed_login_attempts = 0
    target.locked_until = None
    target.last_login_at = utcnow()
    db.commit()

    access_token = auth.create_access_token(data={"sub": target.email, "ver": target.token_version or 0})
    return {"access_token": access_token, "token_type": "bearer"}


@router.put("/restaurant", response_model=RestaurantOut)
async def update_restaurant(
    data: RestaurantUpdate,
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
        restaurant.owner_phone = normalize_phone(data.owner_phone)
    if data.latitude is not None:
        restaurant.latitude = data.latitude
    if data.longitude is not None:
        restaurant.longitude = data.longitude
    db.commit()
    db.refresh(restaurant)
    return {
        "id": restaurant.id,
        "name": restaurant.name,
        "address": restaurant.address,
        "owner_phone": restaurant.owner_phone,
        "latitude": restaurant.latitude,
        "longitude": restaurant.longitude,
    }
