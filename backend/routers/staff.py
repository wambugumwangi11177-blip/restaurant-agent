"""
backend/routers/staff.py
──────────────────────────
Staff roster + role assignment (directive 015).

Manager-vs-Owner boundary on who can grant which tier: an Owner can assign
any of the 7 tiers; a Manager can only assign tiers below Manager (Supervisor
downward) — a Manager cannot mint another Manager or an Owner. This isn't
spelled out as a literal rule in directive 015's matrix, but follows directly
from its stated principle ("no default that silently grants more access than
intended") extended to grantor privilege — otherwise a Manager could
self-escalate peers indefinitely. Documented here so it isn't re-litigated
per call site.
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from ai.evaluation.tracker import write_audit_log
from phone_utils import normalize_phone
from time_utils import utcnow

router = APIRouter(prefix="/staff", tags=["staff"])

# Tiers a Manager (not Owner) is allowed to grant. Manager and Owner
# themselves are excluded — see module docstring.
_MANAGER_GRANTABLE = {
    models.StaffRole.SUPERVISOR,
    models.StaffRole.CONTROLLER,
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.KITCHEN,
    models.StaffRole.WAITER,
}


def _staff_out(member: models.StaffMember, db: Session) -> dict:
    linked_role = None
    if member.user_id:
        linked_user = db.query(models.User).filter(models.User.id == member.user_id).first()
        if linked_user and linked_user.staff_role:
            linked_role = linked_user.staff_role.value
    return {
        "id": member.id,
        "restaurant_id": member.restaurant_id,
        "user_id": member.user_id,
        "name": member.name,
        "role_title": member.role_title,
        "hourly_rate": member.hourly_rate,
        "phone": member.phone,
        "is_active": member.is_active,
        "staff_role": linked_role,
    }


def _parse_staff_role(value: str) -> models.StaffRole:
    try:
        return models.StaffRole[value.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown staff role: {value}")


def _require_grant_allowed(granter: models.User, target_role: models.StaffRole) -> None:
    """Owner (Role.ADMIN) may grant any tier. A Manager-tier user may only
    grant tiers in _MANAGER_GRANTABLE. Anyone else shouldn't reach this
    function at all (the route dependency already blocks them)."""
    if granter.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return
    if target_role not in _MANAGER_GRANTABLE:
        raise HTTPException(
            status_code=403,
            detail="Only an Owner can grant the Owner or Manager tier.",
        )


@router.get("/", response_model=List[schemas.StaffMemberOut])
async def list_staff(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_staff_role(models.StaffRole.MANAGER)
    ),
):
    restaurant = get_or_create_restaurant(db, current_user)
    members = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant.id
    ).order_by(models.StaffMember.name).offset(offset).limit(limit).all()
    return [_staff_out(m, db) for m in members]


@router.post("/", response_model=schemas.StaffMemberOut, status_code=201)
async def create_staff(
    body: schemas.StaffMemberCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_staff_role(models.StaffRole.MANAGER)
    ),
):
    restaurant = get_or_create_restaurant(db, current_user)

    linked_user = None
    if body.create_login:
        if not body.email or not body.password or not body.staff_role:
            raise HTTPException(
                status_code=400,
                detail="email, password, and staff_role are all required when create_login is true.",
            )
        auth.require_strong_password(body.password)
        target_role = _parse_staff_role(body.staff_role)
        _require_grant_allowed(current_user, target_role)

        if db.query(models.User).filter(models.User.email == body.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")

        linked_user = models.User(
            email=body.email,
            hashed_password=auth.get_password_hash(body.password),
            role=models.Role.STAFF,
            staff_role=target_role,
            tenant_id=current_user.tenant_id,
        )
        db.add(linked_user)
        db.commit()
        db.refresh(linked_user)

    member = models.StaffMember(
        restaurant_id=restaurant.id,
        user_id=linked_user.id if linked_user else None,
        name=body.name,
        role_title=body.role_title,
        hourly_rate=body.hourly_rate,
        # Normalized on write so it matches the normalized inbound WhatsApp/SMS
        # number at compare time (same reasoning as RestaurantUpdate.owner_phone
        # in routers/auth.py — storing the raw form would silently break
        # webhooks._resolve_staff_by_phone).
        phone=normalize_phone(body.phone) if body.phone else None,
    )
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        # uq_staff_members_restaurant_phone (migration 030).
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A staff member with this phone number already exists at this restaurant.",
        )
    db.refresh(member)

    if linked_user:
        # Real-time visibility alongside the audit-log write below — reuses
        # STAFF_ROLE_CHANGED rather than a new event type: a brand-new login
        # is, from a "who has access" standpoint, the same signal as a role
        # change (before_role=None makes the notification read as "granted",
        # not "changed"). Excludes the actor.
        from events.bus import emit_async, EventType
        emit_async(EventType.STAFF_ROLE_CHANGED, {
            "restaurant_id": restaurant.id,
            "staff_name": member.name,
            "before_role": None,
            "after_role": target_role.value,
            "changed_by": current_user.email,
            "changed_by_user_id": current_user.id,
        })
        write_audit_log(
            db, restaurant.id, "staff_role_assigned", "staff_router",
            entity_type="user", entity_id=linked_user.id,
            after={"staff_role": linked_user.staff_role.value, "staff_member_id": member.id},
            reasoning=f"Staff member '{member.name}' created with login and role {linked_user.staff_role.value}.",
            approved_by=current_user.email,
        )

    return _staff_out(member, db)


@router.put("/{staff_id}", response_model=schemas.StaffMemberOut)
async def update_staff(
    staff_id: int,
    body: schemas.StaffMemberUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_staff_role(models.StaffRole.MANAGER)
    ),
):
    restaurant = get_or_create_restaurant(db, current_user)
    member = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.restaurant_id == restaurant.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")

    # Privilege guard (security audit 2026-08-23): create/assign-role carefully
    # bound what a Manager may grant via _require_grant_allowed, but this
    # generic update path let a Manager-tier caller deactivate a peer Manager
    # (force-logging them out) or edit their pay rate — the same powers the
    # grant rules exist to withhold.
    updates = body.dict(exclude_unset=True)
    caller_is_admin = current_user.role in (models.Role.ADMIN, models.Role.SUPERADMIN)
    if not caller_is_admin:
        target_tier = None
        if member.user_id:
            linked = db.query(models.User).filter(models.User.id == member.user_id).first()
            target_tier = linked.staff_role if linked else None
        if target_tier in (models.StaffRole.MANAGER, models.StaffRole.OWNER):
            raise HTTPException(
                status_code=403,
                detail="Only an Owner can modify Manager-tier staff.",
            )
        # Segregation of duties on payroll data: nobody edits their own pay
        # rate, and deactivating yourself is what logout is for (a self-off
        # here would also skip the revocation audit/event path below).
        if member.user_id == current_user.id:
            if "hourly_rate" in updates:
                raise HTTPException(
                    status_code=403,
                    detail="You cannot edit your own pay rate.",
                )
            if updates.get("is_active") is False:
                raise HTTPException(
                    status_code=403,
                    detail="You cannot deactivate your own account.",
                )
    was_active = member.is_active
    if "phone" in updates and updates["phone"]:
        updates["phone"] = normalize_phone(updates["phone"])
    for key, value in updates.items():
        setattr(member, key, value)

    # Deactivation must revoke an existing login immediately (directive 016 —
    # this was a real gap: StaffMember.is_active previously had no downstream
    # effect on the linked User's ability to log in or keep an existing
    # session). Reuses the same token_version bump as /auth/logout-all.
    if was_active and member.is_active is False and member.user_id:
        linked_user = db.query(models.User).filter(models.User.id == member.user_id).first()
        if linked_user:
            linked_user.is_active = False
            linked_user.token_version = (linked_user.token_version or 0) + 1
            write_audit_log(
                db, restaurant.id, "staff_deactivated", "staff_router",
                entity_type="user", entity_id=linked_user.id,
                reasoning=f"Staff member '{member.name}' deactivated — login revoked immediately.",
                approved_by=current_user.email,
            )
            # Real-time companion to the audit log, same reasoning as
            # STAFF_ROLE_CHANGED — directive 016's own risk table names this
            # exact scenario ("ex-staff retaining access") as a risk to catch,
            # so the person revoking access should have that action confirmed
            # back to an owner, not just written to a log nobody's watching.
            from events.bus import emit_async, EventType
            emit_async(EventType.STAFF_DEACTIVATED, {
                "restaurant_id": restaurant.id,
                "staff_name": member.name,
                "deactivated_by": current_user.email,
                "deactivated_by_user_id": current_user.id,
            })
    elif not was_active and member.is_active and member.user_id:
        linked_user = db.query(models.User).filter(models.User.id == member.user_id).first()
        if linked_user:
            linked_user.is_active = True
            write_audit_log(
                db, restaurant.id, "staff_reactivated", "staff_router",
                entity_type="user", entity_id=linked_user.id,
                reasoning=f"Staff member '{member.name}' reactivated — login restored.",
                approved_by=current_user.email,
            )
            # Symmetric companion to STAFF_DEACTIVATED — restoring access is a
            # "who has access" change worth surfacing to an owner in real time,
            # not just on a later audit review. Excludes the actor.
            from events.bus import emit_async, EventType
            emit_async(EventType.STAFF_REACTIVATED, {
                "restaurant_id": restaurant.id,
                "staff_name": member.name,
                "reactivated_by": current_user.email,
                "reactivated_by_user_id": current_user.id,
            })

    try:
        db.commit()
    except IntegrityError:
        # uq_staff_members_restaurant_phone (migration 030).
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A staff member with this phone number already exists at this restaurant.",
        )
    db.refresh(member)
    return _staff_out(member, db)


@router.post("/{staff_id}/assign-role", response_model=schemas.StaffMemberOut)
async def assign_role(
    staff_id: int,
    body: schemas.StaffRoleAssign,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_staff_role(models.StaffRole.MANAGER)
    ),
):
    """Explicit role (re)assignment, separate from create — covers both the
    initial grant for a StaffMember created without create_login, and later
    promotions/demotions. Every change is audit-logged (directive 015's Edge
    Cases: role changes must be traceable — this is the theft/risk workstream's
    "who had access" answer)."""
    restaurant = get_or_create_restaurant(db, current_user)
    member = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.restaurant_id == restaurant.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if not member.user_id:
        raise HTTPException(
            status_code=400,
            detail="This staff member has no login — nothing to assign a role to.",
        )

    target_role = _parse_staff_role(body.staff_role)
    _require_grant_allowed(current_user, target_role)

    linked_user = db.query(models.User).filter(models.User.id == member.user_id).first()
    if not linked_user:
        raise HTTPException(status_code=404, detail="Linked user account not found")

    before_role = linked_user.staff_role.value if linked_user.staff_role else None
    linked_user.staff_role = target_role
    db.commit()

    write_audit_log(
        db, restaurant.id, "staff_role_assigned", "staff_router",
        entity_type="user", entity_id=linked_user.id,
        before={"staff_role": before_role},
        after={"staff_role": target_role.value},
        reasoning=f"Role changed for '{member.name}': {before_role} -> {target_role.value}.",
        approved_by=current_user.email,
    )

    # Real-time risk signal alongside the audit trail above — a privilege
    # change is worth surfacing immediately, not just on a later audit-log
    # review. Excludes the actor (current_user): a Manager who just made the
    # change doesn't need to be told about their own action; an Owner making
    # the change already sees it happen. push_notifier's handler filters
    # ACCOUNT_LOCKED-style role targets minus this one user.
    from events.bus import emit_async, EventType
    emit_async(EventType.STAFF_ROLE_CHANGED, {
        "restaurant_id": restaurant.id,
        "staff_name": member.name,
        "before_role": before_role,
        "after_role": target_role.value,
        "changed_by": current_user.email,
        "changed_by_user_id": current_user.id,
    })

    db.refresh(member)
    return _staff_out(member, db)


# ── Owner "view as" — real impersonation, not a UI-only preview ─────────────
# An Owner-tier capability (require_role(ADMIN), not the 7-tier matrix), kept
# in this file since it operates on the same roster. See auth.get_current_user
# for how imp_session_id resolves back to the target on every request.

@router.post("/{staff_id}/impersonate", response_model=schemas.ImpersonateResponse)
async def impersonate_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    member = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.restaurant_id == restaurant.id,
    ).first()
    # 404, not 403: a staff member belonging to another tenant must be
    # indistinguishable from one that doesn't exist (same id-enumeration
    # reasoning as reservations.py's table lookup).
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if not member.user_id:
        raise HTTPException(
            status_code=400,
            detail="This staff member has no login — nothing to impersonate.",
        )

    target = db.query(models.User).filter(models.User.id == member.user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Linked user account not found")
    if target.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if target.role in (models.Role.ADMIN, models.Role.SUPERADMIN):
        raise HTTPException(status_code=403, detail="Cannot impersonate an Owner or Admin account.")
    if target.is_active is False:
        raise HTTPException(status_code=400, detail="This staff member's login is deactivated.")

    expires_at = utcnow() + timedelta(minutes=auth.IMPERSONATION_TOKEN_EXPIRE_MINUTES)
    session = models.ImpersonationSession(
        tenant_id=current_user.tenant_id,
        restaurant_id=restaurant.id,
        impersonator_user_id=current_user.id,
        target_user_id=target.id,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    write_audit_log(
        db, restaurant.id, "impersonation_started", "staff_router",
        entity_type="user", entity_id=target.id,
        after={
            "impersonator_id": current_user.id,
            "impersonator_email": current_user.email,
            "session_id": session.id,
            "target_staff_role": target.staff_role.value if target.staff_role else None,
        },
        reasoning=f"{current_user.email} started impersonating {target.email}.",
        approved_by=current_user.email,
    )

    token = auth.create_access_token(
        data={
            "sub": target.email,
            "ver": target.token_version or 0,
            "imp_session_id": session.id,
            "imp_by": current_user.id,
        },
        expires_delta=timedelta(minutes=auth.IMPERSONATION_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "target": {
            "id": target.id,
            "email": target.email,
            "staff_role": target.staff_role.value if target.staff_role else None,
        },
        "expires_in_minutes": auth.IMPERSONATION_TOKEN_EXPIRE_MINUTES,
    }


@router.post("/end-impersonation")
async def end_impersonation(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Must accept a plain get_current_user dependency (not require_role) — this
    is called WHILE holding an impersonation token, whose resolved current_user
    is the target (role=STAFF), not the Owner."""
    impersonated_by = getattr(current_user, "impersonated_by", None)
    if not impersonated_by:
        raise HTTPException(status_code=400, detail="Not currently impersonating.")

    session = db.query(models.ImpersonationSession).filter(
        models.ImpersonationSession.id == impersonated_by["session_id"]
    ).first()
    if session and session.ended_at is None:
        session.ended_at = utcnow()
        session.end_reason = "manual"
        db.commit()

        write_audit_log(
            db, session.restaurant_id, "impersonation_ended", "staff_router",
            entity_type="user", entity_id=current_user.id,
            before={"session_id": session.id},
            reasoning=f"{impersonated_by['impersonator_email']} ended impersonating {current_user.email}.",
            approved_by=impersonated_by["impersonator_email"],
        )

    return {"status": "ended"}


@router.get("/impersonation-log", response_model=List[schemas.ImpersonationLogEntry])
async def impersonation_log(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    sessions = db.query(models.ImpersonationSession).filter(
        models.ImpersonationSession.restaurant_id == restaurant.id
    ).order_by(models.ImpersonationSession.started_at.desc()).limit(50).all()

    user_ids = {s.impersonator_user_id for s in sessions} | {s.target_user_id for s in sessions}
    users_by_id = {
        u.id: u for u in db.query(models.User).filter(models.User.id.in_(user_ids)).all()
    } if user_ids else {}

    now = utcnow()
    out = []
    for s in sessions:
        impersonator = users_by_id.get(s.impersonator_user_id)
        target = users_by_id.get(s.target_user_id)
        if s.ended_at is not None:
            computed_status = "ended"
        elif s.expires_at < now:
            computed_status = "expired"
        else:
            computed_status = "active"
        out.append({
            "session_id": s.id,
            "impersonator_email": impersonator.email if impersonator else "unknown",
            "target_email": target.email if target else "unknown",
            "started_at": s.started_at,
            "expires_at": s.expires_at,
            "ended_at": s.ended_at,
            "status": computed_status,
        })
    return out
