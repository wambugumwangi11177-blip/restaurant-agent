"""Sign-in handover: reset passwords with one-time codes."""
from __future__ import annotations

import secrets
from datetime import timedelta

import auth
import models
from fastapi import HTTPException
from sqlalchemy.orm import Session
from staff_audit import record_entry
from time_utils import utcnow

HANDOVER_AUDIT_RESET = "handover_sign_in_reset"
HANDOVER_AUDIT_PASSWORD_SET = "handover_password_set"
HANDOVER_TTL = timedelta(hours=72)
HANDOVER_MAX_ATTEMPTS = 5
HANDOVER_LOCK_MINUTES = 15
ELEVEN_LOGIN_ROLES = {
    models.StaffRole.OWNER,
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.CONTROLLER,
}


def may_reset_sign_in(actor: models.User, target: models.User) -> bool:
    if actor.role == models.Role.SUPERADMIN:
        return True
    if actor.tenant_id is None or target.tenant_id is None or actor.tenant_id != target.tenant_id:
        return False
    if actor.role == models.Role.ADMIN or actor.staff_role == models.StaffRole.OWNER:
        return True
    return False


def list_tenant_logins(db: Session, tenant_id: int) -> list[models.User]:
    return (
        db.query(models.User)
        .filter(
            models.User.tenant_id == tenant_id,
            models.User.is_active.is_(True),
            models.User.staff_role.in_(ELEVEN_LOGIN_ROLES),
        )
        .order_by(models.User.email)
        .all()
    )


def _bump_sessions(db: Session, user: models.User) -> None:
    user.token_version = (user.token_version or 0) + 1
    db.query(models.AuthToken).filter(models.AuthToken.user_id == user.id).delete(
        synchronize_session=False
    )


def reset_sign_in(
    db: Session,
    *,
    actor: models.User,
    target: models.User,
    restaurant_id: int,
) -> str:
    if not may_reset_sign_in(actor, target):
        raise HTTPException(status_code=403, detail="Not allowed to reset this login.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = utcnow()
    target.hashed_password = None
    target.password_reset_required = True
    target.must_change_password = True
    target.handover_code_hash = auth.get_password_hash(code)
    target.handover_code_expires_at = now + HANDOVER_TTL
    target.handover_failed_attempts = 0
    target.handover_locked_until = None
    _bump_sessions(db, target)
    record_entry(
        db,
        restaurant_id,
        actor,
        HANDOVER_AUDIT_RESET,
        "user",
        f"Sign-in reset for {target.email}",
        entity_id=target.id,
        detail={"target_email": target.email, "expires_at": (now + HANDOVER_TTL).isoformat()},
    )
    return code


def _handover_locked(user: models.User) -> bool:
    if user.handover_locked_until and user.handover_locked_until > utcnow():
        return True
    if user.handover_locked_until and user.handover_locked_until <= utcnow():
        user.handover_locked_until = None
        user.handover_failed_attempts = 0
    return False


def verify_handover_code(db: Session, user: models.User, code: str) -> None:
    if not user.password_reset_required:
        return
    if _handover_locked(user):
        raise HTTPException(
            status_code=429,
            detail="Too many wrong handover codes. Try again in a few minutes.",
        )
    if not user.handover_code_hash or not user.handover_code_expires_at:
        raise HTTPException(status_code=400, detail="No active handover code for this account.")
    if user.handover_code_expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Handover code has expired. Ask for a new reset.")
    if not auth.verify_password(code, user.handover_code_hash):
        user.handover_failed_attempts = (user.handover_failed_attempts or 0) + 1
        if user.handover_failed_attempts >= HANDOVER_MAX_ATTEMPTS:
            user.handover_locked_until = utcnow() + timedelta(minutes=HANDOVER_LOCK_MINUTES)
        db.commit()
        raise HTTPException(status_code=400, detail="Wrong handover code.")


def clear_handover_after_password_set(
    db: Session,
    user: models.User,
    *,
    restaurant_id: int | None,
    via_email: str,
) -> None:
    user.password_reset_required = False
    user.must_change_password = False
    user.handover_code_hash = None
    user.handover_code_expires_at = None
    user.handover_failed_attempts = 0
    user.handover_locked_until = None
    if restaurant_id is not None:
        record_entry(
            db,
            restaurant_id,
            user,
            HANDOVER_AUDIT_PASSWORD_SET,
            "user",
            f"New password set after handover ({via_email})",
            entity_id=user.id,
            detail={"email": via_email},
        )