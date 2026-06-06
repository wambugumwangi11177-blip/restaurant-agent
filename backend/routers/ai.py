"""
backend/routers/ai.py
──────────────────────
AI Intelligence Router — exposes all AI agents via REST endpoints.

Endpoints:
  GET /ai/dashboard          → system health + quick stats + risks + opportunities
  GET /ai/pricing            → pricing intelligence (SURGE / REPRICE / STIMULATE)
  GET /ai/labor              → labor cost analytics + recommendations
  GET /ai/revenue-forecast   → 30-day trends + 7-day forward forecast
  GET /ai/menu-engineering   → menu matrix (stars, plowhorses, puzzles, dogs)
  GET /ai/inventory          → inventory health + restock predictions
  GET /ai/reservation-insights → no-show analysis + RevPASH + overbooking
"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from auth import get_current_user
import models

logger = logging.getLogger("ai.router")

router = APIRouter(prefix="/ai", tags=["ai"])


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_restaurant(db: Session, user: models.User) -> models.Restaurant:
    """Get the restaurant for the current user's tenant."""
    restaurant = (
        db.query(models.Restaurant)
        .filter(models.Restaurant.tenant_id == user.tenant_id)
        .first()
    )
    if not restaurant:
        raise HTTPException(status_code=404, detail="No restaurant found for this account")
    return restaurant


