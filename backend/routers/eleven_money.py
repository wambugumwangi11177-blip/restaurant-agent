"""Owner money: P&L and margin snapshot (plain outcomes, no engine names)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import auth
from ai.menu_engineer import get_menu_engineering
from ai.profit.intelligence import get_profit_intelligence
from database import get_db
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from services.dish_cost import dish_cost_map

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
    return {
        "has_sales": bool(summary.get("revenue_cents")),
        "revenue_cents": summary.get("revenue_cents"),
        "food_cost_cents": summary.get("food_cost_cents"),
        "margin_cents": summary.get("gross_profit_cents"),
        "margin_pct": summary.get("gross_margin_pct"),
        "dishes_with_cost": recipe_backed,
        "menu_flags": (engineering.get("flags") or [])[:5],
        "message": profit.get("empty_message") or engineering.get("empty_message"),
    }