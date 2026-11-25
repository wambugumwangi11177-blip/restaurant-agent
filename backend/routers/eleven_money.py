"""Owner money: P&L and margin snapshot (plain outcomes, no engine names)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from ai.menu_engineer import get_menu_engineering
from ai.profit.intelligence import get_profit_intelligence
from database import get_db
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from services.dish_cost import dish_cost_map
from time_utils import utcnow
from datetime import timedelta

router = APIRouter(prefix="/eleven/money", tags=["eleven-money"])


@router.get("/pnl")
async def owner_pnl(
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    profit = get_profit_intelligence(db, restaurant.id)
    engineering = get_menu_engineering(db, restaurant.id)
    costs = dish_cost_map(db, restaurant.id)
    recipe_backed = sum(1 for cid in costs.values() if cid > 0)
    summary = profit.get("summary") or {}
    since = utcnow() - timedelta(days=30)
    revenue_cents = summary.get("revenue_cents") or summary.get("total_revenue_30d") or 0
    food_cost_cents = summary.get("food_cost_cents") or summary.get("total_food_cost_30d") or 0
    if not revenue_cents:
        revenue_cents = int(
            db.query(func.coalesce(func.sum(models.Order.total), 0))
            .filter(
                models.Order.restaurant_id == restaurant.id,
                models.Order.is_paid.is_(True),
                models.Order.status != models.OrderStatus.CANCELLED,
                models.Order.created_at >= since,
            )
            .scalar()
            or 0
        )
    bills_cents = (
        db.query(func.coalesce(func.sum(models.RunningCost.amount_cents), 0))
        .filter(
            models.RunningCost.restaurant_id == restaurant.id,
            models.RunningCost.status == "approved",
            models.RunningCost.amount_cents > 0,
        )
        .scalar()
        or 0
    )
    labor_cents = (
        db.query(func.coalesce(func.sum(models.LaborShift.labor_cost), 0))
        .filter(
            models.LaborShift.restaurant_id == restaurant.id,
            models.LaborShift.shift_date >= since.date(),
        )
        .scalar()
        or 0
    )
    gross_cents = revenue_cents - food_cost_cents
    net_cents = gross_cents - int(bills_cents) - int(labor_cents)
    margin_pct = round(100.0 * gross_cents / revenue_cents, 1) if revenue_cents else None
    return {
        "has_sales": bool(revenue_cents),
        "revenue_cents": revenue_cents,
        "food_cost_cents": food_cost_cents,
        "bills_cents": int(bills_cents),
        "labor_cents": int(labor_cents),
        "gross_margin_cents": gross_cents,
        "net_cents": net_cents,
        "margin_pct": margin_pct,
        "dishes_with_cost": recipe_backed,
        "menu_flags": (engineering.get("flags") or [])[:5],
        "message": profit.get("empty_message") or engineering.get("empty_message"),
    }