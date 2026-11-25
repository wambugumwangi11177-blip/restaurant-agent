"""Owner Home v11: today strip, done today, setup checklist."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from integration.inbox_models import PosSourceBinding, PosInbox
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from time_utils import utcnow

router = APIRouter(prefix="/eleven/home", tags=["eleven-home"])

_EAT = timedelta(hours=3)


def _eat_day_start(now):
    local = now + _EAT
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - _EAT


def _pending_kes(item: dict) -> int:
    cents = item.get("amount_cents")
    if cents is not None:
        return int(cents)
    if item.get("kind") == "restock":
        return int(item.get("estimated_total_cents") or 500_000)
    return 0


@router.get("/today")
def home_today(
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    now = utcnow()
    start = _eat_day_start(now)

    from services.owner_today import today_cash_breakdown

    payload = today_cash_breakdown(db, restaurant.id, start)
    payload.update({
        "empty_sales": "Starts when the till connects or sales are imported.",
        "empty_cash": "Cash in the drawer is cash sales for today (M-Pesa is separate).",
    })
    return payload


@router.get("/done-today")
def home_done_today(
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    start = _eat_day_start(utcnow())

    handovers = (
        db.query(func.count(models.KitchenHandover.id))
        .filter(
            models.KitchenHandover.restaurant_id == restaurant.id,
            models.KitchenHandover.created_at >= start,
            models.KitchenHandover.owner_review_status.in_(("approved", "matched")),
        )
        .scalar()
        or 0
    )
    deliveries = (
        db.query(func.count(models.DeliveryReceipt.id))
        .filter(
            models.DeliveryReceipt.restaurant_id == restaurant.id,
            models.DeliveryReceipt.created_at >= start,
            models.DeliveryReceipt.status == "checked",
        )
        .scalar()
        or 0
    )
    parts = []
    if handovers:
        parts.append(f"{handovers} handover{'s' if handovers != 1 else ''} matched")
    if deliveries:
        parts.append(f"{deliveries} deliver{'ies' if deliveries != 1 else 'y'} checked")
    summary = ", ".join(parts) if parts else None
    return {
        "handovers_matched": int(handovers),
        "deliveries_checked": int(deliveries),
        "summary": summary,
        "empty": "Nothing recorded yet today.",
    }


@router.get("/setup")
def home_setup(
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)

    jack = (
        db.query(models.User)
        .filter(
            models.User.active_restaurant_id == restaurant.id,
            models.User.staff_role == models.StaffRole.STOCKKEEPER,
        )
        .first()
    )
    jack_done = False
    if jack:
        prog = (
            db.query(models.StaffSetupProgress)
            .filter(models.StaffSetupProgress.user_id == jack.id)
            .first()
        )
        jack_done = bool(prog and prog.questionnaire_completed_at)

    binding = db.query(PosSourceBinding).filter_by(restaurant_id=restaurant.id).first()
    till_rows = 0
    if binding:
        till_rows = db.query(func.count(PosInbox.id)).filter(PosInbox.binding_id == binding.id).scalar() or 0
    till_connected = till_rows > 0

    staff = (
        db.query(func.count(models.User.id))
        .filter(
            models.User.active_restaurant_id == restaurant.id,
            models.User.role == models.Role.STAFF,
        )
        .scalar()
        or 0
    )

    return {
        "steps": [
            {"id": "jack_questions", "done": jack_done, "label": "Jack: answer setup questions", "href": "/eleven/more/team"},
            {"id": "till", "done": till_connected, "label": "Connect the till", "href": "/eleven/settings/till"},
            {"id": "staff", "done": staff >= 2, "label": "Add staff", "href": "/eleven/more/team"},
        ],
        "all_done": jack_done and till_connected and staff >= 2,
    }