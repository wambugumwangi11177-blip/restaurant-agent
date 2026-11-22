"""Super-admin client list, open/close context, staff provisioning — not for restaurant users."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from restaurant_scope import get_restaurant_or_none
from staff_audit import record_entry
from time_utils import utcnow

router = APIRouter(prefix="/super", tags=["super-admin"])

TEST_RESTAURANT_TENANT = "Test Restaurant"


class ClientRow(BaseModel):
    tenant_id: int
    tenant_name: str
    restaurant_id: int
    restaurant_name: str
    staff_logins: int
    last_import_at: str | None
    setup_complete: bool


class OpenClientIn(BaseModel):
    restaurant_id: int


class NewClientIn(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=80)
    restaurant_name: str = Field(min_length=2, max_length=120)
    address: str = ""


class StaffLoginIn(BaseModel):
    email: EmailStr
    staff_role: models.StaffRole
    display_name: str = ""


def _last_import(db: Session, restaurant_id: int) -> datetime | None:
    row = (
        db.query(models.ImportRun)
        .filter(models.ImportRun.restaurant_id == restaurant_id)
        .order_by(models.ImportRun.created_at.desc())
        .first()
    )
    return row.created_at if row else None


def _staff_count(db: Session, tenant_id: int) -> int:
    return (
        db.query(func.count(models.User.id))
        .filter(
            models.User.tenant_id == tenant_id,
            models.User.is_active.is_(True),
            models.User.role != models.Role.SUPERADMIN,
        )
        .scalar()
        or 0
    )


def _sort_clients(rows: list[ClientRow]) -> list[ClientRow]:
    def key(row: ClientRow) -> tuple:
        if (row.tenant_name or "").strip().lower() == "eleven":
            return (0, row.tenant_name.lower())
        if (row.tenant_name or "").strip().lower() == TEST_RESTAURANT_TENANT.lower():
            return (1, row.tenant_name.lower())
        return (2, row.tenant_name.lower())

    return sorted(rows, key=key)


@router.get("/clients", response_model=list[ClientRow])
def list_clients(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN)),
):
    rows: list[ClientRow] = []
    for restaurant in db.query(models.Restaurant).order_by(models.Restaurant.id).all():
        tenant = db.query(models.Tenant).filter(models.Tenant.id == restaurant.tenant_id).first()
        if tenant is None:
            continue
        last = _last_import(db, restaurant.id)
        rows.append(
            ClientRow(
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                restaurant_id=restaurant.id,
                restaurant_name=restaurant.name,
                staff_logins=_staff_count(db, tenant.id),
                last_import_at=last.isoformat() if last else None,
                setup_complete=_staff_count(db, tenant.id) >= 2,
            )
        )
    return _sort_clients(rows)


@router.get("/context")
def active_context(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN)),
):
    restaurant = get_restaurant_or_none(db, current_user)
    if not restaurant:
        return {"open": False}
    tenant = db.query(models.Tenant).filter(models.Tenant.id == restaurant.tenant_id).first()
    return {
        "open": True,
        "restaurant_id": restaurant.id,
        "restaurant_name": restaurant.name,
        "tenant_name": tenant.name if tenant else "",
    }


@router.post("/open/{restaurant_id}")
def open_client(
    restaurant_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN)),
):
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Client not found")
    actor = db.query(models.User).filter(models.User.id == current_user.id).first()
    actor.active_restaurant_id = restaurant.id
    db.commit()
    tenant = db.query(models.Tenant).filter(models.Tenant.id == restaurant.tenant_id).first()
    return {
        "restaurant_id": restaurant.id,
        "restaurant_name": restaurant.name,
        "tenant_name": tenant.name if tenant else "",
    }


@router.post("/close")
def close_client(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN)),
):
    actor = db.query(models.User).filter(models.User.id == current_user.id).first()
    actor.active_restaurant_id = None
    db.commit()
    return {"open": False}


@router.post("/clients", response_model=ClientRow)
def create_client(
    body: NewClientIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN)),
):
    name = body.tenant_name.strip()
    if db.query(models.Tenant).filter(func.lower(models.Tenant.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail="A client with this name already exists.")
    tenant = models.Tenant(name=name)
    db.add(tenant)
    db.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=body.restaurant_name.strip(), address=body.address.strip())
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    return ClientRow(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        restaurant_id=restaurant.id,
        restaurant_name=restaurant.name,
        staff_logins=0,
        last_import_at=None,
        setup_complete=False,
    )


@router.post("/clients/{tenant_id}/staff")
def create_staff_login(
    tenant_id: int,
    body: StaffLoginIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN)),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Client not found")
    restaurant = (
        db.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant_id).order_by(models.Restaurant.id).first()
    )
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant missing for client")
    email = body.email.strip().lower()
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    system_role = models.Role.ADMIN if body.staff_role == models.StaffRole.OWNER else models.Role.STAFF
    user = models.User(
        email=email,
        hashed_password=None,
        role=system_role,
        staff_role=body.staff_role,
        tenant_id=tenant.id,
        must_change_password=True,
        is_active=True,
        is_email_verified=True,
    )
    db.add(user)
    db.flush()
    user.active_restaurant_id = restaurant.id
    display = (body.display_name or email.split("@")[0]).strip()
    db.add(
        models.StaffMember(
            restaurant_id=restaurant.id,
            user_id=user.id,
            name=display,
            role_title=body.staff_role.value,
        )
    )
    if body.staff_role in (models.StaffRole.STOCKKEEPER, models.StaffRole.CONTROLLER):
        db.add(models.StaffSetupProgress(user_id=user.id, restaurant_id=restaurant.id))
    record_entry(
        db,
        restaurant.id,
        current_user,
        "staff_login_created",
        "staff",
        f"Super-admin created {email} as {body.staff_role.value}.",
        entity_id=user.id,
    )
    db.commit()
    return {"user_id": user.id, "email": email, "staff_role": body.staff_role.value}


@router.get("/import-log")
def import_log(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.SUPERADMIN)),
):
    restaurant = get_restaurant_or_none(db, current_user)
    if not restaurant:
        raise HTTPException(status_code=409, detail="Open a client first.")
    rows = (
        db.query(models.ImportRun)
        .filter(models.ImportRun.restaurant_id == restaurant.id)
        .order_by(models.ImportRun.created_at.desc())
        .limit(40)
        .all()
    )
    return [
        {
            "id": row.id,
            "filename": row.filename,
            "inserted": row.inserted,
            "skipped": row.skipped,
            "failed": __import__("json").loads(row.failed_json or "[]"),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]