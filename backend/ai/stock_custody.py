"""
backend/ai/stock_custody.py
─────────────────────────────
Variance computation for the stock chain-of-custody workstream
(directives/016_stock_custody_risk_and_staff_comms.md).

Theoretical usage: what the recipe data (MenuIngredient) says should have
been consumed, driven off what actually sold (OrderItem). Actual usage: what
was actually recorded moving out of inventory (StockMovement OUT). A gap
between the two beyond a small tolerance is the classic theft/shrinkage
signal — not every gap (spoilage, portion variance, unmeasured garnish use
are all real and not theft), which is why there's a threshold, not a
zero-tolerance flag.

Deliberately pure functions over a Session — no HTTP, no Twilio, no
scheduler — so the math is unit-testable without spinning up the app. Callers
(routers/stock_custody.py for the on-demand report, main.py's scheduled job
for the daily alert) both go through compute_variance_report.
"""

from dataclasses import dataclass
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from time_utils import utcnow

# 3%, the conservative end of the 2-3% industry-standard range for
# theoretical-vs-actual usage variance (cited in the stock-loss-prevention
# skill / directive 016) — below this, it's noise (spoilage, portion
# variance), not a signal worth a manager's attention.
VARIANCE_THRESHOLD = 0.03


@dataclass
class ItemVariance:
    inventory_item_id: int
    item_name: str
    unit: str
    theoretical_usage: float
    actual_usage: float
    variance_pct: float | None   # None when theoretical_usage is 0 (undefined, not zero)
    flagged: bool


def _theoretical_usage_by_item(db: Session, restaurant_id: int, since) -> dict[int, float]:
    """
    Sum(OrderItem.quantity * MenuIngredient.quantity_per_serving), grouped by
    inventory_item_id, for orders placed since `since`. Cancelled orders are
    excluded — a cancelled order never actually consumed ingredients.
    """
    rows = (
        db.query(
            models.MenuIngredient.inventory_item_id,
            func.sum(models.OrderItem.quantity * models.MenuIngredient.quantity_per_serving),
        )
        .join(models.OrderItem, models.OrderItem.menu_item_id == models.MenuIngredient.menu_item_id)
        .join(models.Order, models.Order.id == models.OrderItem.order_id)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.created_at >= since,
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .group_by(models.MenuIngredient.inventory_item_id)
        .all()
    )
    return {item_id: float(total or 0) for item_id, total in rows}


def _actual_usage_by_item(db: Session, restaurant_id: int, since) -> dict[int, float]:
    """Sum(StockMovement.quantity) for OUT movements on this restaurant's
    inventory since `since`, grouped by inventory_item_id."""
    rows = (
        db.query(
            models.StockMovement.inventory_item_id,
            func.sum(models.StockMovement.quantity),
        )
        .join(models.InventoryItem, models.InventoryItem.id == models.StockMovement.inventory_item_id)
        .filter(
            models.InventoryItem.restaurant_id == restaurant_id,
            models.StockMovement.movement_type == models.StockMovementType.OUT,
            models.StockMovement.created_at >= since,
        )
        .group_by(models.StockMovement.inventory_item_id)
        .all()
    )
    return {item_id: float(total or 0) for item_id, total in rows}


