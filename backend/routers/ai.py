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
  GET  /ai/profit                     → profit intelligence (contribution margins, leaks, drift)
  GET  /ai/supply-chain               → supplier performance + purchase order recommendations

/ai/profit and /ai/supply-chain wired 2026-07-07: ai/profit/intelligence.py and
ai/supply_chain/intelligence.py were real, complete, working modules (verified against
real production data) with zero route ever exposing them — found auditing which ai/*
modules were actually reachable vs orphaned. See
directives/013_production_readiness_roadmap.md.

Note: /ai/dashboard, /ai/menu-engineering, /ai/revenue-forecast, and
/ai/reservation-insights are NOT defined here — they're served by
routers/analytics.py (registered first in main.py, so it wins routing ties).
This file used to duplicate those 4 routes with a second, divergent
implementation that was silently unreachable dead code — removed 2026-07-07
after finding it was still being read/edited as if live.
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


def _safe_run(agent_name: str, restaurant_id: int, fn, *args, **kwargs):
    """
    Run an AI function; return error dict on failure instead of crashing.
    Emits AGENT_FAILED — subscribed to by executive.py (tracks repeated
    failures for the same agent) but nothing ever emitted it, found
    2026-07-07 auditing the event orchestration end to end.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.error(f"AI module error: {e}", exc_info=True)
        from events.bus import emit_async, EventType
        emit_async(EventType.AGENT_FAILED, {
            "agent_name": agent_name,
            "restaurant_id": restaurant_id,
            "error": str(e),
        })
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
    return _safe_run("pricing_intelligence", restaurant.id, get_pricing_intelligence, db, restaurant.id)


@router.post("/pricing/{rec_id}/approve")
async def approve_pricing_rec(
    rec_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve a pricing recommendation — updates menu item price immediately."""
    restaurant = get_or_create_restaurant(db, current_user)
    from ai.pricing.recommendations import approve_recommendation
    return approve_recommendation(db, rec_id, restaurant.id, approved_by=current_user.email)


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
    return _safe_run("labor_intelligence", restaurant.id, get_labor_intelligence, db, restaurant.id)


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

    # Bug found 2026-07-07 testing against real production data: this used
    # to import a function name (get_inventory_intelligence) that doesn't
    # exist — the real name is get_inventory_predictions. _safe_run() only
    # catches exceptions from calling the function, not from resolving the
    # import itself, so this was a hard 500 (ImportError), not a graceful
    # {"error": ...} response — nothing had ever exercised this route with a
    # real request before to catch it.
    from ai.inventory_predictor import get_inventory_predictions
    return _safe_run("inventory_predictor", restaurant.id, get_inventory_predictions, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# PROFIT INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/profit")
async def ai_profit(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Contribution margins, profit leaks, portion drift, daypart/channel profitability."""
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.profit.intelligence import get_profit_intelligence
    return _safe_run("profit_intelligence", restaurant.id, get_profit_intelligence, db, restaurant.id)


# ─────────────────────────────────────────────────────────────────────────────
# SUPPLY CHAIN INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/supply-chain")
async def ai_supply_chain(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supplier performance analysis, overdue purchase orders, reorder recommendations."""
    restaurant = get_or_create_restaurant(db, current_user)

    from ai.supply_chain.intelligence import get_supply_chain_intelligence
    return _safe_run("supply_chain_intelligence", restaurant.id, get_supply_chain_intelligence, db, restaurant.id)
