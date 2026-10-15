"""
backend/ai/supply_chain/intelligence.py
─────────────────────────────────────────
Supply Chain Intelligence Agent — Layer 5.

What it does:
  1. Supplier reliability scoring (on-time delivery %)
  2. Lead time analysis (actual vs promised)
  3. Cost trend tracking (is this supplier getting more expensive?)
  4. Stockout attribution (which supplier failures caused stockouts?)
  5. Reorder recommendations with supplier selection
"""

from datetime import timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func
import models
from time_utils import utcnow

RELIABILITY_THRESHOLD = 85.0   # Below this = consider switching supplier

# A reliability percentage means nothing until a supplier has a track record: one delivered order is 100% on
# time, which is not "reliable", it is "unknown" (D3). Below this many closed orders (on time + late) the
# supplier is "learning": no score, no at-risk flag, no recommendation. The tiered PO auto-approval
# (ai/workflows/engine.py) uses the same number, from here.
MIN_CLOSED_ORDERS_FOR_RELIABILITY = 3


def get_supply_chain_intelligence(db: Session, restaurant_id: int) -> dict:
    """Complete supply chain analysis."""
    suppliers = db.query(models.Supplier).filter(
        models.Supplier.restaurant_id == restaurant_id,
        models.Supplier.is_active     == True,
    ).all()

    if not suppliers:
        return _empty_response()

    # One batched query for every supplier's last-50 orders instead of one
    # query per supplier — a window function preserves the exact "50 most
    # recent per supplier" semantics the old per-supplier query had.
    orders_by_supplier = _fetch_recent_orders_by_supplier(db, [s.id for s in suppliers], limit=50)

    supplier_analyses = []
    for supplier in suppliers:
        analysis = _analyse_supplier(supplier, orders_by_supplier.get(supplier.id, []))
        supplier_analyses.append(analysis)

    # Measured suppliers first, best to worst; suppliers still "learning" (no score yet) after them.
    supplier_analyses.sort(key=lambda x: (x["reliability_score"] is not None, x["reliability_score"] or 0), reverse=True)
    measured = [s["reliability_score"] for s in supplier_analyses if s["reliability_score"] is not None]

    # Pending orders (overdue)
    now = utcnow()
    overdue = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.restaurant_id == restaurant_id,
        models.PurchaseOrder.status        == "SENT",
        models.PurchaseOrder.expected_at   <= now,
    ).all()

    # Total procurement spend
    total_spend = db.query(func.sum(models.PurchaseOrder.total_cost)).filter(
        models.PurchaseOrder.restaurant_id == restaurant_id,
        models.PurchaseOrder.status        == "DELIVERED",
        models.PurchaseOrder.ordered_at    >= now - timedelta(days=30),
    ).scalar() or 0

    recommendations = _generate_recommendations(supplier_analyses, overdue)

    return {
        "summary": {
            "total_suppliers":            len(suppliers),
            "total_procurement_spend_30d": total_spend,
            "overdue_orders":             len(overdue),
            "at_risk_suppliers":          sum(1 for s in supplier_analyses if s["at_risk"]),
            "suppliers_learning":         sum(1 for s in supplier_analyses if s["reliability_state"] == "learning"),
            "avg_reliability_pct":        round(sum(measured) / len(measured), 1) if measured else None,
        },
        "suppliers":       supplier_analyses,
        "overdue_orders":  [_serialize_order(o) for o in overdue[:10]],
        "recommendations": recommendations,
    }


def _fetch_recent_orders_by_supplier(
    db: Session, supplier_ids: list[int], limit: int
) -> dict[int, list[models.PurchaseOrder]]:
    """The last `limit` PurchaseOrders per supplier, in one query instead of
    one `.limit(limit)` query per supplier. Fetches every order for these
    suppliers ordered newest-first, then groups and slices to `limit` per
    supplier in Python — simpler than a window-function query, and fine at
    realistic scale (a restaurant's full PO history is at most low
    thousands of rows, not worth a per-supplier subquery for)."""
    if not supplier_ids:
        return {}

    all_orders = (
        db.query(models.PurchaseOrder)
        .filter(models.PurchaseOrder.supplier_id.in_(supplier_ids))
        .order_by(models.PurchaseOrder.ordered_at.desc())
        .all()
    )

    result: dict[int, list[models.PurchaseOrder]] = defaultdict(list)
    for order in all_orders:
        bucket = result[order.supplier_id]
        if len(bucket) < limit:
            bucket.append(order)
    return result


def reliability_from_orders(orders: list[models.PurchaseOrder]) -> tuple[float | None, int]:
    """(on-time %, closed orders). The percentage is None until MIN_CLOSED_ORDERS_FOR_RELIABILITY orders have closed."""
    on_time = sum(1 for o in orders if o.status == "DELIVERED")
    closed = on_time + sum(1 for o in orders if o.status == "LATE")
    if closed < MIN_CLOSED_ORDERS_FOR_RELIABILITY:
        return None, closed
    return on_time / closed * 100, closed


