"""
backend/ai/order_stock.py
────────────────────────────
Order-triggered ingredient deduction (directive 017).

The missing link identified while planning stock automation: marking an
order SERVED never touched inventory, and MenuIngredient (the recipe model)
had no way to get populated until routers/menu.py's ingredient endpoints
existed. This module is what actually spends the recipe data once a
restaurant has entered it.

Deliberately fires at order CREATION, not completion — the owner's call
(2026-07-15): the customer is committed to buying it the moment it's rung
up, so that's the moment stock should reflect it. The corollary is
reverse_ingredients_for_order, which undoes exactly that if the order is
cancelled before the food was ever made.

Negative stock is allowed (directive 007's existing policy: "Allow it
(theoretical debt) but flag heavily") — this module never blocks an order
for insufficient stock, it just deducts, possibly into negative, and the
existing low-stock alert pipeline picks it up from there.
"""

from sqlalchemy.orm import Session

import models


def deduct_ingredients_for_order(db: Session, order: models.Order, performed_by_user_id: int) -> list[str]:
    """
    Deduct recipe ingredients for every item on `order`. Returns the names of
    any menu items with no recipe defined, so the caller can surface "this
    dish has no recipe, stock won't track it" instead of silently doing
    nothing — matches this codebase's "don't guess, surface it" convention
    (same posture as the unassigned-staff-role screen).

    Does not commit — caller controls the transaction boundary alongside the
    order write itself.
    """
    missing_recipes: list[str] = []

    for oi in order.items:
        ingredients = db.query(models.MenuIngredient).filter(
            models.MenuIngredient.menu_item_id == oi.menu_item_id
        ).all()
        if not ingredients:
            menu_item = db.query(models.MenuItem).filter(models.MenuItem.id == oi.menu_item_id).first()
            missing_recipes.append(menu_item.name if menu_item else f"item #{oi.menu_item_id}")
            continue

        for ingredient in ingredients:
            qty = ingredient.quantity_per_serving * oi.quantity
            item = db.query(models.InventoryItem).filter(
                models.InventoryItem.id == ingredient.inventory_item_id
            ).first()
            if not item:
                continue   # Recipe references a since-deleted inventory item — nothing to deduct from.

            item.quantity -= qty
            db.add(models.StockMovement(
                inventory_item_id=item.id,
                movement_type=models.StockMovementType.OUT,
                quantity=qty,
                reason=f"Order #{order.id}",
                performed_by_user_id=performed_by_user_id,
            ))

            if item.quantity <= 0:
                _autohide_menu_items_for_depleted_ingredient(db, order.restaurant_id, item.id)

    return missing_recipes


def _autohide_menu_items_for_depleted_ingredient(db: Session, restaurant_id: int, inventory_item_id: int) -> None:
    """
    Owner's operational walkthrough (2026-07-19): "if stock is zero on
    something and the supplier hasn't brought [more], it's pulled from the
    menu and they tell the kitchen and the POS and the waiters." The
    traversal that knows which dishes are affected already existed
    (executive.py's _get_affected_menu_items, used only to compose an
    owner WhatsApp alert) — this is the same traversal, now also used to
    act. Only is_critical links 86 the dish; a non-critical ingredient
    (garnish, optional topping) running out doesn't take the whole item
    off the menu. Deliberately one-directional, same posture as
    MENU_ITEM_UNAVAILABLE generally — restocking doesn't auto-restore
    availability, a human confirms the dish is actually ready to sell
    again.
    """
    links = db.query(models.MenuIngredient).filter(
        models.MenuIngredient.inventory_item_id == inventory_item_id,
        models.MenuIngredient.is_critical.is_(True),
    ).all()
    if not links:
        return

    for link in links:
        menu_item = db.query(models.MenuItem).filter(
            models.MenuItem.id == link.menu_item_id,
            models.MenuItem.restaurant_id == restaurant_id,
            models.MenuItem.is_available.is_(True),
        ).first()
        if not menu_item:
            continue

        menu_item.is_available = False

        from events.bus import emit_async, EventType
        emit_async(EventType.MENU_ITEM_UNAVAILABLE, {
            "restaurant_id": restaurant_id,
            "item_name": menu_item.name,
            "reason": "stock_depleted",
        })


def reverse_ingredients_for_order(db: Session, order: models.Order, performed_by_user_id: int) -> None:
    """
    Credit back everything deduct_ingredients_for_order took for this order.
    Only call this when an order is cancelled BEFORE it was ever marked
    SERVED (routers/orders.py enforces this) — the food was never made, so
    the stock should never have left. An order cancelled after SERVED must
    NOT be reversed here: the ingredients were physically used regardless of
    what happened to the bill afterward.

    Does not commit — same convention as deduct_ingredients_for_order.
    """
    for oi in order.items:
        ingredients = db.query(models.MenuIngredient).filter(
            models.MenuIngredient.menu_item_id == oi.menu_item_id
        ).all()
        for ingredient in ingredients:
            qty = ingredient.quantity_per_serving * oi.quantity
            item = db.query(models.InventoryItem).filter(
                models.InventoryItem.id == ingredient.inventory_item_id
            ).first()
            if not item:
                continue

            item.quantity += qty
            db.add(models.StockMovement(
                inventory_item_id=item.id,
                movement_type=models.StockMovementType.IN,
                quantity=qty,
                reason=f"Order #{order.id} cancelled before serving — stock returned",
                performed_by_user_id=performed_by_user_id,
            ))
