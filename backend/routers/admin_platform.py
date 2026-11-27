"""Headless platform API for Company OS — no routes in the Eleven frontend."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import handover
import models
from admin_platform_auth import require_platform_admin
from database import get_db
from eleven_import import apply_import, build_template, parse_csv, parse_xlsx, preview_payload
from restaurant_scope import get_restaurant_by_id
from staff_audit import record_entry

router = APIRouter(prefix="/admin/platform", tags=["admin-platform"])

_MAX_BYTES = 2_000_000


class RestaurantRow(BaseModel):
    tenant_id: int
    tenant_name: str
    restaurant_id: int
    restaurant_name: str
    staff_logins: int
    last_import_at: str | None
    setup_complete: bool


class NewRestaurantIn(BaseModel):
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


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File must be 2 MB or smaller.")
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty.")
    return data


def _parse(filename: str, data: bytes, sheet: str | None):
    name = (filename or "").lower()
    try:
        if name.endswith(".csv"):
            return parse_csv(data, sheet or "")
        if name.endswith(".xlsx"):
            return parse_xlsx(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail="Upload an .xlsx workbook or a .csv sheet.")


@router.get("/restaurants", response_model=list[RestaurantRow])
def list_restaurants(
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_platform_admin),
):
    rows: list[RestaurantRow] = []
    for restaurant in db.query(models.Restaurant).order_by(models.Restaurant.id).all():
        tenant = db.query(models.Tenant).filter(models.Tenant.id == restaurant.tenant_id).first()
        if tenant is None:
            continue
        last = _last_import(db, restaurant.id)
        count = _staff_count(db, tenant.id)
        rows.append(
            RestaurantRow(
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                restaurant_id=restaurant.id,
                restaurant_name=restaurant.name,
                staff_logins=count,
                last_import_at=last.isoformat() if last else None,
                setup_complete=count >= 2,
            )
        )
    rows.sort(key=lambda r: ((r.tenant_name.lower() != "eleven", r.tenant_name.lower())))
    return rows


@router.post("/restaurants", response_model=RestaurantRow)
def create_restaurant(
    body: NewRestaurantIn,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_platform_admin),
):
    name = body.tenant_name.strip()
    if db.query(models.Tenant).filter(func.lower(models.Tenant.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail="A client with this name already exists.")
    tenant = models.Tenant(name=name)
    db.add(tenant)
    db.flush()
    restaurant = models.Restaurant(
        tenant_id=tenant.id,
        name=body.restaurant_name.strip(),
        address=body.address.strip(),
    )
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    record_entry(
        db,
        restaurant.id,
        actor,
        "platform_restaurant_created",
        "tenant",
        f"Platform created client {name}.",
        entity_id=restaurant.id,
    )
    db.commit()
    return RestaurantRow(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        restaurant_id=restaurant.id,
        restaurant_name=restaurant.name,
        staff_logins=0,
        last_import_at=None,
        setup_complete=False,
    )


@router.post("/restaurants/{restaurant_id}/staff")
def create_staff(
    restaurant_id: int,
    body: StaffLoginIn,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_platform_admin),
):
    restaurant = get_restaurant_by_id(db, restaurant_id)
    tenant = db.query(models.Tenant).filter(models.Tenant.id == restaurant.tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
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
        active_restaurant_id=restaurant.id,
    )
    db.add(user)
    db.flush()
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
        actor,
        "staff_login_created",
        "staff",
        f"Platform created {email} as {body.staff_role.value}.",
        entity_id=user.id,
    )
    db.commit()
    return {"user_id": user.id, "email": email, "staff_role": body.staff_role.value}


@router.get("/restaurants/{restaurant_id}/import-runs")
def list_import_runs(
    restaurant_id: int,
    db: Session = Depends(get_db),
    _actor: models.User = Depends(require_platform_admin),
):
    get_restaurant_by_id(db, restaurant_id)
    rows = (
        db.query(models.ImportRun)
        .filter(models.ImportRun.restaurant_id == restaurant_id)
        .order_by(models.ImportRun.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": row.id,
            "filename": row.filename,
            "inserted": row.inserted,
            "skipped": row.skipped,
            "failed": json.loads(row.failed_json or "[]"),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/import/template")
def platform_import_template(_actor: models.User = Depends(require_platform_admin)):
    return Response(
        content=build_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="leviii-import-template.xlsx"'},
    )


@router.post("/restaurants/{restaurant_id}/import/preview")
async def platform_import_preview(
    restaurant_id: int,
    file: UploadFile = File(...),
    sheet: str | None = Form(default=None),
    db: Session = Depends(get_db),
    _actor: models.User = Depends(require_platform_admin),
):
    get_restaurant_by_id(db, restaurant_id)
    parsed = _parse(file.filename or "", await _read_upload(file), sheet)
    return preview_payload(parsed)


@router.post("/restaurants/{restaurant_id}/import/confirm")
async def platform_import_confirm(
    restaurant_id: int,
    file: UploadFile = File(...),
    sheet: str | None = Form(default=None),
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_platform_admin),
):
    restaurant = get_restaurant_by_id(db, restaurant_id)
    parsed = _parse(file.filename or "", await _read_upload(file), sheet)
    failed_rows: list[dict] = []
    try:
        summary = apply_import(db, restaurant.id, actor, parsed)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    inserted = sum(part["inserted"] for part in summary.values())
    skipped = sum(part["skipped"] for part in summary.values())
    for sheet_name, part in summary.items():
        for fail in part.get("failed") or []:
            failed_rows.append({"sheet": sheet_name, **fail})
    db.add(
        models.ImportRun(
            restaurant_id=restaurant.id,
            uploaded_by_user_id=actor.id,
            filename=file.filename or "upload",
            inserted=inserted,
            skipped=skipped,
            failed_json=json.dumps(failed_rows),
            summary_json=json.dumps(summary),
        )
    )
    record_entry(
        db,
        restaurant.id,
        actor,
        "import_confirmed",
        "import",
        f"{actor.email} confirmed a platform import: {inserted} new row(s), {skipped} already present.",
        detail={"inserted": inserted, "skipped": skipped, "sheets": summary, "via": "admin_platform"},
    )
    db.commit()
    return {"inserted": inserted, "skipped": skipped, "sheets": summary}


class StaffRow(BaseModel):
    user_id: int
    email: str
    staff_role: str | None
    display_name: str
    password_reset_required: bool
    has_password: bool
    is_active: bool


class ResetSignInOut(BaseModel):
    handover_code: str
    expires_at: str
    email: str


def _staff_display_name(db: Session, user: models.User, restaurant_id: int) -> str:
    member = (
        db.query(models.StaffMember)
        .filter(
            models.StaffMember.restaurant_id == restaurant_id,
            models.StaffMember.user_id == user.id,
        )
        .first()
    )
    if member and member.name:
        return member.name
    return user.email.split("@")[0]


@router.get("/restaurants/{restaurant_id}/staff", response_model=list[StaffRow])
def list_staff(
    restaurant_id: int,
    db: Session = Depends(get_db),
    _actor: models.User = Depends(require_platform_admin),
):
    restaurant = get_restaurant_by_id(db, restaurant_id)
    users = (
        db.query(models.User)
        .filter(
            models.User.tenant_id == restaurant.tenant_id,
            models.User.role != models.Role.SUPERADMIN,
        )
        .order_by(models.User.email)
        .all()
    )
    return [
        StaffRow(
            user_id=user.id,
            email=user.email,
            staff_role=user.staff_role.value if user.staff_role else None,
            display_name=_staff_display_name(db, user, restaurant.id),
            password_reset_required=bool(user.password_reset_required or user.must_change_password),
            has_password=user.hashed_password is not None,
            is_active=bool(user.is_active),
        )
        for user in users
    ]


@router.post("/restaurants/{restaurant_id}/staff/{user_id}/reset-sign-in", response_model=ResetSignInOut)
def reset_staff_sign_in(
    restaurant_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_platform_admin),
):
    restaurant = get_restaurant_by_id(db, restaurant_id)
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if (
        target is None
        or target.tenant_id != restaurant.tenant_id
        or target.role == models.Role.SUPERADMIN
    ):
        raise HTTPException(status_code=404, detail="Staff login not found on this client.")
    code = handover.reset_sign_in(
        db,
        actor=actor,
        target=target,
        restaurant_id=restaurant.id,
        allow_platform=True,
    )
    db.commit()
    expires = target.handover_code_expires_at
    return ResetSignInOut(
        handover_code=code,
        expires_at=expires.isoformat() if expires else "",
        email=target.email,
    )
