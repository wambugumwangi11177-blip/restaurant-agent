"""
app/api/auth.py
───────────────
Login (password + optional TOTP), current user, MFA enrolment, password change,
logout-everywhere, and member management. There is no public sign-up: the first
founder is created by execution/bootstrap_workspace.py, everyone else is added
by a founder.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_principal, require
from app.config import get_settings
from app.db import get_db
from app.kernel.audit import write_audit
from app.kernel.events import emit
from app.kernel.models import Membership, Role, User, Workspace
from app.kernel.rbac import permissions_for
from app.kernel.schemas import normalize_phone
from app.kernel.tenancy import Principal
from app.security import (
    WeakPasswordError,
    create_access_token,
    generate_mfa_secret,
    hash_password,
    mfa_provisioning_uri,
    require_strong_password,
    verify_password,
    verify_totp,
)

router = APIRouter()


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(_In):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, max_length=6)
    workspace_slug: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    email = body.email.lower()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    generic = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    if user is None:
        verify_password(body.password, hash_password("timing-equaliser"))  # same cost as a real check
        write_audit(db, action="auth.login_failed", workspace_id=None, changes={"reason": "unknown_email"})
        db.commit()
        raise generic
    if user.locked_until and user.locked_until > _now():
        raise HTTPException(status.HTTP_423_LOCKED, "Too many failed attempts. Try again later.")
    if not user.is_active or not verify_password(body.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= s.max_failed_logins:
            user.locked_until = _now() + timedelta(minutes=s.lockout_minutes)
            user.failed_logins = 0
        write_audit(db, action="auth.login_failed", workspace_id=None, entity_type="user", entity_id=user.id,
                    changes={"reason": "bad_password"})
        db.commit()
        raise generic
    if user.mfa_enabled:
        if not body.totp_code:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "mfa_required")
        if not verify_totp(user.mfa_secret or "", body.totp_code):
            user.failed_logins += 1
            write_audit(db, action="auth.login_failed", workspace_id=None, entity_type="user", entity_id=user.id,
                        changes={"reason": "bad_totp"})
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication code")

    memberships = db.execute(
        select(Membership, Workspace).join(Workspace, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == user.id).order_by(Membership.id)
    ).all()
    if body.workspace_slug:
        memberships = [(m, w) for m, w in memberships if w.slug == body.workspace_slug]
    if not memberships:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not a member of any matching workspace")
    if len(memberships) > 1 and not body.workspace_slug:
        raise HTTPException(status.HTTP_409_CONFLICT, {
            "message": "Choose a workspace", "workspaces": [w.slug for _, w in memberships]})
    membership, ws = memberships[0]

    user.failed_logins = 0
    user.locked_until = None
    write_audit(db, action="auth.login", workspace_id=ws.id, entity_type="user", entity_id=user.id,
                actor_user_id=user.id)
    db.commit()
    return {
        "access_token": create_access_token(user.id, ws.id, user.token_version),
        "token_type": "bearer",
        "expires_in": s.jwt_ttl_minutes * 60,
    }


@router.get("/auth/me")
def me(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    user = principal.user
    ws = db.get(Workspace, principal.workspace_id)
    return {
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "phone": user.phone,
                 "mfa_enabled": user.mfa_enabled},
        "workspace": {"id": ws.id, "slug": ws.slug, "name": ws.name, "timezone": ws.timezone, "currency": ws.currency},
        "role": principal.role,
        "permissions": permissions_for(principal.role),
    }


@router.post("/auth/mfa/setup")
def mfa_setup(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    user = principal.user
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA is already enabled")
    user.mfa_secret = generate_mfa_secret()
    db.commit()
    return {"secret": user.mfa_secret, "otpauth_uri": mfa_provisioning_uri(user.email, user.mfa_secret)}


class CodeIn(_In):
    code: str = Field(min_length=6, max_length=6)


@router.post("/auth/mfa/enable")
def mfa_enable(body: CodeIn, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    user = principal.user
    if not user.mfa_secret or not verify_totp(user.mfa_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code — run setup again if needed")
    user.mfa_enabled = True
    write_audit(db, action="auth.mfa_enabled", workspace_id=principal.workspace_id, entity_type="user",
                entity_id=user.id, actor_user_id=user.id)
    db.commit()
    return {"mfa_enabled": True}


class PasswordChangeIn(_In):
    current_password: str
    new_password: str = Field(max_length=256)


@router.post("/auth/password")
def change_password(body: PasswordChangeIn, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)) -> dict:
    user = principal.user
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is wrong")
    try:
        require_strong_password(body.new_password)
    except WeakPasswordError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # every existing session ends
    write_audit(db, action="auth.password_changed", workspace_id=principal.workspace_id, entity_type="user",
                entity_id=user.id, actor_user_id=user.id)
    db.commit()
    return {"changed": True, "access_token": create_access_token(user.id, principal.workspace_id, user.token_version)}


@router.post("/auth/logout-all")
def logout_all(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> dict:
    principal.user.token_version += 1
    write_audit(db, action="auth.logout_all", workspace_id=principal.workspace_id, entity_type="user",
                entity_id=principal.user_id, actor_user_id=principal.user_id)
    db.commit()
    return {"logged_out": True}


# ── Members ──────────────────────────────────────────────────────────────────

class MemberIn(_In):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role: Role
    password: str | None = Field(default=None, max_length=256)
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def norm_phone(cls, v: str | None) -> str | None:
        return normalize_phone(v)


class MemberPatch(_In):
    role: Role | None = None
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def norm_phone(cls, v: str | None) -> str | None:
        return normalize_phone(v)


def _member_out(m: Membership, u: User) -> dict:
    return {"user_id": u.id, "email": u.email, "full_name": u.full_name, "phone": u.phone, "role": m.role,
            "mfa_enabled": u.mfa_enabled, "is_active": u.is_active}


@router.get("/members")
def list_members(principal: Principal = Depends(require("records.read")), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Membership, User).join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == principal.workspace_id).order_by(Membership.id)
    ).all()
    return [_member_out(m, u) for m, u in rows]


def _founder_count(db: Session, workspace_id: int) -> int:
    return int(db.execute(select(func.count()).select_from(Membership).where(
        Membership.workspace_id == workspace_id, Membership.role == Role.FOUNDER.value)).scalar_one())


@router.post("/members", status_code=201)
def add_member(body: MemberIn, principal: Principal = Depends(require("members.manage")),
               db: Session = Depends(get_db)) -> dict:
    email = body.email.lower()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    if user is None:
        if not body.password:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "password is required for a new user")
        try:
            require_strong_password(body.password)
        except WeakPasswordError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
        if body.phone and db.execute(select(User).where(User.phone == body.phone)).scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Another user already has that phone number")
        user = User(email=email, full_name=body.full_name, phone=body.phone, password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
    elif db.execute(select(Membership).where(Membership.user_id == user.id,
                                             Membership.workspace_id == principal.workspace_id)).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Already a member")
    m = Membership(workspace_id=principal.workspace_id, user_id=user.id, role=body.role.value)
    db.add(m)
    db.flush()
    write_audit(db, action="member.add", workspace_id=principal.workspace_id, entity_type="user", entity_id=user.id,
                changes={"role": body.role.value}, actor_user_id=principal.user_id)
    emit(db, "member.added", workspace_id=principal.workspace_id, entity_type="user", entity_id=user.id,
         payload={"role": body.role.value}, actor_user_id=principal.user_id)
    db.commit()
    return _member_out(m, user)


@router.patch("/members/{user_id}")
def update_member(user_id: int, body: MemberPatch, principal: Principal = Depends(require("members.manage")),
                  db: Session = Depends(get_db)) -> dict:
    row = db.execute(select(Membership, User).join(User, User.id == Membership.user_id).where(
        Membership.workspace_id == principal.workspace_id, Membership.user_id == user_id)).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    m, u = row
    changes = body.model_dump(exclude_unset=True)
    if "role" in changes and changes["role"] is not None:
        new_role = changes["role"].value
        if m.role == Role.FOUNDER.value and new_role != Role.FOUNDER.value and _founder_count(db, principal.workspace_id) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "A workspace must keep at least one founder")
        write_audit(db, action="member.role_change", workspace_id=principal.workspace_id, entity_type="user",
                    entity_id=u.id, changes={"role": {"from": m.role, "to": new_role}}, actor_user_id=principal.user_id)
        m.role = new_role
    if "phone" in changes:
        if changes["phone"] and db.execute(select(User).where(User.phone == changes["phone"], User.id != u.id)).scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Another user already has that phone number")
        u.phone = changes["phone"]
        write_audit(db, action="member.phone_change", workspace_id=principal.workspace_id, entity_type="user",
                    entity_id=u.id, changes={"phone": {"changed": True}}, actor_user_id=principal.user_id)
    db.commit()
    return _member_out(m, u)


@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: int, principal: Principal = Depends(require("members.manage")),
                  db: Session = Depends(get_db)) -> None:
    m = db.execute(select(Membership).where(
        Membership.workspace_id == principal.workspace_id, Membership.user_id == user_id)).scalar_one_or_none()
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    if m.role == Role.FOUNDER.value and _founder_count(db, principal.workspace_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "A workspace must keep at least one founder")
    user = db.get(User, user_id)
    db.delete(m)
    user.token_version += 1  # revoke their sessions immediately
    write_audit(db, action="member.remove", workspace_id=principal.workspace_id, entity_type="user",
                entity_id=user_id, changes={"role": m.role}, actor_user_id=principal.user_id)
    db.commit()
