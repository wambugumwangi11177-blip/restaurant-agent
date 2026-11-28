"""Cash + M-Pesa day close — controllers and managers only."""
from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

import auth
import models
from bill_schedule import business_today
from database import get_db
from money_visibility import hides_money
from routers.deps import get_or_create_restaurant
from schemas import StrictModel
from staff_audit import record_entry
from store_access import require_module
from time_utils import utcnow

router = APIRouter(prefix="/store", tags=["store"])


class CashCloseIn(StrictModel):
    cash_counted_kes: float = Field(ge=0)
    mpesa_counted_kes: float = Field(ge=0)
    notes: str = ""


def _cash_roles(user: models.User) -> bool:
    if user.role in (models.Role.ADMIN, models.Role.SUPERADMIN):
        return True
    return user.staff_role in (models.StaffRole.CONTROLLER, models.StaffRole.MANAGER)


def _expected_cash_cents(db: Session, restaurant_id: int, day) -> tuple[int | None, bool]:
    from ai.cash_reconciliation.intelligence import expected_cash_amount_cents

    start = datetime.combine(day, time.min)
    end = datetime.combine(day, time.max)
    has_orders = (
        db.query(models.Order.id)
        .filter(models.Order.restaurant_id == restaurant_id, models.Order.created_at >= start)
        .first()
        is not None
    )
    if not has_orders:
        return None, True
    return expected_cash_amount_cents(db, restaurant_id, start, end), False


@router.get("/cash-close/status")
async def cash_close_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "day-close")
    restaurant = get_or_create_restaurant(db, current_user)
    if hides_money(current_user, "/store/cash-close"):
        raise HTTPException(status_code=403, detail="The storekeeper does not count cash here.")
    day = business_today()
    row = (
        db.query(models.DayCashClose)
        .filter(models.DayCashClose.restaurant_id == restaurant.id, models.DayCashClose.business_date == day)
        .first()
    )
    expected_cash, pending = _expected_cash_cents(db, restaurant.id, day)
    stock_closed = (
        db.query(models.DayClose.id)
        .filter(models.DayClose.restaurant_id == restaurant.id, models.DayClose.created_at >= datetime.combine(day, time.min))
        .first()
        is not None
    )
    payload = {
        "business_date": day.isoformat(),
        "stock_closed": stock_closed,
        "cash_closed": row is not None,
        "expected_pending": pending if row is None else row.expected_pending,
        "reminder_time": restaurant.day_close_reminder_time or "22:00",
    }
    if row is None:
        if expected_cash is not None:
            payload["expected_cash_kes"] = expected_cash / 100.0
        return payload
    payload["cash_counted_kes"] = row.cash_counted_cents / 100.0
    payload["mpesa_counted_kes"] = row.mpesa_counted_cents / 100.0
    if row.expected_cash_cents is not None:
        payload["expected_cash_kes"] = row.expected_cash_cents / 100.0
    return payload


@router.post("/cash-close", status_code=201)
async def save_cash_close(
    body: CashCloseIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "day-close")
    if not _cash_roles(current_user):
        raise HTTPException(status_code=403, detail="Only the accountant or floor manager records cash.")
    restaurant = get_or_create_restaurant(db, current_user)
    day = business_today()
    existing = (
        db.query(models.DayCashClose)
        .filter(models.DayCashClose.restaurant_id == restaurant.id, models.DayCashClose.business_date == day)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Cash for today is already closed.")
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    expected_cash, pending = _expected_cash_cents(db, restaurant.id, day)
    row = models.DayCashClose(
        restaurant_id=restaurant.id,
        business_date=day,
        user_id=user.id,
        cash_counted_cents=round(body.cash_counted_kes * 100),
        mpesa_counted_cents=round(body.mpesa_counted_kes * 100),
        expected_cash_cents=expected_cash,
        expected_mpesa_cents=None,
        expected_pending=pending,
        status="reported",
        notes=body.notes.strip(),
    )
    db.add(row)
    record_entry(
        db,
        restaurant.id,
        user,
        "cash_close_recorded",
        "day_cash_close",
        f"{user.email} recorded today's cash and M-Pesa counts.",
        entity_id=None,
        detail={"business_date": day.isoformat(), "expected_pending": pending},
    )
    db.commit()
    from ai.notify import notify_users

    owners = db.query(models.User).filter(
        models.User.tenant_id == user.tenant_id,
        models.User.role.in_((models.Role.ADMIN, models.Role.SUPERADMIN)),
        models.User.is_active.is_(True),
    ).all()
    if owners:
        notify_users(
            db,
            [o.id for o in owners],
            title="Cash close recorded",
            body="Today's cash and M-Pesa counts were keyed.",
            url="/eleven",
            event_type="day_cash_close",
        )
    return {"status": "reported", "expected_pending": pending}