"""Team activity: the owner reads what each staff member did and what went
wrong on their screens, without anyone's password. Read only; nothing here
signs in as, or acts for, a staff member."""
from __future__ import annotations

import json
import re
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from people import person_of
from routers.deps import get_or_create_restaurant, get_restaurant_or_none
from routers.eleven_owner import _require_owner
from schemas import StrictModel
from time_utils import utcnow

router = APIRouter(tags=["team-activity"])

_EAT = ZoneInfo("Africa/Nairobi")
_REPORTS_PER_MINUTE = 20

_LABELS = {
    "signed_in": "Signed in",
    "initial_password_set": "Set a first password",
    "pin_set": "Set a PIN",
    "pin_changed": "Changed a PIN",
    "pin_lockout": "PIN locked after wrong tries",
    "account_ready": "Finished account setup",
    "questions_ready": "Answered all setup questions",
    "recipes_ready": "Finished recipes setup",
    "question_answered": "Answered a setup question",
    "question_delegated": "Passed a setup question on",
    "supplier_added": "Added a supplier",
    "supplier_prefilled": "Updated a supplier",
    "opening_count": "Counted a stock item",
    "opening_profile_saved": "Saved stock item details",
    "recipe_line_added": "Added a recipe line",
    "recipe_line_updated": "Changed a recipe line",
    "recipe_line_removed": "Removed a recipe line",
    "stock_issued": "Moved stock",
    "delivery_received": "Received a delivery",
    "delivery_price_confirmed": "Confirmed delivery prices",
    "kitchen_handover": "Handed stock to the kitchen",
    "spoilage_recorded": "Wrote off wastage",
    "day_closed": "Closed the day",
    "cash_close_recorded": "Reported the day's cash",
    "chef_added": "Added a chef",
    "chef_pin_failed": "Wrong chef PIN",
    "chef_pin_locked": "Chef PIN locked",
    "close_pin_failed": "Wrong close PIN",
    "close_pin_locked": "Close PIN locked",
    "running_cost_added": "Added a running cost",
    "running_cost_paid": "Marked a running cost paid",
    "approval_threshold": "Changed an approval limit",
}
_PHOTO_CHECK = {
    "match": "matches the photos",
    "mismatch": "does not match the photos",
    "unavailable": "could not be checked",
}
_PHOTO_CHECK_RE = re.compile(r"^(?:zone_(?:open|close)|delivery|handover)_ai_(match|mismatch|unavailable)$")
_PROBLEM_ACTIONS = {"pin_lockout", "chef_pin_failed", "chef_pin_locked", "close_pin_failed", "close_pin_locked"}


class ClientErrorIn(StrictModel):
    kind: str = Field(pattern="^(script|request)$")
    screen: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=1000)
    status_code: int | None = Field(default=None, ge=100, le=599)


