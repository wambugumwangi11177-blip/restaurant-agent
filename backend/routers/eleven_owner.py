"""Owner-only Eleven summary — honest when POS/import data is absent."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from routers.deps import get_or_create_restaurant
from time_utils import utcnow

router = APIRouter(prefix="/eleven", tags=["eleven-owner"])

_EAT = timedelta(hours=3)
_PERIODS = {"today": None, "7d": timedelta(days=7), "30d": timedelta(days=30)}


def _require_owner(user: models.User) -> None:
    if user.role != models.Role.ADMIN or user.staff_role != models.StaffRole.OWNER:
        raise HTTPException(status_code=403, detail="Owner access only.")
    tenant = (user.tenant.name or "").strip().lower()
    if tenant != "eleven":
        raise HTTPException(status_code=403, detail="Eleven owner only.")


@router.get("/summary")
def owner_summary(
    period: str = Query(default="7d"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_owner(current_user)
    if period not in _PERIODS:
        raise HTTPException(status_code=422, detail="period must be today, 7d, or 30d")
    restaurant = get_or_create_restaurant(db, current_user)
    now = utcnow()
    start = now - _PERIODS[period] if _PERIODS[period] else (now + _EAT).replace(hour=0, minute=0, second=0, microsecond=0) - _EAT

    paid_orders = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant.id,
        models.Order.created_at >= start,
        models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
    )
    order_count = paid_orders.count()
    revenue_cents = (
        db.query(func.coalesce(func.sum(models.Order.total), 0))
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.created_at >= start,
            models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .scalar()
    )
    voids = db.query(func.count(models.Order.id)).filter(
        models.Order.restaurant_id == restaurant.id,
        models.Order.created_at >= start,
        models.Order.status == models.OrderStatus.CANCELLED,
    ).scalar()

    paid_rows = paid_orders.all()
    by_day_map: dict[str, int] = {}
    by_hour_map: dict[int, int] = {}
    for order in paid_rows:
        if order.created_at:
            day_key = order.created_at.date().isoformat()
            by_day_map[day_key] = by_day_map.get(day_key, 0) + 1
            by_hour_map[order.created_at.hour] = by_hour_map.get(order.created_at.hour, 0) + 1

    items = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.restaurant_id == restaurant.id)
        .all()
    )
    needs_cost = [i.item_name for i in items if (i.cost_per_unit or 0) <= 0 and (i.quantity or 0) > 0]
    valued = [i for i in items if (i.cost_per_unit or 0) > 0]
    stock_value_cents = sum(int((i.cost_per_unit or 0) * (i.quantity or 0)) for i in valued)

    return {
        "period": period,
        "has_sales_data": order_count > 0,
        "sales": {
            "tickets": order_count,
            "revenue_kes": float(revenue_cents) / 100.0 if order_count else None,
            "voids": int(voids or 0),
            "by_day": [{"day": d, "tickets": c} for d, c in sorted(by_day_map.items())],
            "by_hour": [{"hour": h, "tickets": c} for h, c in sorted(by_hour_map.items())],
        },
        "stock": {
            "value_kes": float(stock_value_cents) / 100.0 if valued else None,
            "needs_cost": needs_cost,
            "state": "needs_cost" if needs_cost else ("ready" if valued else "empty"),
        },
        "imported_yet": order_count > 0 or len(items) > 1,
        "empty_message": (
            None
            if order_count > 0
            else "No sales in this period yet. Import sales or connect the till — we will not guess figures."
        ),
    }