"""
backend/routers/events.py
──────────────────────────
Self-hosted product analytics (Phase 8): record feature-usage events for the
app's own users and query simple funnel/usage/retention summaries. Distinct from
routers/analytics.py (which is the RESTAURANT's business metrics) — this is about
how owners/staff use the product. No third-party analytics service.
"""

import json
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models
from time_utils import utcnow

logger = logging.getLogger("product.analytics")

router = APIRouter(prefix="/events", tags=["product-analytics"])


@router.post("/track")
async def track_event(
    body: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Record one product event for the current user. Body: {event_name, properties?}.
    Best-effort — a bad/oversized properties blob is dropped, never 500s, so
    analytics can never break a user flow.
    """
    event_name = (body or {}).get("event_name", "").strip()[:120]
    if not event_name:
        return {"tracked": False, "error": "event_name is required"}
    try:
        props = json.dumps((body or {}).get("properties", {}))[:2000]
    except (TypeError, ValueError):
        props = ""
    db.add(models.ProductEvent(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        event_name=event_name,
        properties=props,
    ))
    db.commit()
    return {"tracked": True}


@router.get("/summary")
async def events_summary(
    days: int = 30,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Usage summary for this tenant over `days`: event counts by name, total events,
    and distinct active users (a DAU/WAU-style signal). Admin-only.
    """
    days = min(max(days, 1), 365)
    since = utcnow() - timedelta(days=days)
    base = db.query(models.ProductEvent).filter(
        models.ProductEvent.tenant_id == current_user.tenant_id,
        models.ProductEvent.created_at >= since,
    )

    by_name = dict(
        db.query(models.ProductEvent.event_name, func.count(models.ProductEvent.id))
        .filter(
            models.ProductEvent.tenant_id == current_user.tenant_id,
            models.ProductEvent.created_at >= since,
        )
        .group_by(models.ProductEvent.event_name)
        .all()
    )
    active_users = base.with_entities(models.ProductEvent.user_id).distinct().count()

    return {
        "window_days": days,
        "total_events": base.count(),
        "active_users": active_users,
        "events_by_name": by_name,
    }
