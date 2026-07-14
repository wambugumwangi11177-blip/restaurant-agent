"""
backend/ai/enterprise/benchmarking.py
────────────────────────────────────────
Cross-location benchmarking (Phase 10). Compares the same KPIs across every
restaurant in an organization and ranks them, so a chain owner or regional
manager can see who's leading and who needs help.

Reuses the per-restaurant deterministic analytics (ops_manager health score,
30-day revenue) rather than inventing new metrics — it only aggregates and ranks
what each site already computes. No LLM.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from time_utils import utcnow

logger = logging.getLogger("ai.enterprise")


def _restaurants_in_org(db: Session, organization_id: int) -> list[models.Restaurant]:
    return (
        db.query(models.Restaurant)
        .filter(models.Restaurant.organization_id == organization_id)
        .all()
    )


def _site_kpis(db: Session, restaurant: models.Restaurant) -> dict:
    """The comparable KPIs for one site. Degrades to zeros on thin data."""
    since = utcnow() - timedelta(days=30)
    revenue_30d = (
        db.query(func.coalesce(func.sum(models.Order.total), 0))
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= since,
        )
        .scalar()
    ) or 0
    orders_30d = (
        db.query(func.count(models.Order.id))
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= since,
        )
        .scalar()
    ) or 0

    health = None
    try:
        from ai.ops_manager import get_operations_dashboard
        health = get_operations_dashboard(db, restaurant.id).get("health_score")
    except Exception:  # noqa: BLE001 — one site's failure never sinks the roll-up
        pass

    return {
        "restaurant_id": restaurant.id,
        "name": restaurant.name,
        "region_id": restaurant.region_id,
        "revenue_30d_cents": int(revenue_30d),
        "orders_30d": int(orders_30d),
        "avg_order_value_cents": int(revenue_30d / orders_30d) if orders_30d else 0,
        "health_score": health,
    }


def benchmark_organization(db: Session, organization_id: int) -> dict:
    """Rank every site in an organization by 30-day revenue, with chain totals and
    averages, plus best/worst callouts."""
    org = db.query(models.Organization).filter(models.Organization.id == organization_id).first()
    if org is None:
        return {"available": False, "error": "Organization not found."}

    sites = [_site_kpis(db, r) for r in _restaurants_in_org(db, organization_id)]
    if not sites:
        return {"available": True, "organization": org.name, "site_count": 0,
                "sites": [], "totals": {}, "leaders": {}}

    sites.sort(key=lambda s: s["revenue_30d_cents"], reverse=True)
    for i, s in enumerate(sites, start=1):
        s["rank"] = i

    total_rev = sum(s["revenue_30d_cents"] for s in sites)
    total_orders = sum(s["orders_30d"] for s in sites)
    healths = [s["health_score"] for s in sites if isinstance(s["health_score"], (int, float))]

    return {
        "available": True,
        "organization": org.name,
        "site_count": len(sites),
        "totals": {
            "revenue_30d_cents": total_rev,
            "orders_30d": total_orders,
            "avg_revenue_per_site_cents": int(total_rev / len(sites)),
            "avg_health_score": round(sum(healths) / len(healths), 1) if healths else None,
        },
        "leaders": {
            "top_revenue": sites[0]["name"],
            "bottom_revenue": sites[-1]["name"],
        },
        "sites": sites,
    }
