"""Owner/admin Excel or CSV import. Storekeeper and kitchen cannot call it."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

import auth
import models
from ai.notify import notify_users
from database import get_db
from eleven_import import apply_import, build_template, parse_csv, parse_xlsx, preview_payload
from routers.deps import get_or_create_restaurant
from staff_audit import record_entry

router = APIRouter(prefix="/eleven/import", tags=["eleven-import"])

_MAX_BYTES = 2_000_000


def _eleven_restaurant(db: Session, user: models.User) -> models.Restaurant:
    restaurant = get_or_create_restaurant(db, user)
    tenant = db.query(models.Tenant).filter(models.Tenant.id == user.tenant_id).first()
    if not tenant or (tenant.name or "").strip().lower() != "eleven":
        raise HTTPException(status_code=403, detail="This import only writes into the Eleven restaurant.")
    return restaurant


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


@router.get("/template")
async def download_template(
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    _eleven_restaurant(db, current_user)
    return Response(
        content=build_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="eleven-import-template.xlsx"'},
    )


@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
    sheet: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    _eleven_restaurant(db, current_user)
    parsed = _parse(file.filename or "", await _read_upload(file), sheet)
    return preview_payload(parsed)


@router.post("/confirm")
async def confirm_import(
    file: UploadFile = File(...),
    sheet: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = _eleven_restaurant(db, current_user)
    parsed = _parse(file.filename or "", await _read_upload(file), sheet)
    try:
        summary = apply_import(db, restaurant.id, current_user, parsed)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    inserted = sum(part["inserted"] for part in summary.values())
    skipped = sum(part["skipped"] for part in summary.values())
    record_entry(
        db,
        restaurant.id,
        current_user,
        "import_confirmed",
        "import",
        f"{current_user.email} confirmed an import: {inserted} new row(s), {skipped} already present.",
        detail={"inserted": inserted, "skipped": skipped, "sheets": summary},
    )
    db.commit()
    owners = db.query(models.User).filter(
        models.User.tenant_id == current_user.tenant_id,
        models.User.role.in_((models.Role.ADMIN, models.Role.SUPERADMIN)),
        models.User.is_active.is_(True),
        models.User.id != current_user.id,
    ).all()
    if owners:
        notify_users(
            db,
            [owner.id for owner in owners],
            "Eleven import saved",
            f"{inserted} new row(s) from the workbook. {skipped} were already there.",
            "staff.setup",
            url="/eleven/import",
        )
    return {"inserted": inserted, "skipped": skipped, "sheets": summary}