def _safe_run(fn, *args, **kwargs):
    """Run an AI function; return error dict on failure instead of crashing."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.error(f"AI module error: {e}", exc_info=True)
        return {"error": str(e), "available": False}


# ─────────────────────────────────────────────────────────────────────────────
# AI DASHBOARD — COMMAND CENTER
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def ai_dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    System health score + quick stats + active risks + opportunities.
    Aggregates data from multiple agents for the Command Center page.
    """
    restaurant = _get_restaurant(db, current_user)
    rid = restaurant.id
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Quick Stats ──────────────────────────────────────────────────────────
    orders_today = (
        db.query(func.count(models.Order.id))
        .filter(
            models.Order.restaurant_id == rid,
            models.Order.created_at >= today_start,
        )
        .scalar() or 0
    )

    revenue_today = (
        db.query(func.sum(models.Order.total))
        .filter(
            models.Order.restaurant_id == rid,
            models.Order.created_at >= today_start,
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .scalar() or 0
    )

    revenue_30d = (
        db.query(func.sum(models.Order.total))
        .filter(
            models.Order.restaurant_id == rid,
            models.Order.created_at >= thirty_days_ago,
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .scalar() or 0
    )

    total_orders_30d = (
        db.query(func.count(models.Order.id))
        .filter(
            models.Order.restaurant_id == rid,
            models.Order.created_at >= thirty_days_ago,
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .scalar() or 0
    )

    pending_orders = (
        db.query(func.count(models.Order.id))
        .filter(
            models.Order.restaurant_id == rid,
            models.Order.status.in_([models.OrderStatus.PENDING, models.OrderStatus.PREPARING]),
        )
        .scalar() or 0
    )

    # ── Inventory Alerts ──────────────────────────────────────────────────────
    low_stock_items = (
        db.query(models.InventoryItem)
        .filter(
            models.InventoryItem.restaurant_id == rid,
            models.InventoryItem.quantity <= models.InventoryItem.low_stock_threshold,
        )
        .all()
    )

    critical_stock = [i for i in low_stock_items if i.quantity <= 0]
    low_stock = [i for i in low_stock_items if i.quantity > 0]

    # ── Pricing Opportunities ─────────────────────────────────────────────────
    pending_pricing = (
        db.query(func.count(models.PricingRecommendation.id))
        .filter(
            models.PricingRecommendation.restaurant_id == rid,
            models.PricingRecommendation.status == "PENDING",
        )
        .scalar() or 0
    )

    # ── Revenue Trend (WoW) ───────────────────────────────────────────────────
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)

    rev_this_week = (
        db.query(func.sum(models.Order.total))
        .filter(
            models.Order.restaurant_id == rid,
            models.Order.created_at >= seven_days_ago,
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .scalar() or 0
    )

    rev_last_week = (
        db.query(func.sum(models.Order.total))
        .filter(
            models.Order.restaurant_id == rid,
            models.Order.created_at >= fourteen_days_ago,
            models.Order.created_at < seven_days_ago,
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .scalar() or 0
    )

    wow_growth = round(((rev_this_week - rev_last_week) / max(rev_last_week, 1)) * 100, 1) if rev_last_week else 0

    # ── Health Score Calculation ──────────────────────────────────────────────
    # Score based on: revenue trend, inventory health, pricing, order flow
    score_components = []

    # Revenue trend (weight 30%)
    revenue_score = min(100, max(0, 70 + wow_growth * 2))
    score_components.append({"category": "Revenue Trend", "score": int(revenue_score), "weight": 30,
                              "detail": f"WoW growth: {wow_growth:+.1f}%"})

    # Inventory health (weight 25%)
    total_inv = db.query(func.count(models.InventoryItem.id)).filter(
        models.InventoryItem.restaurant_id == rid
    ).scalar() or 1
    inv_score = max(0, 100 - (len(critical_stock) * 20) - (len(low_stock) * 5))
    score_components.append({"category": "Inventory Health", "score": int(inv_score), "weight": 25,
                              "detail": f"{len(critical_stock)} critical, {len(low_stock)} low-stock items"})

    # Order flow (weight 25%)
    avg_daily = total_orders_30d / 30 if total_orders_30d else 0
    order_score = min(100, int(70 + (avg_daily / max(avg_daily, 1) - 1) * 30)) if avg_daily else 50
    order_score = max(0, min(100, order_score))
    score_components.append({"category": "Order Volume", "score": order_score, "weight": 25,
                              "detail": f"{int(avg_daily)} avg orders/day over 30 days"})

    # Pricing efficiency (weight 20%)
    pricing_score = max(60, 100 - pending_pricing * 10)
    score_components.append({"category": "Pricing Efficiency", "score": int(pricing_score), "weight": 20,
                              "detail": f"{pending_pricing} pending pricing recommendations"})

    health_score = int(sum(c["score"] * c["weight"] / 100 for c in score_components))

    # ── Risks & Opportunities ─────────────────────────────────────────────────
    risks = []
    opportunities = []

    for item in critical_stock:
        risks.append({
            "severity": "CRITICAL",
            "risk": f"{item.item_name} out of stock",
            "detail": "Immediate reorder required — menu items affected",
        })

    for item in low_stock:
        risks.append({
            "severity": "HIGH",
            "risk": f"{item.item_name} low stock",
            "detail": f"Only {item.quantity} {item.unit} remaining (threshold: {item.low_stock_threshold})",
        })

    if pending_pricing > 0:
        total_opp = (
            db.query(func.sum(models.PricingRecommendation.monthly_impact_cents))
            .filter(
                models.PricingRecommendation.restaurant_id == rid,
                models.PricingRecommendation.status == "PENDING",
            )
            .scalar() or 0
        )
        opportunities.append({
            "opportunity": f"{pending_pricing} pricing recommendations pending",
            "potential": f"+KES {total_opp // 100:,}/month if approved",
            "agent": "Pricing Intelligence",
        })

    if wow_growth > 10:
        opportunities.append({
            "opportunity": "Strong revenue momentum",
            "potential": f"{wow_growth:+.1f}% week-over-week growth",
            "agent": "Revenue Intelligence",
        })

    # ── Recent AI Actions (from AgentMessage log) ─────────────────────────────
    recent_actions = []
    try:
        msgs = (
            db.query(models.AgentMessage)
            .filter(models.AgentMessage.restaurant_id == rid)
            .order_by(models.AgentMessage.created_at.desc())
            .limit(5)
            .all()
        )
        for m in msgs:
            recent_actions.append({
                "action": m.message_type or "Agent action",
                "agent": m.direction or "AI System",
                "time": m.created_at.strftime("%d %b, %H:%M") if m.created_at else "",
            })
    except Exception:
        pass

    return {
        "health_score": health_score,
        "health_breakdown": score_components,
        "quick_stats": {
            "today_orders": orders_today,
            "revenue_today": revenue_today,
            "revenue_today_kes": f"KES {revenue_today // 100:,}",
            "total_revenue_30d": revenue_30d,
            "total_revenue_30d_kes": f"KES {revenue_30d // 100:,}",
            "avg_daily_revenue_kes": f"KES {int(revenue_30d / 30) // 100:,}",
            "pending_orders": pending_orders,
            "active_alerts": len(critical_stock) + len(low_stock),
            "week_over_week_growth": wow_growth,
        },
        "risks": risks[:10],
        "opportunities": opportunities,
        "recent_ai_actions": recent_actions,
        "restaurant": {
            "id": restaurant.id,
            "name": restaurant.name,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# PRICING INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/pricing")
async def ai_pricing(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pricing intelligence: SURGE, REPRICE, STIMULATE recommendations."""
    restaurant = _get_restaurant(db, current_user)

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
    restaurant = _get_restaurant(db, current_user)
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
    restaurant = _get_restaurant(db, current_user)
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
    restaurant = _get_restaurant(db, current_user)

    from ai.labor.intelligence import get_labor_intelligence
    result = _safe_run(get_labor_intelligence, db, restaurant.id)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# REVENUE FORECAST
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/revenue-forecast")
async def ai_revenue_forecast(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """30-day revenue trends + 7-day forward forecast with confidence intervals."""
    restaurant = _get_restaurant(db, current_user)

    from ai.revenue_forecaster import get_revenue_forecast
    result = _safe_run(get_revenue_forecast, db, restaurant.id)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# MENU ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/menu-engineering")
async def ai_menu_engineering(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Menu matrix analysis: Stars, Plowhorses, Puzzles, Dogs."""
    restaurant = _get_restaurant(db, current_user)

    from ai.menu_engineer import get_menu_intelligence
    result = _safe_run(get_menu_intelligence, db, restaurant.id)
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
    restaurant = _get_restaurant(db, current_user)

    from ai.inventory_predictor import get_inventory_intelligence
    result = _safe_run(get_inventory_intelligence, db, restaurant.id)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# RESERVATION INSIGHTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/reservation-insights")
async def ai_reservation_insights(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """No-show analysis, RevPASH, overbooking recommendations."""
    restaurant = _get_restaurant(db, current_user)

    from ai.reservation_optimizer import get_reservation_insights
    result = _safe_run(get_reservation_insights, db, restaurant.id)
    return result