def compute_variance_report(
    db: Session, restaurant_id: int, hours: int = 24
) -> list[ItemVariance]:
    """
    Theoretical vs. actual usage per inventory item over the trailing `hours`
    window (default 24h — one day/shift's worth, matching the "alert on the
    report, not on every movement" philosophy). Items with zero theoretical
    usage are skipped, not flagged with a nonsensical infinite variance —
    an item nobody's recipe uses but that still moved stock isn't a variance
    question, it's a data-quality one (untracked recipe, or wrong item).
    """
    since = utcnow() - timedelta(hours=hours)

    theoretical = _theoretical_usage_by_item(db, restaurant_id, since)
    actual = _actual_usage_by_item(db, restaurant_id, since)

    item_ids = set(theoretical) | set(actual)
    if not item_ids:
        return []

    items_by_id = {
        i.id: i
        for i in db.query(models.InventoryItem).filter(
            models.InventoryItem.id.in_(item_ids),
            models.InventoryItem.restaurant_id == restaurant_id,
        ).all()
    }

    results: list[ItemVariance] = []
    for item_id in item_ids:
        item = items_by_id.get(item_id)
        if item is None:
            continue   # Stale reference (deleted item) — nothing to report on.

        theo = theoretical.get(item_id, 0.0)
        act = actual.get(item_id, 0.0)

        if theo <= 0:
            # No recipe-driven expectation for this item in the window —
            # variance is undefined, not zero. Skip rather than guess.
            variance_pct = None
            flagged = False
        else:
            variance_pct = abs(act - theo) / theo
            flagged = variance_pct > VARIANCE_THRESHOLD

        results.append(ItemVariance(
            inventory_item_id=item_id,
            item_name=item.item_name,
            unit=item.unit,
            theoretical_usage=theo,
            actual_usage=act,
            variance_pct=variance_pct,
            flagged=flagged,
        ))

    return results


def flagged_items(db: Session, restaurant_id: int, hours: int = 24) -> list[ItemVariance]:
    return [r for r in compute_variance_report(db, restaurant_id, hours) if r.flagged]


class TransferConfirmError(Exception):
    """Raised for any confirm precondition failure — callers (the HTTP route,
    the inbound WhatsApp/SMS handler) each translate this into their own error
    surface (HTTPException vs a plain-text reply)."""


def confirm_transfer(
    db: Session,
    transfer_id: int,
    restaurant_id: int,
    confirming_user_id: int,
    confirmed_quantity: float,
    notes: str = "",
) -> models.StockTransfer:
    """
    Shared confirm logic for both routers/stock_custody.py's HTTP endpoint and
    the inbound staff Twilio command (routers/webhooks.py via
    ai/whatsapp/brain.py). Single implementation deliberately — this codebase
    has already hit the "two code paths both notify for the same thing" bug
    once (see ai/whatsapp/brain.run_stock_check's docstring); a transfer
    confirmed via WhatsApp must behave identically to one confirmed via the
    dashboard, including writing the StockMovement pair and emitting
    STOCK_TRANSFER_DISCREPANCY exactly once on a mismatch.
    """
    transfer = db.query(models.StockTransfer).filter(
        models.StockTransfer.id == transfer_id,
        models.StockTransfer.restaurant_id == restaurant_id,
    ).first()
    if not transfer:
        raise TransferConfirmError("Transfer not found")
    if transfer.status != models.StockTransferStatus.PENDING:
        raise TransferConfirmError(f"Transfer already {transfer.status.value}")
    if confirmed_quantity < 0:
        raise TransferConfirmError("confirmed_quantity cannot be negative")

    transfer.confirmed_by_user_id = confirming_user_id
    transfer.confirmed_at = utcnow()
    transfer.confirmed_quantity = confirmed_quantity
    if notes:
        transfer.notes = f"{transfer.notes}\n[confirm] {notes}".strip()

    mismatch = abs(confirmed_quantity - transfer.quantity) > 1e-9

    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == transfer.inventory_item_id
    ).first()

    if mismatch:
        transfer.status = models.StockTransferStatus.DISPUTED
    else:
        transfer.status = models.StockTransferStatus.CONFIRMED
        db.add(models.StockMovement(
            inventory_item_id=item.id,
            movement_type=models.StockMovementType.OUT,
            quantity=transfer.quantity,
            reason=f"Transfer to {transfer.to_location}",
            performed_by_user_id=transfer.initiated_by_user_id,
        ))
        db.add(models.StockMovement(
            inventory_item_id=item.id,
            movement_type=models.StockMovementType.IN,
            quantity=transfer.confirmed_quantity,
            reason=f"Transfer received from {transfer.from_location}",
            performed_by_user_id=confirming_user_id,
        ))

    db.commit()
    db.refresh(transfer)

    from ai.evaluation.tracker import write_audit_log
    confirming_user = db.query(models.User).filter(models.User.id == confirming_user_id).first()
    write_audit_log(
        db, restaurant_id,
        "stock_transfer_disputed" if mismatch else "stock_transfer_confirmed",
        "stock_custody",
        entity_type="stock_transfer", entity_id=transfer.id,
        before={"declared_quantity": transfer.quantity},
        after={"confirmed_quantity": transfer.confirmed_quantity},
        reasoning=(
            f"Transfer #{transfer.id} of {item.item_name if item else transfer.inventory_item_id}: "
            f"declared {transfer.quantity}{transfer.unit}, confirmed {transfer.confirmed_quantity}{transfer.unit}."
        ),
        approved_by=confirming_user.email if confirming_user else "system",
    )

    if mismatch:
        from events.bus import emit_async, EventType
        emit_async(EventType.STOCK_TRANSFER_DISCREPANCY, {
            "restaurant_id": restaurant_id,
            "transfer_id": transfer.id,
            "item_name": item.item_name if item else "Unknown item",
            "declared_quantity": transfer.quantity,
            "confirmed_quantity": transfer.confirmed_quantity,
            "unit": transfer.unit,
        })

    return transfer


