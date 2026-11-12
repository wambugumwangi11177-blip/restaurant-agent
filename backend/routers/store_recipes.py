"""Recipes Jack takes in from the chefs. No prices on the way in or out."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from routers.deps import get_or_create_restaurant
from schemas import StrictModel
from staff_audit import record_entry
from time_utils import utcnow

router = APIRouter(prefix="/store/recipes", tags=["store-recipes"])

_CAN_WRITE = (
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.KITCHEN,
    models.StaffRole.MANAGER,
)


class RecipeLineIn(StrictModel):
    dish_name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="Kitchen", min_length=1, max_length=60)
    ingredient_name: str = Field(min_length=1, max_length=120)
    quantity: float = Field(gt=0, le=1000000)
    unit: str = Field(min_length=1, max_length=40)
    yield_fraction: float = Field(default=1.0, gt=0, le=1)


def _dishes(db: Session, restaurant_id: int) -> list[dict]:
    dishes = (
        db.query(models.MenuItem)
        .filter(models.MenuItem.restaurant_id == restaurant_id)
        .order_by(models.MenuItem.name.asc())
        .all()
    )
    if not dishes:
        return []
    lines = (
        db.query(models.MenuIngredient)
        .filter(models.MenuIngredient.menu_item_id.in_([dish.id for dish in dishes]))
        .all()
    )
    items = {
        item.id: item
        for item in db.query(models.InventoryItem).filter(
            models.InventoryItem.restaurant_id == restaurant_id
        ).all()
    }
    by_dish: dict[int, list] = {}
    for line in lines:
        ingredient = items.get(line.inventory_item_id)
        by_dish.setdefault(line.menu_item_id, []).append({
            "id": line.id,
            "ingredient_name": ingredient.item_name if ingredient else "",
            "quantity": line.quantity_per_serving,
            "unit": line.recipe_unit or (ingredient.unit if ingredient else ""),
            "yield_fraction": line.yield_fraction,
            "created_by_user_id": line.created_by_user_id,
            "created_at": line.created_at.isoformat() if line.created_at else None,
        })
    return [
        {
            "id": dish.id,
            "name": dish.name,
            "category": dish.category,
            "lines": by_dish.get(dish.id, []),
        }
        for dish in dishes
        if by_dish.get(dish.id)
    ]


@router.get("")
async def list_recipes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    return {"dishes": _dishes(db, restaurant.id)}


@router.post("", status_code=201)
async def save_recipe_line(
    body: RecipeLineIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    dish_name = body.dish_name.strip()
    ingredient_name = body.ingredient_name.strip()
    unit = body.unit.strip()
    dish = (
        db.query(models.MenuItem)
        .filter(
            models.MenuItem.restaurant_id == restaurant.id,
            models.MenuItem.name.ilike(dish_name),
        )
        .first()
    )
    if dish is None:
        # Price stays 0. This role never sends or sees a price.
        dish = models.MenuItem(
            restaurant_id=restaurant.id,
            name=dish_name,
            category=body.category.strip(),
            price=0,
            cost_price=0,
            description="",
            is_available=True,
        )
        db.add(dish)
        db.flush()
    ingredient = (
        db.query(models.InventoryItem)
        .filter(
            models.InventoryItem.restaurant_id == restaurant.id,
            models.InventoryItem.item_name.ilike(ingredient_name),
        )
        .first()
    )
    if ingredient is None:
        ingredient = models.InventoryItem(
            restaurant_id=restaurant.id,
            item_name=ingredient_name,
            quantity=0,
            unit=unit,
            cost_per_unit=0,
            low_stock_threshold=0,
            expiry_days=30,
        )
        db.add(ingredient)
        db.flush()
    line = (
        db.query(models.MenuIngredient)
        .filter(
            models.MenuIngredient.menu_item_id == dish.id,
            models.MenuIngredient.inventory_item_id == ingredient.id,
        )
        .first()
    )
    action = "recipe_line_updated" if line else "recipe_line_added"
    if line is None:
        line = models.MenuIngredient(
            menu_item_id=dish.id,
            inventory_item_id=ingredient.id,
            quantity_per_serving=body.quantity,
            is_critical=True,
            yield_fraction=body.yield_fraction,
            recipe_unit=unit,
            created_by_user_id=current_user.id,
            created_at=utcnow(),
        )
        db.add(line)
        db.flush()
    else:
        line.quantity_per_serving = body.quantity
        line.yield_fraction = body.yield_fraction
        line.recipe_unit = unit
        if line.created_by_user_id is None:
            line.created_by_user_id = current_user.id
            line.created_at = utcnow()
    record_entry(
        db,
        restaurant.id,
        current_user,
        action,
        "menu_ingredient",
        f"{current_user.email} saved {dish.name}: {body.quantity} {unit} {ingredient.item_name} (yield {body.yield_fraction}).",
        entity_id=line.id,
        detail={
            "dish": dish.name,
            "ingredient": ingredient.item_name,
            "quantity": body.quantity,
            "unit": unit,
            "yield_fraction": body.yield_fraction,
        },
    )
    db.commit()
    return {"dishes": _dishes(db, restaurant.id)}
