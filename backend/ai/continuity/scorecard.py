"""
Founder-continuity scorecard (report: "Automate the routine work, not the founder").

A deterministic, read-only weekly scorecard so an operator (or the founder after
an absence) can see in one call which restaurants are at risk and whether the
company needs a human. No LLM involved: every number comes from the database.

Per restaurant it scores 0-100 from four signals the report names for a health
score - usage, freshness, unresolved escalations, support load - and flags
red/amber/green. The platform summary applies the report's "20% red" rule: a
call is warranted only when more than 20% of restaurants are red.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

import models
from time_utils import utcnow

RED_BELOW = 50
AMBER_BELOW = 75
CALL_WHEN_RED_SHARE_ABOVE = 0.20


def _status(score: int) -> str:
    return "red" if score < RED_BELOW else "amber" if score < AMBER_BELOW else "green"


def restaurant_health(db: Session, restaurant: models.Restaurant, now=None) -> dict:
    now = now or utcnow()
    week = now - timedelta(days=7)
    prev_week = now - timedelta(days=14)
    rid = restaurant.id

    last_order = (
        db.query(models.Order.created_at)
        .filter(models.Order.restaurant_id == rid)
        .order_by(models.Order.created_at.desc())
        .first()
    )
    last_order_at = last_order[0] if last_order else None
    orders_7d = db.query(models.Order).filter(
        models.Order.restaurant_id == rid, models.Order.created_at >= week).count()
    orders_prev = db.query(models.Order).filter(
        models.Order.restaurant_id == rid,
        models.Order.created_at >= prev_week, models.Order.created_at < week).count()
    open_tickets = db.query(models.SupportTicket).filter(
        models.SupportTicket.restaurant_id == rid,
        models.SupportTicket.status.in_(
            [models.SupportTicketStatus.OPEN, models.SupportTicketStatus.IN_PROGRESS]),
    ).count()

    score = 100
    reasons: list[str] = []

    # Freshness: no recent orders means the data (and the value report) is stale.
    if last_order_at is None:
        score -= 40
        reasons.append("no orders recorded")
    else:
        idle_days = (now - last_order_at).days
        if idle_days >= 7:
            score -= 40
            reasons.append(f"no orders for {idle_days} days")
        elif idle_days >= 3:
            score -= 15
            reasons.append(f"no orders for {idle_days} days")

    # Usage trend: a collapse versus the prior week precedes churn.
    if orders_prev >= 10 and orders_7d < orders_prev * 0.5:
        score -= 25
        reasons.append(f"orders down {orders_prev}->{orders_7d} week on week")

    # Unresolved human-needed items.
    if open_tickets:
        score -= min(20, 5 * open_tickets)
        reasons.append(f"{open_tickets} open support ticket(s)")

    unacked = (
        db.query(models.Notification)
        .join(models.User, models.User.id == models.Notification.user_id)
        .join(models.Tenant, models.Tenant.id == models.User.tenant_id)
        .filter(
            models.Tenant.id == restaurant.tenant_id,
            models.Notification.severity.in_(["critical", "high"]),
            models.Notification.acknowledged_at.is_(None),
            models.Notification.created_at <= now - timedelta(days=2),
        ).count()
    )
    if unacked:
        score -= min(20, 5 * unacked)
        reasons.append(f"{unacked} critical/high alert(s) unacknowledged for 2+ days")

    score = max(0, score)
    return {
        "restaurant_id": rid,
        "name": restaurant.name,
        "score": score,
        "status": _status(score),
        "reasons": reasons,
        "orders_7d": orders_7d,
        "orders_prev_7d": orders_prev,
        "last_order_at": last_order_at.isoformat() if last_order_at else None,
    }


def platform_scorecard(db: Session, now=None) -> dict:
    now = now or utcnow()
    rows = [restaurant_health(db, r, now) for r in db.query(models.Restaurant).all()]
    rows.sort(key=lambda r: r["score"])
    red = sum(1 for r in rows if r["status"] == "red")
    share = (red / len(rows)) if rows else 0.0
    return {
        "generated_at": now.isoformat(),
        "restaurants": rows,
        "summary": {
            "total": len(rows),
            "red": red,
            "amber": sum(1 for r in rows if r["status"] == "amber"),
            "green": sum(1 for r in rows if r["status"] == "green"),
            "needs_human_call": share > CALL_WHEN_RED_SHARE_ABOVE or (len(rows) == 1 and red == 1),
        },
    }