class TransferRequestError(Exception):
    """Precondition failures for the kitchen-initiated ("pull") requisition
    flow — request/fulfill, mirroring TransferConfirmError's role for
    confirm. Same reasoning: shared between the HTTP route and the inbound
    Twilio command, one implementation, two callers."""


def request_transfer(
    db: Session,
    restaurant_id: int,
    inventory_item_id: int,
    requested_by_user_id: int,
    from_location: str = "store",
    to_location: str = "kitchen",
    notes: str = "",
) -> models.StockTransfer:
    """
    Kitchen asks for an ingredient — the "pull" starting point (directive
    017). No quantity yet: the kitchen is asking, not declaring. A
    storekeeper commits a real quantity later via fulfill_transfer.
    """
    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == inventory_item_id,
        models.InventoryItem.restaurant_id == restaurant_id,
    ).first()
    if not item:
        raise TransferRequestError("Inventory item not found")

    transfer = models.StockTransfer(
        restaurant_id=restaurant_id,
        inventory_item_id=item.id,
        unit=item.unit,
        from_location=from_location,
        to_location=to_location,
        status=models.StockTransferStatus.REQUESTED,
        requested_by_user_id=requested_by_user_id,
        requested_at=utcnow(),
        notes=notes,
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)

    # Unlike confirm_transfer/submit_count above, this fires on every request
    # (not just an exception) — someone has to learn a request exists before
    # they can act on it. See EventType.STOCK_TRANSFER_REQUESTED's docstring
    # in events/bus.py for why that's not the same alert-fatigue risk.
    from events.bus import emit_async, EventType
    emit_async(EventType.STOCK_TRANSFER_REQUESTED, {
        "restaurant_id": restaurant_id,
        "transfer_id": transfer.id,
        "item_name": item.item_name,
        "unit": transfer.unit,
        "from_location": from_location,
        "to_location": to_location,
    })

    return transfer


