"""Recipe-based dish cost (KES cents). Falls back to MenuItem.cost_price when no recipe."""
from __future__ import annotations

from sqlalchemy.orm import Session

import models


def dish_cost_cents(db: Session, restaurant_id: int, menu_item_id: int) -> int | None:
    """Sum ingredient cost for one serving. None when the dish has no recipe lines."""
    lines = (
        db.query(models.MenuIngredient)
        .filter(models.MenuIngredient.menu_item_id == menu_item_id)
        .all()
    )
    if not lines:
        return None
    total = 0.0
    for line in lines:
        item = db.query(models.InventoryItem).filter(
            models.InventoryItem.id == line.inventory_item_id,
            models.InventoryItem.restaurant_id == restaurant_id,
        ).first()
        if item is None:
            continue
        unit_cost = float(item.cost_per_unit or 0)
        qty = float(line.quantity_per_serving or 0)
        yield_f = float(line.yield_fraction or 1.0)
        if yield_f <= 0:
            yield_f = 1.0
        total += unit_cost * qty / yield_f
    if total <= 0:
        return None
    return int(round(total * 100))


def effective_dish_cost_cents(db: Session, restaurant_id: int, menu_item: models.MenuItem) -> int:
    computed = dish_cost_cents(db, restaurant_id, menu_item.id)
    if computed is not None:
        return computed
    return int(menu_item.cost_price or 0)


def dish_cost_map(db: Session, restaurant_id: int) -> dict[int, int]:
    items = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == restaurant_id).all()
    return {item.id: effective_dish_cost_cents(db, restaurant_id, item) for item in items}