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

    # Sort by reliability descending
    supplier_analyses.sort(key=lambda x: x["reliability_score"], reverse=True)

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
            "at_risk_suppliers":          sum(1 for s in supplier_analyses if s["reliability_score"] < RELIABILITY_THRESHOLD),
            "avg_reliability_pct":        round(
                sum(s["reliability_score"] for s in supplier_analyses) / max(len(supplier_analyses), 1), 1
            ),
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


def _analyse_supplier(supplier: models.Supplier, orders: list[models.PurchaseOrder]) -> dict:
    delivered = [o for o in orders if o.status == "DELIVERED"]
    late      = [o for o in orders if o.status == "LATE"]
    pending   = [o for o in orders if o.status in ("PENDING", "SENT")]

    on_time_count = len(delivered)
    late_count    = len(late)
    total_closed  = on_time_count + late_count

    reliability_pct = (on_time_count / max(total_closed, 1)) * 100

    # Update stored reliability score
    supplier.reliability_score = round(reliability_pct, 1)

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
        "reliability_score": round(reliability_pct, 1),
        "reliability_label": "EXCELLENT" if reliability_pct >= 95 else
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
        "at_risk":           reliability_pct < RELIABILITY_THRESHOLD,
    }


def _generate_recommendations(supplier_analyses: list, overdue_orders: list) -> list[dict]:
    recs = []
    for s in supplier_analyses:
        if s["reliability_score"] < RELIABILITY_THRESHOLD:
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
            "overdue_orders": 0, "at_risk_suppliers": 0, "avg_reliability_pct": 0,
        },
        "suppliers": [], "overdue_orders": [],
        "recommendations": [{
            "priority": "INFO",
            "message": "No suppliers configured yet",
            "action": "Add suppliers to unlock supply chain intelligence",
        }],
    }