def fulfill_transfer(
    db: Session,
    transfer_id: int,
    restaurant_id: int,
    fulfilled_by_user_id: int,
    quantity: float,
    notes: str = "",
) -> models.StockTransfer:
    """
    Storekeeper commits a quantity against a REQUESTED transfer, moving it to
    PENDING — the same state a push-initiated transfer starts in, so
    confirm_transfer works identically for both regardless of which way the
    transfer originated.
    """
    transfer = db.query(models.StockTransfer).filter(
        models.StockTransfer.id == transfer_id,
        models.StockTransfer.restaurant_id == restaurant_id,
    ).first()
    if not transfer:
        raise TransferRequestError("Transfer not found")
    if transfer.status != models.StockTransferStatus.REQUESTED:
        raise TransferRequestError(f"Transfer is {transfer.status.value}, not awaiting fulfilment")
    if quantity <= 0:
        raise TransferRequestError("quantity must be positive")

    transfer.quantity = quantity
    transfer.initiated_by_user_id = fulfilled_by_user_id
    transfer.initiated_at = utcnow()
    transfer.status = models.StockTransferStatus.PENDING
    if notes:
        transfer.notes = f"{transfer.notes}\n[fulfil] {notes}".strip()

    db.commit()
    db.refresh(transfer)

    # Tell the requester (and whoever else is watching the log) it's ready to
    # collect — same "fires on every happy-path step" reasoning as
    # request_transfer above, not just on mismatch.
    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == transfer.inventory_item_id
    ).first()
    from events.bus import emit_async, EventType
    emit_async(EventType.STOCK_TRANSFER_FULFILLED, {
        "restaurant_id": restaurant_id,
        "transfer_id": transfer.id,
        "item_name": item.item_name if item else "Unknown item",
        "quantity": quantity,
        "unit": transfer.unit,
        "from_location": transfer.from_location,
        "to_location": transfer.to_location,
    })

    return transfer


class StockCountError(Exception):
    """Precondition failures for submitting a physical stock count."""


def submit_count(
    db: Session,
    restaurant_id: int,
    inventory_item_id: int,
    counted_by_user_id: int,
    counted_quantity: float,
    notes: str = "",
) -> models.StockCount:
    """
    Record a physical count and reconcile InventoryItem.quantity to match it
    (an ADJUST movement, same mechanism as the existing manual /adjust
    endpoint). This is the independent check described in StockCount's
    model docstring — the one number that doesn't come from the recipe math,
    which is what makes a mismatch against the system's expected quantity a
    real signal once ingredient deduction is automatic.
    """
    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == inventory_item_id,
        models.InventoryItem.restaurant_id == restaurant_id,
    ).first()
    if not item:
        raise StockCountError("Inventory item not found")
    if counted_quantity < 0:
        raise StockCountError("counted_quantity cannot be negative")

    expected = item.quantity
    delta = counted_quantity - expected

    count = models.StockCount(
        restaurant_id=restaurant_id,
        inventory_item_id=item.id,
        expected_quantity=expected,
        counted_quantity=counted_quantity,
        counted_by_user_id=counted_by_user_id,
        notes=notes,
    )
    db.add(count)

    if abs(delta) > 1e-9:
        db.add(models.StockMovement(
            inventory_item_id=item.id,
            movement_type=models.StockMovementType.ADJUST if delta >= 0 else models.StockMovementType.OUT,
            quantity=abs(delta),
            reason="Physical count reconciliation",
            performed_by_user_id=counted_by_user_id,
        ))
    item.quantity = counted_quantity

    db.commit()
    db.refresh(count)

    from ai.evaluation.tracker import write_audit_log
    write_audit_log(
        db, restaurant_id, "stock_count_recorded", "stock_custody",
        entity_type="stock_count", entity_id=count.id,
        before={"expected_quantity": expected},
        after={"counted_quantity": counted_quantity},
        reasoning=f"{item.item_name}: system expected {expected}{item.unit}, count found {counted_quantity}{item.unit}.",
    )

    # Only a real gap is worth a message — not every count (most will match
    # closely), matching the "alert on the exception" philosophy used
    # throughout this workstream. Threshold reuses VARIANCE_THRESHOLD rather
    # than inventing a second number to keep in sync.
    if expected > 0 and abs(delta) / expected > VARIANCE_THRESHOLD:
        from events.bus import emit_async, EventType
        emit_async(EventType.STOCK_COUNT_DISCREPANCY, {
            "restaurant_id": restaurant_id,
            "count_id": count.id,
            "item_name": item.item_name,
            "expected_quantity": expected,
            "counted_quantity": counted_quantity,
            "unit": item.unit,
        })

    return count
