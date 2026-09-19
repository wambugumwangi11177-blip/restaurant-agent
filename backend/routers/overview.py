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
import hashlib
import logging

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from auth import require_staff_role
from time_utils import utcnow

logger = logging.getLogger("overview")

router = APIRouter(prefix="/overview", tags=["overview"])

_PERIODS = {"1h": timedelta(hours=1), "today": None, "7d": timedelta(days=7), "30d": timedelta(days=30)}

# EAT = UTC+3. The database stores naive UTC; "today" for the owner is the
# Nairobi calendar day, so compute the window in Python (never func.date()
# over UTC columns — that drifts after 03:00 EAT).
_EAT_OFFSET = timedelta(hours=3)


def _eat_now():
    return utcnow() + _EAT_OFFSET


def _restaurant_id(db: Session, user) -> int:
    """Resolve the selected restaurant inside the authenticated tenant."""
    query = db.query(models.Restaurant.id).filter(
        models.Restaurant.tenant_id == user.tenant_id)
    if user.active_restaurant_id is not None:
        query = query.filter(models.Restaurant.id == user.active_restaurant_id)
    row = query.order_by(models.Restaurant.id).first()
    if row is None and user.active_restaurant_id is not None:
        raise HTTPException(404, "Restaurant not found")
    return row[0] if row else 0


def _eat_range(period: str):
    now_eat = _eat_now()
    if period == "today":
        start_eat = now_eat.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_eat = now_eat - _PERIODS[period]
    return start_eat - _EAT_OFFSET, now_eat - _EAT_OFFSET  # naive UTC for column compare


def _summarize(db: Session, rid: int, start, end) -> dict:
    """Paid, non-cancelled order value by creation time; not payment cash flow."""
    base = lambda q, col: q.filter(
        models.Order.restaurant_id == rid, col >= start, col < end,
        models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
    )
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
        models.Order.status.in_([models.OrderStatus.PENDING, models.OrderStatus.PREP]),
    ).scalar()
    return {**core, "orders": sum(split.values()), "delayed": 0,
            "active_now": int(active), "split": split}


def _stock_card(db: Session, rid: int) -> dict:
    low = db.query(models.InventoryItem).join(models.Restaurant).filter(
        models.Restaurant.id == rid,
        models.InventoryItem.quantity <= models.InventoryItem.low_stock_threshold,
    ).all()
    return {"low_stock": [{"name": i.item_name, "qty": float(i.quantity)} for i in low],
            "expiring_48h": [], "waste_pct_week": 0.0}


def _bookings_card(db: Session, rid: int, start, end) -> dict:
    covers = db.query(func.coalesce(func.sum(models.Reservation.party_size), 0)).filter(
        models.Reservation.restaurant_id == rid,
        models.Reservation.reservation_date >= (start + _EAT_OFFSET).date(),
        models.Reservation.reservation_date <= (end + _EAT_OFFSET).date(),
    ).scalar()
    return {"covers_today": int(covers), "next_reservation_min": None,
            "waitlist": 0, "no_show_pct": 0.0}


def _staff_card(db: Session, rid: int, start, end) -> dict:
    sched = db.query(func.count(models.LaborShift.id)).join(models.Restaurant).filter(
        models.Restaurant.id == rid,
        models.LaborShift.shift_date >= (start + _EAT_OFFSET).date(),
        models.LaborShift.shift_date <= (end + _EAT_OFFSET).date(),
    ).scalar()
    worked = db.query(func.count(models.LaborShift.id)).join(models.Restaurant).filter(
        models.Restaurant.id == rid,
        models.LaborShift.shift_date >= (start + _EAT_OFFSET).date(),
        models.LaborShift.shift_date <= (end + _EAT_OFFSET).date(),
        models.LaborShift.actual_start.isnot(None),
        models.LaborShift.actual_end.is_(None),
    ).scalar()
    cost_cents = db.query(func.coalesce(func.sum(models.LaborShift.labor_cost), 0)).join(
        models.Restaurant).filter(
        models.Restaurant.id == rid,
        models.LaborShift.shift_date >= (start + _EAT_OFFSET).date(),
        models.LaborShift.shift_date <= (end + _EAT_OFFSET).date(),
    ).scalar()
    labor_pct = 0.0
    if core_rev := db.query(func.coalesce(func.sum(models.Order.total), 0)).filter(
        models.Order.restaurant_id == rid,
        models.Order.created_at >= start, models.Order.created_at < end,
        models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
    ).scalar():
        labor_pct = round((cost_cents / core_rev) * 100, 1) if core_rev else 0.0
    return {"scheduled": int(sched), "on_shift": int(worked), "overtime_risk": 0,
            "labor_cost_pct": labor_pct}


