"""
backend/stock_ledger.py
─────────────────────────
Order-driven inventory movement — the write path that connects selling a dish to
consuming its ingredients.

Why this exists
───────────────
`MenuIngredient` (the recipe link: which inventory items a dish consumes, and how
much of each per serving) has been in the schema since the knowledge-graph work,
but until 2026-08-06 nothing wrote it and nothing read it on the order path.
Stock only ever moved through the manual `/inventory/{id}/receive` and `/adjust`
endpoints. That left every downstream number — food cost %, "4 hours of chicken
left", depletion prediction, reorder suggestions, profit leaks — resting on
counts a human remembered to type in.

This module is that missing link. It is deliberately *deterministic and
side-effect-light*: pure DB reads and writes, no LLM, no messaging. Alerting
already happens elsewhere (ai/whatsapp/brain.run_stock_check on its 2-hourly
cron, plus the STOCK_DEPLETED / STOCK_CRITICAL events).

Four decisions worth knowing about
──────────────────────────────────
1. **Consumption is recorded when the order is CREATED, not when it is served.**
   The question an owner asks inventory is "what can I still sell tonight?" A
   dish committed to a live ticket is already spoken for. Deducting at SERVED
   would mean that during a rush — exactly when the shortage alert matters most
   — twenty in-flight orders' worth of stock still reads as available.

2. **Stock is allowed to go negative, and an order is never blocked.**
   A negative quantity means the opening count was wrong, which is information.
   Refusing to sell food because the software's count disagrees with the shelf
   would be a far worse failure than a negative number on a dashboard, and it
   would teach staff to work around the system on their busiest night.

3. **Dishes with no recipe are skipped silently.** Most restaurants will map
   their expensive, theft-prone or fast-moving ingredients first and never map
   a bottled soda. A partial recipe book has to produce partial (correct)
   deduction rather than an error.

4. **Idempotence is carried in `StockMovement.reason`**, not a new column.
   Every movement this module writes is tagged `sale:order:<id>` or
   `void:order:<id>`, and both entry points check for their tag before writing.
   A retried request, a double-tapped cancel, or a webhook replay therefore
   cannot double-deduct. This avoids a migration on a table that already has
   the FK index it needs (migration 015).

Unit boundary — read before touching the cost helper
────────────────────────────────────────────────────
`InventoryItem.cost_per_unit` is a **Float in whole KES** (confirmed by
ai/roi/savings.py, which multiplies it by 100 to reach cents), while
`MenuItem.cost_price` is an **Integer in cents**. Note that a *third* field,
`PurchaseOrder.cost_per_unit`, is Integer cents — same name, different unit.
Mixing these silently produces margins wrong by 100×, which is precisely the
class of error ai/data_quality.py exists to catch after the fact.
"""

from sqlalchemy.orm import Session, joinedload

import models

# Tag prefixes written into StockMovement.reason. Kept as constants because both
# the writer and the "have I already done this?" guard depend on the exact text.
SALE_REASON_PREFIX = "sale:order:"
VOID_REASON_PREFIX = "void:order:"


def _sale_reason(order_id: int) -> str:
    return f"{SALE_REASON_PREFIX}{order_id}"


def _void_reason(order_id: int) -> str:
    return f"{VOID_REASON_PREFIX}{order_id}"


def _recipe_map(db: Session, menu_item_ids: list[int]) -> dict[int, list[models.MenuIngredient]]:
    """{menu_item_id: [MenuIngredient, ...]} for the given dishes, in one query."""
    if not menu_item_ids:
        return {}
    rows = (
        db.query(models.MenuIngredient)
        .filter(models.MenuIngredient.menu_item_id.in_(menu_item_ids))
        .all()
    )
    out: dict[int, list[models.MenuIngredient]] = {}
    for row in rows:
        out.setdefault(row.menu_item_id, []).append(row)
    return out


def _already_recorded(db: Session, reason: str) -> bool:
    return db.query(models.StockMovement.id).filter(
        models.StockMovement.reason == reason
    ).first() is not None


