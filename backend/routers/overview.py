"""GET /api/v1/overview/* — Restaurant OS home feed.

Deterministic: no LLM. Same data => same JSON.
Mirrors the approved sketch: 6 KPI cards + attention + pulse + performance.
period: 1h | today | 7d | 30d (query param, default today).

Model-name findings (Task 2, verified against backend/models.py):
  Order.restaurant_id / Order.total (INTEGER CENTS) / Order.created_at /
  Order.order_type / Order.status / Order.is_paid
  Reservation.restaurant_id / reservation_date / party_size
  InventoryItem.restaurant_id / item_name / quantity / low_stock_threshold
  LaborShift.restaurant_id / shift_date / labor_cost (cents) / actual_hours
  Restaurant.tenant_id — tenant scoping goes Order.restaurant -> Restaurant.
  require_staff_role(*roles) from auth.py: ADMIN/SUPERADMIN always pass.
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from auth import require_staff_role
from time_utils import utcnow

router = APIRouter(prefix="/overview", tags=["overview"])

_PERIODS = {"1h": timedelta(hours=1), "today": None, "7d": timedelta(days=7), "30d": timedelta(days=30)}

# EAT = UTC+3. The database stores naive UTC; "today" for the owner is the
# Nairobi calendar day, so compute the window in Python (never func.date()
# over UTC columns — that drifts after 03:00 EAT).
_EAT_OFFSET = timedelta(hours=3)


def _eat_now():
    return utcnow() + _EAT_OFFSET


def _eat_range(period: str):
    now_eat = _eat_now()
    if period == "today":
        start_eat = now_eat.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_eat = now_eat - _PERIODS[period]
    return start_eat - _EAT_OFFSET, now_eat - _EAT_OFFSET  # naive UTC for column compare


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
    active = db.query(func.count(models.Order.id)).filter(
        models.Order.restaurant_id == rid,
        models.Order.created_at >= start, models.Order.created_at < end,
        models.Order.status.in_([models.OrderStatus.PENDING, models.OrderStatus.PREPARING]),
    ).scalar()
    return {**core, "delayed": 0, "active_now": int(active), "split": split}


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
    sched = db.query(func.count(models.LaborShift.id)).join(models.Restaurant).filter(
        models.Restaurant.tenant_id == rid,
        models.LaborShift.shift_date >= start.date(),
        models.LaborShift.shift_date <= end.date(),
    ).scalar()
    worked = db.query(func.count(models.LaborShift.id)).join(models.Restaurant).filter(
        models.Restaurant.tenant_id == rid,
        models.LaborShift.shift_date >= start.date(),
        models.LaborShift.shift_date <= end.date(),
        models.LaborShift.actual_start.isnot(None),
        models.LaborShift.actual_end.is_(None),
    ).scalar()
    cost_cents = db.query(func.coalesce(func.sum(models.LaborShift.labor_cost), 0)).join(
        models.Restaurant).filter(
        models.Restaurant.tenant_id == rid,
        models.LaborShift.shift_date >= start.date(),
        models.LaborShift.shift_date <= end.date(),
    ).scalar()
    labor_pct = 0.0
    if core_rev := db.query(func.coalesce(func.sum(models.Order.total), 0)).filter(
        models.Order.restaurant_id.in_(
            db.query(models.Restaurant.id).filter(models.Restaurant.tenant_id == rid)),
        models.Order.created_at >= start, models.Order.created_at < end,
    ).scalar():
        labor_pct = round((cost_cents / core_rev) * 100, 1) if core_rev else 0.0
    return {"scheduled": int(sched), "on_shift": int(worked), "overtime_risk": 0,
            "labor_cost_pct": labor_pct}


def _attention_cards(db: Session, rid: int) -> list:
    cards = []
    low = db.query(models.InventoryItem).join(models.Restaurant).filter(
        models.Restaurant.tenant_id == rid,
        models.InventoryItem.quantity <= models.InventoryItem.low_stock_threshold,
    ).all()
    for item in low:
        cards.append({
            "id": f"stock-{item.id}",
            "domain": "Stock",
            "title": f"{item.item_name} is running low ({float(item.quantity)} left)",
            "why": "Current stock has reached the reorder point.",
            "what_to_do": f"Raise today's order to restock {item.item_name}.",
            "impact": "",
            "status": "open",
        })
    pending_po = db.query(func.count(models.PurchaseOrder.id)).join(models.Restaurant).filter(
        models.Restaurant.tenant_id == rid,
        models.PurchaseOrder.status == "pending",
    ).scalar()
    if pending_po:
        cards.append({
            "id": "po-pending", "domain": "Purchasing",
            "title": f"{pending_po} purchase order(s) awaiting approval",
            "why": "Approving keeps deliveries on schedule.",
            "what_to_do": "Review and approve the pending purchase orders.",
            "impact": "", "status": "open",
        })
    # decided cards are filtered out by the decision endpoint read below
    decided = {d.card_key for d in db.query(models.AttentionDecision).filter(
        models.AttentionDecision.tenant_id == rid).all()}
    return [c for c in cards if c["id"] not in decided]


def _pulse(db: Session, rid: int, core: dict, stock: dict, bookings: dict) -> list:
    pulse = []
    if core["orders"]:
        pulse.append({"domain": "Orders",
                      "headline": f"{core['orders']} orders",
                      "detail": f"{core['revenue']:.0f} KSh so far"})
    if stock["low_stock"]:
        pulse.append({"domain": "Stock",
                      "headline": f"{stock['low_stock'][0]['name']} runs low",
                      "detail": f"{len(stock['low_stock'])} items to watch"})
    if bookings["covers_today"]:
        pulse.append({"domain": "Bookings",
                      "headline": f"{bookings['covers_today']} covers expected",
                      "detail": "See bookings for times"})
    return pulse


def _performance(db: Session, rid: int) -> dict:
    trend = []
    now_eat = _eat_now()
    for back in range(6, -1, -1):
        day = (now_eat - timedelta(days=back)).date()
        s = day.strftime("%Y-%m-%d")
        start_utc = now_eat.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=back) - _EAT_OFFSET
        end_utc = start_utc + timedelta(days=1)
        rev, cnt = db.query(
            func.coalesce(func.sum(models.Order.total), 0),
            func.count(models.Order.id),
        ).filter(models.Order.restaurant_id == rid,
                 models.Order.created_at >= start_utc,
                 models.Order.created_at < end_utc).first()
        trend.append({"date": s, "revenue": float(rev) / 100.0, "orders": int(cnt)})
    return {"revenue_trend": trend, "orders_trend": trend}


@router.get("/today")
def today(period: str = Query("today", pattern="^(1h|today|7d|30d)$"),
          db: Session = Depends(get_db), user=Depends(require_staff_role())):
    rid = user.active_restaurant_id
    if rid is None:
        row = db.query(models.Restaurant.id, models.Restaurant.name).filter(
            models.Restaurant.tenant_id == user.tenant_id).first()
        rid = row[0] if row else 0
    start, end = _eat_range(period)
    core = _summarize(db, rid, start, end)
    revenue_card = {
        **core,
        "avg_order": round(core["revenue"] / core["orders"], 2) if core["orders"] else 0.0,
        "pace_projection": 0.0,
    }
    if period == "today":
        now_eat = _eat_now()
        hours_open = max(now_eat.hour + now_eat.minute / 60, 1.0)
        revenue_card["pace_projection"] = round(core["revenue"] / hours_open * 14, 2)  # 14h day
    stock = _stock_card(db, rid)
    bookings = _bookings_card(db, rid, start, end)
    return {
        "greeting_date": _eat_now().date().isoformat(),
        "restaurant_name": db.query(models.Restaurant.name).filter(
            models.Restaurant.id == rid).scalar() or "Vibanda Village",
        "period": period,
        "revenue": revenue_card,
        "orders": _orders_card(db, rid, start, end, core),
        "kitchen": {"avg_prep_min": 0, "delay_risk": 0, "bottleneck": None},
        "stock": stock,
        "bookings": bookings,
        "staff": _staff_card(db, rid, start, end),
        "attention": _attention_cards(db, rid),
        "pulse": _pulse(db, rid, core, stock, bookings),
        "performance": _performance(db, rid),
    }


@router.post("/attention/{card_key}/decision")
def decide(card_key: str, body: dict, db: Session = Depends(get_db),
           user=Depends(require_staff_role())):
    if body.get("decision") not in ("approved", "later", "rejected"):
        raise HTTPException(422, "decision must be approved|later|rejected")
    row = models.AttentionDecision(
        tenant_id=user.tenant_id, card_key=card_key, decision=body["decision"],
        decided_by=user.id,
    )
    db.add(row)
    db.commit()
    return {"card_key": card_key, "status": body["decision"]}