@router.post("/client-errors", status_code=202)
def report_client_error(
    body: ClientErrorIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_restaurant_or_none(db, current_user)
    if restaurant is None:
        return {"stored": False}
    recent = (
        db.query(func.count(models.ClientError.id))
        .filter(
            models.ClientError.user_id == current_user.id,
            models.ClientError.created_at > utcnow() - timedelta(minutes=1),
        )
        .scalar()
    )
    if recent >= _REPORTS_PER_MINUTE:
        return {"stored": False}
    db.add(models.ClientError(
        restaurant_id=restaurant.id,
        user_id=current_user.id,
        kind=body.kind,
        screen=body.screen,
        message=body.message,
        status_code=body.status_code,
    ))
    db.commit()
    return {"stored": True}


def _stamp(moment) -> dict:
    local = moment.replace(tzinfo=timezone.utc).astimezone(_EAT)
    return {"at": local.isoformat(), "day": f"{local:%a} {local.day} {local:%b}", "time": f"{local:%H:%M}"}


def _describe(row: models.StaffEntryAudit, user: models.User) -> tuple[str, str]:
    check = _PHOTO_CHECK_RE.match(row.action)
    if check:
        subject = "Delivery" if row.action.startswith("delivery") else "Handover" if row.action.startswith("handover") else "Store photo"
        return "Photo check", f"{subject} {_PHOTO_CHECK[check.group(1)]}."
    label = _LABELS.get(row.action) or row.action.replace("_", " ").capitalize()
    summary = row.summary or ""
    if user.email and summary.startswith(user.email):
        summary = summary[len(user.email):].strip()
        summary = summary[:1].upper() + summary[1:]
    return label, summary


def _attachments(db: Session, rows: list[models.StaffEntryAudit]) -> dict[int, dict]:
    """Lines and photo paths for the rows that carry them, read in a few queries."""
    out: dict[int, dict] = {row.id: {"lines": [], "photos": []} for row in rows}
    by_action: dict[str, dict[int, int]] = {}
    for row in rows:
        if row.entity_id is None:
            continue
        action = "zone_photo" if row.action in ("zone_open_photo", "zone_close_photo") else row.action
        by_action.setdefault(action, {})[row.entity_id] = row.id

    def targets(action: str) -> dict[int, int]:
        return by_action.get(action, {})

    if targets("delivery_received"):
        ids = list(targets("delivery_received"))
        for line in db.query(models.DeliveryReceiptLine).filter(models.DeliveryReceiptLine.receipt_id.in_(ids)).order_by(models.DeliveryReceiptLine.id):
            out[targets("delivery_received")[line.receipt_id]]["lines"].append(
                {"item": line.item_name, "quantity": line.quantity, "unit": line.unit}
            )
        for photo in db.query(models.DeliveryEvidencePhoto).filter(models.DeliveryEvidencePhoto.receipt_id.in_(ids)).order_by(models.DeliveryEvidencePhoto.id):
            out[targets("delivery_received")[photo.receipt_id]]["photos"].append(
                {"label": photo.kind, "path": f"/api/v1/store/deliveries/{photo.receipt_id}/photos/{photo.id}"}
            )
    if targets("kitchen_handover"):
        ids = list(targets("kitchen_handover"))
        for line in db.query(models.KitchenHandoverLine).filter(models.KitchenHandoverLine.handover_id.in_(ids)).order_by(models.KitchenHandoverLine.id):
            out[targets("kitchen_handover")[line.handover_id]]["lines"].append(
                {"item": line.item_name, "quantity": line.quantity, "unit": line.unit}
            )
        for handover in db.query(models.KitchenHandover).filter(models.KitchenHandover.id.in_(ids), models.KitchenHandover.photo_storage_key.isnot(None)):
            out[targets("kitchen_handover")[handover.id]]["photos"].append(
                {"label": "handover", "path": f"/api/v1/store/handovers/{handover.id}/photo"}
            )
    if targets("spoilage_recorded"):
        for record in db.query(models.SpoilageRecord).filter(models.SpoilageRecord.id.in_(list(targets("spoilage_recorded")))):
            out[targets("spoilage_recorded")[record.id]]["photos"].append(
                {"label": "wastage", "path": f"/api/v1/store/spoilage/{record.id}/photo"}
            )
    if targets("zone_photo"):
        for photo_id, audit_id in targets("zone_photo").items():
            out[audit_id]["photos"].append({"label": "store", "path": f"/api/v1/store/day-photos/{photo_id}/photo"})
    return out


@router.get("/eleven/team-activity")
def team_activity(
    person: int | None = Query(default=None),
    before: int | None = Query(default=None),
    limit: int = Query(default=60, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    staff = (
        db.query(models.User)
        .filter(models.User.tenant_id == restaurant.tenant_id, models.User.role == models.Role.STAFF)
        .all()
    )
    people = sorted(
        ({"id": user.id, "name": person_of(db, user)["person_name"]} for user in staff),
        key=lambda item: item["name"].lower(),
    )
    staff_ids = {user.id for user in staff}
    scope = [person] if person in staff_ids else list(staff_ids) if person is None else []

    query = db.query(models.StaffEntryAudit).filter(
        models.StaffEntryAudit.restaurant_id == restaurant.id,
        models.StaffEntryAudit.user_id.in_(scope),
    )
    if before is not None:
        query = query.filter(models.StaffEntryAudit.id < before)
    rows = query.order_by(models.StaffEntryAudit.id.desc()).limit(limit + 1).all()
    more = len(rows) > limit
    rows = rows[:limit]
    users = {user.id: user for user in staff}
    names = {item["id"]: item["name"] for item in people}
    attached = _attachments(db, rows)
    events = []
    for row in rows:
        label, summary = _describe(row, users[row.user_id])
        events.append({
            "id": row.id,
            **_stamp(row.created_at),
            "person_id": row.user_id,
            "person_name": names[row.user_id],
            "label": label,
            "summary": summary,
            "needs_attention": row.action in _PROBLEM_ACTIONS or row.action.endswith("_ai_mismatch"),
            **attached[row.id],
        })

    problems = []
    if before is None:
        errors = (
            db.query(models.ClientError)
            .filter(models.ClientError.restaurant_id == restaurant.id, models.ClientError.user_id.in_(scope))
            .order_by(models.ClientError.id.desc())
            .limit(50)
            .all()
        )
        problems = [
            {
                "id": error.id,
                **_stamp(error.created_at),
                "person_id": error.user_id,
                "person_name": names.get(error.user_id, "Someone"),
                "kind": error.kind,
                "screen": error.screen,
                "message": error.message,
                "status_code": error.status_code,
            }
            for error in errors
        ]
    return {"timezone": "Africa/Nairobi", "people": people, "events": events, "problems": problems, "has_more": more}