# Category -> the word the owner sees. The AI layer names things after its own
# agents ("supply_chain"); the Home page speaks the restaurant's language.
_DOMAIN_LABEL = {
    "pricing": "Pricing",
    "inventory": "Stock",
    "menu": "Menu",
    "labor": "Staff",
    "labour": "Staff",
    "supply_chain": "Purchasing",
    "marketing": "Growth",
    "profit": "Profit",
    "revenue": "Sales",
}


def _card_key(agent: str, action: str) -> str:
    """A stable id for one piece of advice.

    The owner's approve/later/reject is recorded against this key
    (models.AttentionDecision), so it MUST NOT move when the ranking reshuffles
    — keying on rank would resurrect a dismissed card the moment something else
    outranked it. Agent + the advice itself is stable for as long as the advice
    is, and changes when the advice does, which is the behaviour we want.
    """
    # usedforsecurity=False: this digest is a STABLE UI KEY, not a security
    # primitive. Nothing authenticates, signs or compares secrets with it — it
    # only has to be short, deterministic and collision-unlikely across one
    # restaurant's advice set. Without the flag Bandit rates it HIGH (CWE-327)
    # and the blocking `sast` CI job fails, which is what it did for four
    # consecutive merges. Declaring intent is the fix; the algorithm is fine
    # for a non-security key.
    digest = hashlib.sha1(
        f"{agent}|{action}".encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:10]
    return f"d-{digest}"


def _decision_cards(db: Session, rid: int) -> list:
    """What needs attention, from the Decision Intelligence layer.

    This is the point of the Home page: the owner should not have to ask. Every
    specialist agent's recommendations (pricing, inventory, menu, labour, supply
    chain, marketing) are collected, scored on impact/confidence/risk/effort and
    returned best-first, so the thing most worth doing today is at the top.

    Deterministic — no LLM. The agents computed these numbers; this only orders
    and relabels them.
    """
    from ai.decisions import get_ranked_decisions

    data = get_ranked_decisions(db, rid)
    cards = []
    for d in data.get("decisions", [])[:8]:
        action = (d.get("action") or "").strip()
        if not action:
            continue
        impact_cents = d.get("impact_cents_month") if d.get("quantified") else None
        category = (d.get("category") or "").lower()
        cards.append({
            "id": _card_key(d.get("agent") or "agent", action),
            "domain": _DOMAIN_LABEL.get(category, category.replace("_", " ").title() or "Business"),
            "title": action,
            "why": (d.get("rationale") or "").strip(),
            "what_to_do": action,
            "impact": f"About KSh {impact_cents // 100:,} a month" if impact_cents else "",
            "status": "open",
            # Surfaced so the UI can show WHY this is first, not just that it is.
            "priority_score": d.get("priority_score"),
            "confidence_pct": d.get("confidence_pct"),
        })
    return cards


def _operational_cards(db: Session, rid: int) -> list:
    """Time-critical facts, not recommendations.

    A stockout today is not a ranked suggestion — it is happening. These are
    computed directly so the page still warns the owner when the AI layer has
    nothing to say (a brand-new restaurant) or cannot run.
    """
    cards = []
    low = db.query(models.InventoryItem).join(models.Restaurant).filter(
        models.Restaurant.id == rid,
        models.InventoryItem.quantity <= models.InventoryItem.low_stock_threshold,
    ).all()
    for item in low:
        title = f"{item.item_name} is running low ({float(item.quantity)} left)"
        cards.append({
            "id": _card_key("stock", title),
            "domain": "Stock",
            "title": title,
            "why": "Current stock has reached the reorder point.",
            "what_to_do": f"Raise today's order to restock {item.item_name}.",
            "impact": "",
            "status": "open",
        })
    pending_po = db.query(func.count(models.PurchaseOrder.id)).join(models.Restaurant).filter(
        models.Restaurant.id == rid,
        func.lower(models.PurchaseOrder.status) == "pending",
    ).scalar()
    if pending_po:
        title = f"{pending_po} purchase order(s) awaiting approval"
        cards.append({
            "id": _card_key("purchasing", title),
            "domain": "Purchasing",
            "title": title,
            "why": "Approving keeps deliveries on schedule.",
            "what_to_do": "Review and approve the pending purchase orders.",
            "impact": "",
            "status": "open",
        })
    return cards


