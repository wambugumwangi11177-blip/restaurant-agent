"""Owner dishes: cost, price, margin from recipes."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from services.dish_cost import effective_dish_cost_cents
from services.plate_tracking import plates_report

router = APIRouter(prefix="/eleven/dishes", tags=["eleven-dishes"])


@router.get("")
async def list_dishes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    dishes = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == restaurant.id).order_by(models.MenuItem.name).all()
    plates = plates_report(db, restaurant.id)
    out = []
    for dish in dishes:
        cost_cents = effective_dish_cost_cents(db, restaurant.id, dish)
        price = int(dish.price or 0)
        margin = price - cost_cents if price else None
        margin_pct = round(100.0 * margin / price, 1) if price and margin is not None else None
        has_recipe = (
            db.query(models.MenuIngredient.id)
            .filter(models.MenuIngredient.menu_item_id == dish.id)
            .first()
            is not None
        )
        out.append(
            {
                "id": dish.id,
                "name": dish.name,
                "category": dish.category,
                "price_cents": price,
                "cost_cents": cost_cents,
                "cost_source": "recipe" if has_recipe else "manual",
                "margin_cents": margin,
                "margin_pct": margin_pct,
            }
        )
    return {"dishes": out, "plates": plates}