def consume_for_order(db: Session, order: models.Order) -> list[dict]:
    """
    Deduct every mapped ingredient this order consumes and write the matching
    StockMovement rows. Returns a summary of what moved (used by tests and
    callers that want to surface "this order took you below threshold").

    Does not commit — the caller owns the transaction, so a failure anywhere in
    order creation rolls the deduction back with it.
    """
    reason = _sale_reason(order.id)
    if _already_recorded(db, reason):
        return []

    items = order.items or []
    recipes = _recipe_map(db, [oi.menu_item_id for oi in items if oi.menu_item_id])
    if not recipes:
        return []

    # Aggregate before writing: a ticket with two dishes that both use chicken
    # should move chicken once, not twice, so the ledger reads the way an owner
    # would describe it ("this order used 0.8kg of chicken").
    totals: dict[int, float] = {}
    for oi in items:
        for link in recipes.get(oi.menu_item_id, []):
            qty = (link.quantity_per_serving or 0) * (oi.quantity or 0)
            if qty:
                totals[link.inventory_item_id] = totals.get(link.inventory_item_id, 0.0) + qty

    if not totals:
        return []

    inventory = {
        inv.id: inv
        for inv in db.query(models.InventoryItem).filter(
            models.InventoryItem.id.in_(list(totals))
        ).all()
    }

    moved = []
    for inventory_item_id, qty in totals.items():
        inv = inventory.get(inventory_item_id)
        if inv is None:
            # Ingredient deleted while a recipe still points at it. Skip rather
            # than raise: a stale recipe row must never make an order fail.
            continue
        # Deliberately unclamped — see decision 2 in the module docstring.
        inv.quantity = (inv.quantity or 0) - qty
        db.add(models.StockMovement(
            inventory_item_id=inventory_item_id,
            movement_type=models.StockMovementType.OUT,
            quantity=qty,
            reason=reason,
        ))
        moved.append({
            "inventory_item_id": inventory_item_id,
            "item_name": inv.item_name,
            "quantity": qty,
            "unit": inv.unit,
            "remaining": inv.quantity,
        })

    return moved


def restore_for_order(db: Session, order: models.Order) -> list[dict]:
    """
    Reverse a consumption when an order is cancelled. Writes compensating IN
    movements rather than deleting the original OUT rows, so the ledger keeps an
    honest history: "this was taken, then given back" is the auditable version,
    and it's what lets `_detect_portion_drift`-style analysis distinguish a void
    from a sale that never happened.

    No-ops if the order was never deducted, or was already restored.
    """
    if not _already_recorded(db, _sale_reason(order.id)):
        return []
    void_reason = _void_reason(order.id)
    if _already_recorded(db, void_reason):
        return []

    sale_movements = db.query(models.StockMovement).filter(
        models.StockMovement.reason == _sale_reason(order.id)
    ).all()
    if not sale_movements:
        return []

    inventory = {
        inv.id: inv
        for inv in db.query(models.InventoryItem).filter(
            models.InventoryItem.id.in_([m.inventory_item_id for m in sale_movements])
        ).all()
    }

    restored = []
    for movement in sale_movements:
        inv = inventory.get(movement.inventory_item_id)
        if inv is None:
            continue
        inv.quantity = (inv.quantity or 0) + (movement.quantity or 0)
        db.add(models.StockMovement(
            inventory_item_id=movement.inventory_item_id,
            movement_type=models.StockMovementType.IN,
            quantity=movement.quantity,
            reason=void_reason,
        ))
        restored.append({
            "inventory_item_id": movement.inventory_item_id,
            "item_name": inv.item_name,
            "quantity": movement.quantity,
            "remaining": inv.quantity,
        })

    return restored


def recipe_cost_cents(db: Session, menu_item_id: int) -> int | None:
    """
    What this dish costs to make, derived from its recipe:
        Σ (quantity_per_serving × ingredient cost_per_unit) → KES → cents.

    Returns None when the dish has no recipe, which callers must treat as "keep
    the hand-entered cost_price" rather than "the cost is zero". A zero would
    read as 100% margin and poison every pricing and profit number for that item.

    See the unit-boundary note in the module docstring: cost_per_unit is whole
    KES, cost_price is cents, hence the ×100.
    """
    links = (
        db.query(models.MenuIngredient)
        .options(joinedload(models.MenuIngredient.inventory_item))
        .filter(models.MenuIngredient.menu_item_id == menu_item_id)
        .all()
    )
    if not links:
        return None

    total_kes = 0.0
    for link in links:
        inv = link.inventory_item
        if inv is None:
            continue
        total_kes += (link.quantity_per_serving or 0) * (inv.cost_per_unit or 0)
    return int(round(total_kes * 100))