def refresh_supplier_reliability(db: Session, supplier_id: int) -> float | None:
    """The WRITE path for Supplier.reliability_score: recompute it from the supplier's last 50 orders and store it.

    Called when a purchase order closes (ai/reorder.py::receive_purchase_order) — never from a read. D3: the
    analysis below used to overwrite this column every time anyone opened the supply-chain page, so merely
    looking at the data changed what the tiered auto-approval trusted. Stays put while the supplier is still
    learning. The caller commits.
    """
    supplier = db.query(models.Supplier).filter(models.Supplier.id == supplier_id).first()
    if supplier is None:
        return None
    orders = _fetch_recent_orders_by_supplier(db, [supplier_id], limit=50).get(supplier_id, [])
    pct, _closed = reliability_from_orders(orders)
    if pct is not None:
        supplier.reliability_score = round(pct, 1)
    return pct


def _analyse_supplier(supplier: models.Supplier, orders: list[models.PurchaseOrder]) -> dict:
    """Read-only: analyses a supplier, writes nothing (D3)."""
    delivered = [o for o in orders if o.status == "DELIVERED"]
    late      = [o for o in orders if o.status == "LATE"]
    pending   = [o for o in orders if o.status in ("PENDING", "SENT")]

    on_time_count = len(delivered)
    late_count    = len(late)
    reliability_pct, total_closed = reliability_from_orders(orders)
    learning = reliability_pct is None

    # Actual lead times for delivered orders
    lead_times = []
    for o in delivered:
        if o.ordered_at and o.delivered_at:
            lead_days = (o.delivered_at - o.ordered_at).days
            lead_times.append(lead_days)

    avg_lead_days = round(sum(lead_times) / max(len(lead_times), 1), 1) if lead_times else supplier.avg_lead_days

    # Cost trend (simple: compare first vs second half of order history)
    costs = [o.cost_per_unit for o in delivered if o.cost_per_unit]
    if len(costs) >= 4:
        first_half = costs[:len(costs)//2]
        second_half = costs[len(costs)//2:]
        cost_trend_pct = round(
            ((sum(second_half)/len(second_half) - sum(first_half)/len(first_half))
             / max(sum(first_half)/len(first_half), 1)) * 100, 1
        )
    else:
        cost_trend_pct = 0.0

    return {
        "id":                supplier.id,
        "name":              supplier.name,
        "contact_phone":     supplier.contact_phone,
        "reliability_score": None if learning else round(reliability_pct, 1),
        "reliability_state": "learning" if learning else "measured",
        "closed_orders":     total_closed,
        "reliability_label": "LEARNING" if learning else
                             "EXCELLENT" if reliability_pct >= 95 else
                             "GOOD"      if reliability_pct >= 85 else
                             "POOR",
        "total_orders":      len(orders),
        "delivered_on_time": on_time_count,
        "delivered_late":    late_count,
        "pending_orders":    len(pending),
        "avg_lead_days":     avg_lead_days,
        "promised_lead_days": supplier.avg_lead_days,
        "lead_time_variance": round(avg_lead_days - supplier.avg_lead_days, 1),
        "cost_trend_pct":    cost_trend_pct,
        "cost_trend_label":  "increasing" if cost_trend_pct > 5 else
                             "decreasing" if cost_trend_pct < -5 else "stable",
        "at_risk":           (not learning) and reliability_pct < RELIABILITY_THRESHOLD,
    }


def _generate_recommendations(supplier_analyses: list, overdue_orders: list) -> list[dict]:
    recs = []
    for s in supplier_analyses:
        if s["reliability_score"] is not None and s["reliability_score"] < RELIABILITY_THRESHOLD:
            recs.append({
                "priority":    "HIGH",
                "supplier":    s["name"],
                "message":     f"{s['name']} reliability at {s['reliability_score']:.1f}% — below {RELIABILITY_THRESHOLD}% threshold",
                "action":      "Find alternative supplier for critical items. Maintain minimum safety stock.",
            })
        if s["cost_trend_pct"] > 10:
            recs.append({
                "priority":    "MEDIUM",
                "supplier":    s["name"],
                "message":     f"{s['name']} prices up {s['cost_trend_pct']}% — review contract",
                "action":      "Negotiate new pricing or get quotes from alternative suppliers.",
            })
    if overdue_orders:
        recs.append({
            "priority": "CRITICAL",
            "supplier": "Multiple",
            "message":  f"{len(overdue_orders)} overdue purchase order(s)",
            "action":   "Contact suppliers immediately. Check stock levels for affected items.",
        })
    return recs


def _serialize_order(o: models.PurchaseOrder) -> dict:
    days_overdue = (utcnow() - o.expected_at).days if o.expected_at else 0
    return {
        "id":           o.id,
        "supplier":     o.supplier.name if o.supplier else "Unknown",
        "item":         o.inventory_item.item_name if o.inventory_item else "Unknown",
        "qty":          o.quantity_ordered,
        "expected_at":  o.expected_at.isoformat() if o.expected_at else None,
        "days_overdue": days_overdue,
        "total_cost":   o.total_cost,
    }


def _empty_response() -> dict:
    return {
        "summary": {
            "total_suppliers": 0, "total_procurement_spend_30d": 0,
            "overdue_orders": 0, "at_risk_suppliers": 0, "suppliers_learning": 0, "avg_reliability_pct": None,
        },
        "suppliers": [], "overdue_orders": [],
        "recommendations": [{
            "priority": "INFO",
            "message": "No suppliers configured yet",
            "action": "Add suppliers to unlock supply chain intelligence",
        }],
    }