def _attention_cards(db: Session, rid: int, tenant_id: int) -> list:
    """The Home page's "what needs your attention", operational first.

    Order is deliberate: what is happening now (a stockout, an unapproved
    order) outranks what would be profitable to change, however large the
    modelled impact. The owner cannot act on a pricing recommendation while
    the kitchen is out of beef.

    The AI layer is wrapped: if an adapter raises, the owner still gets the
    operational warnings rather than an empty page. A silent degrade is the
    right trade here — Home must always render.
    """
    cards = _operational_cards(db, rid)
    try:
        ai_cards = _decision_cards(db, rid)
    except Exception:  # noqa: BLE001 — Home must render even if an agent fails
        logger.exception("[overview] decision layer failed for restaurant %s", rid)
        ai_cards = []

    # Drop AI advice that restates an operational card. "Beef is running low"
    # and "Reorder Beef soon" are one problem; showing both makes the page look
    # like it cannot count. Match on the subject (the inventory item's name),
    # not the wording, because the two layers phrase it differently.
    subjects = {
        item.item_name.lower()
        for item in db.query(models.InventoryItem).join(models.Restaurant).filter(
            models.Restaurant.id == rid,
            models.InventoryItem.quantity <= models.InventoryItem.low_stock_threshold,
        ).all()
    }
    seen = {c["id"] for c in cards}
    seen_titles = {c["title"].lower() for c in cards}
    for c in ai_cards:
        title_l = c["title"].lower()
        if c["id"] in seen or title_l in seen_titles:
            continue
        if c["domain"] == "Stock" and any(name in title_l for name in subjects):
            continue
        seen.add(c["id"])
        seen_titles.add(title_l)
        cards.append(c)

    decided = {d.card_key for d in db.query(models.AttentionDecision).filter(
        models.AttentionDecision.tenant_id == tenant_id).all()}
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
                 models.Order.created_at < end_utc,
                 models.Order.is_paid.is_(True),
                 models.Order.status != models.OrderStatus.CANCELLED).first()
        trend.append({"date": s, "revenue": float(rev) / 100.0, "orders": int(cnt)})
    return {"revenue_trend": trend, "orders_trend": trend}


@router.get("/today")
def today(period: str = Query("today", pattern="^(1h|today|7d|30d)$"),
          db: Session = Depends(get_db), user=Depends(require_staff_role())):
    rid = _restaurant_id(db, user)
    start, end = _eat_range(period)
    core = _summarize(db, rid, start, end)
    revenue_card = {
        **core,
        "avg_order": round(core["revenue"] / core["orders"], 2) if core["orders"] else 0.0,
        "pace_projection": 0.0,
    }
    # No pace forecast without verified opening hours and comparable history.
    stock = _stock_card(db, rid)
    operational_start, operational_end = _eat_range("today")
    bookings = _bookings_card(db, rid, operational_start, operational_end)
    return {
        "greeting_date": _eat_now().date().isoformat(),
        "restaurant_name": db.query(models.Restaurant.name).filter(
            models.Restaurant.id == rid).scalar() or "Vibanda Village",
        "period": period,
        "revenue_basis": "paid_non_cancelled_orders_by_creation_time",
        "unavailable_metrics": ["pace_projection", "kitchen", "delayed_orders",
                                "expiry", "waste", "waitlist", "no_show_rate", "overtime_risk"],
        "revenue": revenue_card,
        "orders": _orders_card(db, rid, start, end, core),
        "kitchen": {"avg_prep_min": 0, "delay_risk": 0, "bottleneck": None},
        "stock": stock,
        "bookings": bookings,
        "staff": _staff_card(db, rid, operational_start, operational_end),
        "attention": _attention_cards(db, rid, user.tenant_id),
        "pulse": _pulse(db, rid, _summarize(db, rid, operational_start, operational_end), stock, bookings),
        "performance": _performance(db, rid),
    }


@router.post("/attention/{card_key}/decision")
def decide(card_key: str, body: dict, db: Session = Depends(get_db),
           user=Depends(require_staff_role())):
    _restaurant_id(db, user)  # Apply the same ownership check as the feed.
    if body.get("decision") not in ("approved", "later", "rejected"):
        raise HTTPException(422, "decision must be approved|later|rejected")
    row = models.AttentionDecision(
        tenant_id=user.tenant_id, card_key=card_key, decision=body["decision"],
        decided_by=user.id,
    )
    db.add(row)
    db.commit()
    return {"card_key": card_key, "status": body["decision"]}
