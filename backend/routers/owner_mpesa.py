"""/api/v1/owner/mpesa/* — the owner's M-Pesa statement (docs/v2/SPEC.md S6.1): upload it, see what was uploaded, undo an upload.

Owners, managers and controllers (the accountant) may use it; every other staff role gets 403. Everything is scoped to the caller's own
tenant and active restaurant (routers/deps.py): there is no restaurant id anywhere in this API, so there is none to forge, and an upload
id that is not this restaurant's is a 404. Observer-mode deployments block the whole /owner prefix (observer_mode.py).

The file is a CSV exported from M-Pesa. What the matching does with it (does each payment have its sale, does each sale have its
payment) is S6.2; this only takes it in.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from auth import require_staff_role
from database import get_db
from owner.mpesa_statement import import_statement, upload_json
from parsers.mpesa_csv import MAX_BYTES, StatementError
from rate_limit import limiter
from routers.deps import get_restaurant_or_none

router = APIRouter(prefix="/owner/mpesa", tags=["owner-mpesa"])

_roles = require_staff_role(models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.CONTROLLER)


def _restaurant(db: Session, user: models.User) -> models.Restaurant:
    restaurant = get_restaurant_or_none(db, user)
    if restaurant is None:
        raise HTTPException(404, "Restaurant not found")
    return restaurant


@router.post("/statement", status_code=201)
@limiter.limit("10/minute")
def upload_statement(request: Request, response: Response, file: UploadFile = File(...), db: Session = Depends(get_db),
                     user: models.User = Depends(_roles)):
    """Upload an M-Pesa statement (CSV). 201 with what was new; 200 when every payment in it was already uploaded.
    `not_read` lists the rows that were left out and why — nothing is guessed at."""
    restaurant = _restaurant(db, user)
    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, f"This file is larger than {MAX_BYTES // (1024 * 1024)} MB. Export a shorter period and upload that.")
    try:
        result = import_statement(db, restaurant.id, user.id, file.filename, raw)
    except StatementError as exc:
        raise HTTPException(422, str(exc)) from None
    if not result["new"]:
        response.status_code = 200
    return result


@router.get("/statements")
def list_statements(db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    """What has been uploaded, newest first, and how many payments are on file in all."""
    rid = _restaurant(db, user).id
    rows = db.query(models.MpesaStatementUpload).filter(models.MpesaStatementUpload.restaurant_id == rid).order_by(
        models.MpesaStatementUpload.uploaded_at.desc(), models.MpesaStatementUpload.id.desc()).limit(100).all()
    lines = db.query(func.count(models.MpesaStatementLine.id)).filter(models.MpesaStatementLine.restaurant_id == rid).scalar() or 0
    return {"statements": [upload_json(u) for u in rows], "payments_on_file": lines}


@router.delete("/statements/{upload_id}")
def delete_statement(upload_id: int, db: Session = Depends(get_db), user: models.User = Depends(_roles)):
    """Undo an upload: its payments leave the file, so a wrong statement does not stay in the matching."""
    rid = _restaurant(db, user).id
    upload = db.query(models.MpesaStatementUpload).filter(models.MpesaStatementUpload.id == upload_id,
                                                          models.MpesaStatementUpload.restaurant_id == rid).first()
    if upload is None:
        raise HTTPException(404, "Statement not found")
    removed = upload.line_count
    db.query(models.MpesaStatementLine).filter(models.MpesaStatementLine.upload_id == upload.id,
                                               models.MpesaStatementLine.restaurant_id == rid).delete(synchronize_session=False)
    db.delete(upload)
    db.commit()
    return {"deleted": upload_id, "payments_removed": removed}
