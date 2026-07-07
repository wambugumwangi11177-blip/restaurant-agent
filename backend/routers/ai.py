"""
backend/routers/ai.py
──────────────────────
Analytics & Recommendations Router — exposes the deterministic analytics/
recommendation modules in ai/ via REST endpoints. These are rule-based
statistics and thresholds, not LLM-backed — see directives/012_agentic_roadmap.md's
standing rule on labeling AI-vs-deterministic honestly. The only LLM-backed
code in this project is ai/whatsapp/orchestrator.py (Phase 2).

Endpoints:
  GET  /ai/pricing                    → pricing intelligence (SURGE / REPRICE / STIMULATE)
  POST /ai/pricing/{rec_id}/approve   → approve a pricing recommendation
  POST /ai/pricing/{rec_id}/reject    → reject a pricing recommendation
  GET  /ai/labor                      → labor cost analytics + recommendations
  GET  /ai/inventory                  → inventory health + restock predictions

Note: /ai/dashboard, /ai/menu-engineering, /ai/revenue-forecast, and
/ai/reservation-insights are NOT defined here — they're served by
routers/analytics.py (registered first in main.py, so it wins routing ties).
This file used to duplicate those 4 routes with a second, divergent
implementation that was silently unreachable dead code — removed 2026-07-07
after finding it was still being read/edited as if live. See
directives/013_production_readiness_roadmap.md's "duplicate /ai router
routes" entry for the full story.
"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models
from routers.deps import get_or_create_restaurant

logger = logging.getLogger("ai.router")

router = APIRouter(prefix="/ai", tags=["ai"])


def _safe_run(fn, *args, **kwargs):
    """Run an AI function; return error dict on failure instead of crashing."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.error(f"AI module error: {e}", exc_info=True)
        return {"error": str(e), "available": False}


# ─────────────────────────────────────────────────────────────────────────────
# PRICING INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pricing")
async def ai_pricing(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pricing intelligence: SURGE, REPRICE, STIMULATE recommendations."""
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.pricing.recommendations import get_pricing_intelligence
    result = _safe_run(get_pricing_intelligence, db, restaurant.id)
    return result


@router.post("/pricing/{rec_id}/approve")
async def approve_pricing_rec(
    rec_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve a pricing recommendation — updates menu item price immediately."""
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.pricing.recommendations import approve_recommendation
    return approve_recommendation(db, rec_id, restaurant.id)


@router.post("/pricing/{rec_id}/reject")
async def reject_pricing_rec(
    rec_id: int,
    body: dict = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reject a pricing recommendation."""
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.pricing.recommendations import reject_recommendation
    reason = (body or {}).get("reason", "")
    return reject_recommendation(db, rec_id, restaurant.id, reason)


# ─────────────────────────────────────────────────────────────────────────────
# LABOR INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/labor")
async def ai_labor(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Labor cost analytics, overtime analysis, and staffing recommendations."""
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.labor.intelligence import get_labor_intelligence
    result = _safe_run(get_labor_intelligence, db, restaurant.id)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY PREDICTIONS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/inventory")
async def ai_inventory(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inventory health, usage velocity, ABC classification, restock predictions."""
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.inventory_predictor import get_inventory_intelligence
    result = _safe_run(get_inventory_intelligence, db, restaurant.id)
    return result
