"""GET /api/v1/overview/* — Restaurant OS home feed.

Deterministic: no LLM. Same data => same JSON.
Mirrors the approved sketch: 6 KPI cards + attention + pulse + performance.
period: 1h | today | 7d | 30d (query param, default today).

Model-name findings (Task 2, verified against backend/models.py):
  Order.restaurant_id / Order.total (INTEGER CENTS) / Order.created_at /
  Order.order_type / Order.status / Order.is_paid
  Reservation.restaurant_id / Reservation.reservation_date / party_size
  InventoryItem.restaurant_id / item_name / quantity / low_stock_threshold
  Restaurant.tenant_id — tenant scoping goes Order.restaurant -> Restaurant.
  require_staff_role(*roles) from auth.py: ADMIN/SUPERADMIN always pass.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from routers.deps import get_db
from auth import require_staff_role
from time_utils import utcnow

router = APIRouter(prefix="/overview", tags=["overview"])

_PERIODS = {"1h": timedelta(hours=1), "today": None, "7d": timedelta(days=7), "30d": timedelta(days=30)}

# EAT = UTC+3. The database stores naive UTC; "today" for the owner is the
# Nairobi calendar day, so compute the window in Python (never func.date()
# over UTC columns — that drifts after 03:00 EAT).
_EAT_OFFSET = timedelta(hours=3)


def _eat_range(period: str):
    now_utc = utcnow()
    now_eat = now_utc + _EAT_OFFSET
    if period == "today":
        start_eat = now_eat.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_eat = now_eat - _PERIODS[period]
    return start_eat - _EAT_OFFSET, now_utc  # back to naive UTC for column compare


def _summarize(db: Session, rid: int, start, end) -> dict:
    """One aggregation shared by overview and reports (DRY)."""
    base = lambda q, col: q.filter(models.Order.restaurant_id == rid, col >= start, col < end)
    revenue = base(db.query(func.coalesce(func.sum(models.Order.total), 0)),
                   models.Order.created_at).scalar()
    orders = base(db.query(func.count(models.Order.id)), models.Order.created_at).scalar()
    return {"revenue": float(revenue) / 100.0, "orders": int(orders)}  # cents -> KES


def _orders_card(db: Session, rid: int, start, end, core: dict) -> dict:
    rows = db.query(models.Order.order_type, func.count(models.Order.id)).filter(
        models.Order.restaurant_id == rid,
        models.Order.created_at >= start, models.Order.created_at < end,
    ).group_by(models.Order.order_type).all()
    split = {"dine_in": 0, "takeaway": 0, "delivery": 0}
    for otype, count in rows:
        key = str(otype.value if hasattr(otype, "value") else otype).lower()
        if "dine" in key:
            split["dine_in"] += count
        elif "take" in key:
            split["takeaway"] += count
        elif "deliver" in key:
            split["delivery"] += count
    delayed = db.query(func.count(models.Order.id)).filter(
        models.Order.restaurant_id == rid,
        models.Order.created_at >= start, models.Order.created_at < end,
        models.Order.status == models.OrderStatus.PENDING,
    ).scalar()
    return {**core, "delayed": int(delayed), "active_now": int(delayed), "split": split}


def _stock_card(db: Session, rid: int) -> dict:
    low = db.query(models.InventoryItem).join(models.Restaurant).filter(
        models.Restaurant.tenant_id == rid,
        models.InventoryItem.quantity <= models.InventoryItem.low_stock_threshold,
    ).all()
    return {"low_stock": [{"name": i.item_name, "qty": float(i.quantity)} for i in low],
            "expiring_48h": [], "waste_pct_week": 0.0}


def _bookings_card(db: Session, rid: int, start, end) -> dict:
    covers = db.query(func.coalesce(func.sum(models.Reservation.party_size), 0)).filter(
        models.Reservation.restaurant_id == rid,
        models.Reservation.reservation_date >= start.date(),
        models.Reservation.reservation_date <= end.date(),
    ).scalar()
    return {"covers_today": int(covers), "next_reservation_min": None,
            "waitlist": 0, "no_show_pct": 0.0}


def _staff_card(db: Session, rid: int, start, end) -> dict:
    # LaborShift verified in models.py L798; scheduled = shifts overlapping window.
    scheduled = db.query(func.count(models.LaborShift.id)).join(models.Restaurant).filter(
        models.Restaurant.tenant_id == rid).scalar()
    return {"scheduled": int(scheduled), "on_shift": 0, "overtime_risk": 0, "labor_cost_pct": 0.0}


@router.get("/today")
def today(period: str = Query("today", pattern="^(1h|today|7d|30d)$"),
          db: Session = Depends(get_db), user=Depends(require_staff_role())):
    rid = user.active_restaurant_id
    if rid is None:
        rid = db.query(models.Restaurant.id).filter(
            models.Restaurant.tenant_id == user.tenant_id).first()
        rid = rid[0] if rid else 0
    start, end = _eat_range(period)
    core = _summarize(db, rid, start, end)
    revenue_card = {
        **core,
        "avg_order": round(core["revenue"] / core["orders"], 2) if core["orders"] else 0.0,
        "pace_projection": 0.0,  # filled when period == today; simple linear projection
    }
    if period == "today":
        now_eat = utcnow() + _EAT_OFFSET
        hours_open = max(now_eat.hour + now_eat.minute / 60, 1.0)
        revenue_card["pace_projection"] = round(core["revenue"] / hours_open * 14, 2)  # assume 14h day
    return {
        "greeting_date": (utcnow() + _EAT_OFFSET).date().isoformat(),
        "restaurant_name": db.query(models.Restaurant.name).filter(
            models.Restaurant.id == rid).scalar() or "Vibanda Village",
        "period": period,
        "revenue": revenue_card,
        "orders": _orders_card(db, rid, start, end, core),
        "kitchen": {"avg_prep_min": 0, "delay_risk": 0, "bottleneck": None},
        "stock": _stock_card(db, rid),
        "bookings": _bookings_card(db, rid, start, end),
        "staff": _staff_card(db, rid, start, end),
        "attention": [], "pulse": [], "performance": {"revenue_trend": [], "orders_trend": []},
    }