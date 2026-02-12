"""
AI Analytics Router
Exposes all AI intelligence services as API endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from auth import get_current_user
import models
from ai import menu_engineer, revenue_forecaster, kds_intelligence, inventory_predictor, reservation_optimizer, ops_manager

router = APIRouter(prefix="/ai", tags=["AI Intelligence"])


def _get_restaurant_id(db: Session, user: models.User) -> int:
    """Get the restaurant ID for the current user's tenant."""
    restaurant = db.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == user.tenant_id
    ).first()
    return restaurant.id if restaurant else 0


@router.get("/dashboard")
def ai_dashboard(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """AI Operations Manager — central intelligence dashboard."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return ops_manager.get_operations_dashboard(db, rid)


@router.get("/menu-engineering")
def menu_engineering(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Menu Engineering Matrix — Star/Plowhorse/Puzzle/Dog classification."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    data = menu_engineer.get_menu_engineering(db, rid)
    data["upsell_pairs"] = menu_engineer.get_upsell_pairs(db, rid)
    return data


@router.get("/revenue-forecast")
def revenue_forecast(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Revenue forecasting with trends and predictions."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return revenue_forecaster.get_revenue_forecast(db, rid)


@router.get("/kds-intelligence")
def kds_intel(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Kitchen Display System intelligence — prep times, bottlenecks, throughput."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return kds_intelligence.get_kds_intelligence(db, rid)


@router.get("/inventory-predictions")
def inventory_intel(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Inventory intelligence — depletion forecasts, reorder alerts, spoilage risk."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return inventory_predictor.get_inventory_predictions(db, rid)


@router.get("/reservation-insights")
def reservation_intel(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Reservation intelligence — no-show analysis, table utilization, revenue per seat."""
    rid = _get_restaurant_id(db, user)
    if not rid:
        return {"error": "No restaurant found"}
    return reservation_optimizer.get_reservation_insights(db, rid)
