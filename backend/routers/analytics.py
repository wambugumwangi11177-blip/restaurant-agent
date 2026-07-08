"""
Analytics Router
Exposes the deterministic analytics/recommendation modules as API endpoints.
Rule-based statistics and thresholds, not LLM-backed — see
directives/012_agentic_roadmap.md's standing rule on labeling honestly.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
from ai import menu_engineer, revenue_forecaster, kds_intelligence, inventory_predictor, reservation_optimizer, ops_manager
from ai.analysis_clock import data_freshness
from routers.deps import get_restaurant_or_none

router = APIRouter(prefix="/ai", tags=["Analytics"])


def _get_restaurant_id(db: Session, user: models.User) -> int:
    """Get the restaurant ID for the current user's tenant (0 if none — read-only, no auto-create)."""
    restaurant = get_restaurant_or_none(db, user)
    return restaurant.id if restaurant else 0


def _with_freshness(db: Session, restaurant_id: int, data: dict) -> dict:
    """
    Attach a data-freshness block to any analytics payload. Every window in
    these modules is anchored to the restaurant's last real activity (see
    ai/analysis_clock.py), which means a silently-broken order feed looks
    identical to a healthy restaurant — the numbers just quietly stop moving.
    This block lets the frontend warn when it's showing stale data.
    """
    if isinstance(data, dict):
        data["freshness"] = data_freshness(db, restaurant_id)
    return data


@router.get("/dashboard")
def ai_dashboard(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """AI Operations Manager — central intelligence dashboard."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return _with_freshness(db, rid, ops_manager.get_operations_dashboard(db, rid))


@router.get("/menu-engineering")
def menu_engineering(narrate: bool = True, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """
    Menu Engineering Matrix — Star/Plowhorse/Puzzle/Dog classification.
    Numbers are deterministic; when an LLM provider is set (and narrate=true) a
    grounding-checked `narrative` block is attached — see routers/ai.py's /profit.
    """
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    data = menu_engineer.get_menu_engineering(db, rid)
    data["upsell_pairs"] = menu_engineer.get_upsell_pairs(db, rid)
    if narrate:
        from ai.reasoning import narrate as reason
        note = reason(data, "menu", restaurant_id=rid)
        if note:
            data["narrative"] = note
    return _with_freshness(db, rid, data)


@router.get("/revenue-forecast")
def revenue_forecast(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Revenue forecasting with trends and predictions."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return _with_freshness(db, rid, revenue_forecaster.get_revenue_forecast(db, rid))


@router.get("/kds-intelligence")
def kds_intel(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Kitchen Display System intelligence — prep times, bottlenecks, throughput."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return _with_freshness(db, rid, kds_intelligence.get_kds_intelligence(db, rid))


@router.get("/inventory-predictions")
def inventory_intel(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Inventory intelligence — depletion forecasts, reorder alerts, spoilage risk."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return _with_freshness(db, rid, inventory_predictor.get_inventory_predictions(db, rid))


@router.get("/reservation-insights")
def reservation_intel(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Reservation intelligence — no-show analysis, table utilization, revenue per seat."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return _with_freshness(db, rid, reservation_optimizer.get_reservation_insights(db, rid))
