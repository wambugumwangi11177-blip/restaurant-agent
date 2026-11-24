"""Expected plates from kitchen handovers vs sold dish lines."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from services.dish_cost import effective_dish_cost_cents
from time_utils import utcnow


def pos_has_dish_lines(db: Session, restaurant_id: int) -> bool:
    return (
        db.query(models.OrderItem.id)
        .join(models.Order, models.Order.id == models.OrderItem.order_id)
        .filter(models.Order.restaurant_id == restaurant_id)
        .first()
        is not None
    )


def plates_report(db: Session, restaurant_id: int, days: int = 7) -> dict:
    if not pos_has_dish_lines(db, restaurant_id):
        return {
            "status": "waiting_pos",
            "message": "Waiting on POS dish lines",
            "dishes": [],
        }
    since = utcnow() - timedelta(days=days)
    sold = (
        db.query(
            models.MenuItem.id,
            models.MenuItem.name,
            func.sum(models.OrderItem.quantity).label("sold"),
        )
        .join(models.OrderItem, models.OrderItem.menu_item_id == models.MenuItem.id)
        .join(models.Order, models.Order.id == models.OrderItem.order_id)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.created_at >= since,
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .group_by(models.MenuItem.id, models.MenuItem.name)
        .all()
    )
    dishes = []
    for mid, name, sold_qty in sold:
        menu_item = db.query(models.MenuItem).filter(models.MenuItem.id == mid).first()
        ingredients = (
            db.query(models.MenuIngredient)
            .filter(models.MenuIngredient.menu_item_id == mid)
            .all()
        )
        if not ingredients:
            dishes.append({"dish": name, "sold": float(sold_qty or 0), "expected_handover_units": None})
            continue
        handover_qty = 0.0
        for h in (
            db.query(models.KitchenHandover)
            .filter(
                models.KitchenHandover.restaurant_id == restaurant_id,
                models.KitchenHandover.created_at >= since,
            )
            .all()
        ):
            for line in h.lines:
                if line.inventory_item_id in {i.inventory_item_id for i in ingredients}:
                    handover_qty += float(line.quantity or 0)
        per_plate = sum(float(i.quantity_per_serving or 0) for i in ingredients)
        expected = float(sold_qty or 0) * per_plate if per_plate else None
        dishes.append(
            {
                "dish": name,
                "sold": float(sold_qty or 0),
                "expected_handover_units": round(expected, 2) if expected is not None else None,
                "handover_units_recorded": round(float(handover_qty or 0), 2),
                "cost_cents": effective_dish_cost_cents(db, restaurant_id, menu_item) if menu_item else 0,
            }
        )
    return {"status": "ok", "message": None, "dishes": dishes, "days": days}