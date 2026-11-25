"""Owner / platform-admin sign-in handover resets."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

import auth
import handover
import models
from database import get_db
from routers.deps import get_or_create_restaurant
router = APIRouter(prefix="/eleven/logins", tags=["eleven-handover"])


class LoginRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    staff_role: str | None
    password_reset_required: bool
    has_password: bool


class ResetSignInOut(BaseModel):
    handover_code: str
    expires_at: str
    must_log_out: bool
    email: str


@router.get("", response_model=list[LoginRow])
def list_logins(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(models.StaffRole.OWNER)),
):
    if current_user.tenant_id is None:
        raise HTTPException(status_code=400, detail="No tenant on this account.")
    restaurant = get_or_create_restaurant(db, current_user)
    rows = handover.list_tenant_logins(db, current_user.tenant_id)
    rows = [
        u
        for u in rows
        if u.role != models.Role.SUPERADMIN
        and u.active_restaurant_id == restaurant.id
    ]
    return [
        LoginRow(
            id=u.id,
            email=u.email,
            staff_role=u.staff_role.value if u.staff_role else None,
            password_reset_required=bool(u.password_reset_required),
            has_password=u.hashed_password is not None,
        )
        for u in rows
    ]


@router.post("/{user_id}/reset-sign-in", response_model=ResetSignInOut)
def reset_sign_in(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN, models.Role.ADMIN)),
):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.staff_role not in handover.ELEVEN_LOGIN_ROLES:
        raise HTTPException(status_code=400, detail="This login is not in the handover list.")
    if not handover.may_reset_sign_in(current_user, target):
        raise HTTPException(status_code=403, detail="Not allowed to reset this login.")

    restaurant = get_or_create_restaurant(db, current_user)
    code = handover.reset_sign_in(
        db,
        actor=current_user,
        target=target,
        restaurant_id=restaurant.id,
    )
    db.commit()
    expires = target.handover_code_expires_at
    return ResetSignInOut(
        handover_code=code,
        expires_at=expires.isoformat() if expires else "",
        must_log_out=current_user.id == target.id,
        email=target.email,
    )


@router.get("/admin", response_model=list[LoginRow])
def admin_list_eleven_logins(
    tenant_name: str = "Eleven",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN)),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.name == tenant_name).first()
    if tenant is None:
        return []
    rows = handover.list_tenant_logins(db, tenant.id)
    return [
        LoginRow(
            id=u.id,
            email=u.email,
            staff_role=u.staff_role.value if u.staff_role else None,
            password_reset_required=bool(u.password_reset_required),
            has_password=u.hashed_password is not None,
        )
        for u in rows
    ]


@router.post("/admin/{user_id}/reset-sign-in", response_model=ResetSignInOut)
def admin_reset_sign_in(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN)),
):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.staff_role not in handover.ELEVEN_LOGIN_ROLES:
        raise HTTPException(status_code=400, detail="This login is not in the handover list.")
    restaurant = (
        db.query(models.Restaurant).filter(models.Restaurant.tenant_id == target.tenant_id).first()
    )
    if restaurant is None:
        raise HTTPException(status_code=400, detail="No restaurant for tenant.")
    code = handover.reset_sign_in(
        db,
        actor=current_user,
        target=target,
        restaurant_id=restaurant.id,
    )
    db.commit()
    expires = target.handover_code_expires_at
    return ResetSignInOut(
        handover_code=code,
        expires_at=expires.isoformat() if expires else "",
        must_log_out=False,
        email=target.email,
    )