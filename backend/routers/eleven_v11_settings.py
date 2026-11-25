"""Owner settings v11 — targets, reports list, connections."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from integration.inbox_models import PosInbox, PosSourceBinding
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from services.owner_prefs import read_prefs, write_prefs
from time_utils import utcnow

router = APIRouter(prefix="/eleven/settings", tags=["eleven-settings-v11"])


class TargetsIn(BaseModel):
    food_cost_target_pct: float | None = None
    monthly_sales_target_kes: float | None = None
    default_par_days: int | None = None
    locale: str | None = None


@router.get("/targets")
def get_targets(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    return read_prefs(restaurant)


@router.patch("/targets")
def patch_targets(body: TargetsIn, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    prefs = write_prefs(db, restaurant, body.model_dump(exclude_none=True))
    db.commit()
    return prefs


@router.get("/connections")
def connections(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    binding = db.query(PosSourceBinding).filter_by(restaurant_id=restaurant.id).first()
    inbox = 0
    if binding:
        inbox = db.query(PosInbox).filter_by(binding_id=binding.id).count()
    accountant = (
        db.query(models.User)
        .filter(
            models.User.active_restaurant_id == restaurant.id,
            models.User.staff_role == models.StaffRole.CONTROLLER,
        )
        .count()
    )
    return {
        "till_connected": inbox > 0,
        "till_receipts": inbox,
        "whatsapp": bool(restaurant.owner_phone),
        "accountant_seats": accountant,
    }


@router.get("/reports")
def reports_list(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    now = utcnow()
    period = now.strftime("%Y-%m")
    return {
        "schedule": {
            "daily": "21:00 EAT",
            "weekly": "Monday 08:00 EAT",
            "monthly": "Month end after final P&L",
        },
        "past": [
            {"id": f"daily-{now.date().isoformat()}", "kind": "daily", "title": f"Daily store report — {now.date().isoformat()}", "ready": True},
            {"id": f"monthly-{period}", "kind": "monthly", "title": f"Monthly P&L — {period}", "href": f"/api/v1/eleven/money/export/monthly/{period}.xlsx"},
        ],
        "notifications": True,
        "empty": "Reports begin after the first day of sales.",
    }