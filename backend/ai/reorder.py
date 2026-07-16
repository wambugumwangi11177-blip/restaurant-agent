"""
backend/ai/reorder.py
────────────────────────
Par-level / reorder-point automation (directive 018).

Standard restaurant inventory practice (external research, cited in the
planning conversation this directive is built from): Par Level is the target
quantity to hold; Reorder Point is the level that triggers a new order;
Order Quantity = Par Level − On Hand. This module is that formula, adjusted
by the exogenous demand signals ai/simulation/signals.py already computes
for the Digital Twin (Kenyan public holidays, school-term breaks — weather
and sports are wired but no-op until their API keys are configured).

`InventoryItem.low_stock_threshold` (existing column, used by the alert
pipeline in ai/whatsapp/brain.py) doubles as the Reorder Point — it already
means "the level that should trigger action" in every place that reads it.
This module doesn't introduce a second threshold; it reuses that one and
adds `par_level` (new) as the target to restock up to.

Deliberately pure functions over a Session — no HTTP, no Twilio, no
scheduler — same posture as ai/stock_custody.py, for the same reason: the
math should be unit-testable without spinning up the app.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

import models
from time_utils import utcnow

# Purchase orders in either of these statuses are still "in flight" — don't
# draft a second one for the same item while one is already outstanding.
_OPEN_STATUSES = ("PENDING", "SENT")


@dataclass
class ReorderCandidate:
    inventory_item_id: int
    item_name: str
    unit: str
    on_hand: float
    par_level: float
    base_quantity: float        # par_level - on_hand, before demand adjustment
    demand_factor: float
    demand_reasons: list[str]
    adjusted_quantity: float    # what to actually order
    supplier_id: int
    supplier_name: str
    cost_per_unit: float        # InventoryItem's cost_per_unit (KES, not cents)


def find_reorder_candidates(db: Session, restaurant_id: int, on_date: date | None = None) -> list[ReorderCandidate]:
    """
    Items at or below their reorder point (low_stock_threshold), with both
    par_level and default_supplier_id set, and no outstanding purchase order
    already covering them. Order quantity is demand-adjusted using the same
    signal provider the Digital Twin uses, so a holiday or school-break
    raises the target before the shortage actually hits.
    """
    on_date = on_date or utcnow().date()

    from ai.simulation.signals import demand_signals
    signals = demand_signals(on_date)
    factor = signals["factor"]
    reasons = signals["reasons"]

    items = db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant_id,
        models.InventoryItem.par_level.isnot(None),
        models.InventoryItem.default_supplier_id.isnot(None),
    ).all()

    candidates: list[ReorderCandidate] = []
    for item in items:
        threshold = item.low_stock_threshold or 0
        if item.quantity > threshold:
            continue   # Not at the reorder point yet.

        already_open = db.query(models.PurchaseOrder).filter(
            models.PurchaseOrder.inventory_item_id == item.id,
            models.PurchaseOrder.status.in_(_OPEN_STATUSES),
        ).first()
        if already_open:
            continue   # Don't draft a second order while one's still in flight.

        supplier = db.query(models.Supplier).filter(
            models.Supplier.id == item.default_supplier_id,
            models.Supplier.is_active.is_(True),
        ).first()
        if not supplier:
            continue   # Default supplier missing or deactivated — nothing to draft against.

        base_quantity = max(item.par_level - item.quantity, 0.0)
        if base_quantity <= 0:
            continue

        adjusted_quantity = round(base_quantity * factor, 2)

        candidates.append(ReorderCandidate(
            inventory_item_id=item.id,
            item_name=item.item_name,
            unit=item.unit,
            on_hand=item.quantity,
            par_level=item.par_level,
            base_quantity=base_quantity,
            demand_factor=factor,
            demand_reasons=list(reasons),
            adjusted_quantity=adjusted_quantity,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            cost_per_unit=item.cost_per_unit or 0.0,
        ))

    return candidates


def draft_purchase_order(db: Session, restaurant_id: int, candidate: ReorderCandidate) -> models.PurchaseOrder:
    """
    Create a PENDING purchase order from a candidate — "PENDING" already
    means "created, not yet sent" in this model's existing status
    convention (see PurchaseOrder's docstring: PENDING -> SENT -> DELIVERED),
    so no new status value was needed for the draft state.

    cost_per_unit conversion: InventoryItem.cost_per_unit is stored in whole
    KES (see routers/inventory.py's StockReceive / the frontend's direct
    "KES {cost_per_unit}" display, no /100), but PurchaseOrder.cost_per_unit
    is documented in cents — converting here, once, rather than letting the
    mismatch leak into a silently-wrong total_cost.
    """
    cost_per_unit_cents = round(candidate.cost_per_unit * 100)
    total_cost_cents = round(cost_per_unit_cents * candidate.adjusted_quantity)

    reason_note = f" ({'; '.join(candidate.demand_reasons)})" if candidate.demand_reasons else ""
    notes = (
        f"Auto-drafted: par {candidate.par_level}{candidate.unit}, "
        f"on hand {candidate.on_hand}{candidate.unit}, "
        f"demand factor {candidate.demand_factor}{reason_note}."
    )

    po = models.PurchaseOrder(
        restaurant_id=restaurant_id,
        supplier_id=candidate.supplier_id,
        inventory_item_id=candidate.inventory_item_id,
        quantity_ordered=candidate.adjusted_quantity,
        unit=candidate.unit,
        cost_per_unit=cost_per_unit_cents,
        total_cost=total_cost_cents,
        status="PENDING",
        notes=notes,
    )
    db.add(po)
    db.commit()
    db.refresh(po)

    from events.bus import emit_async, EventType
    emit_async(EventType.PURCHASE_ORDER_CREATED, {
        "restaurant_id": restaurant_id,
        "po_id": po.id,
        "item_name": candidate.item_name,
        "quantity": candidate.adjusted_quantity,
        "unit": candidate.unit,
        "supplier_name": candidate.supplier_name,
    })

    return po


class PurchaseOrderError(Exception):
    """Precondition failures for approve/receive — shared error type so
    routers/purchase_orders.py can translate them into the right HTTP status
    without duplicating the precondition checks themselves."""


def approve_and_send(db: Session, po_id: int, restaurant_id: int, approved_by_email: str) -> models.PurchaseOrder:
    """
    PENDING -> SENT. This is the approval gate the owner asked for
    explicitly: nothing reaches a supplier without a human here. Texts the
    supplier (fallback_sms=True — a supplier isn't guaranteed to be on
    WhatsApp) with what's being ordered; the send is one-way and
    informational, not an interactive confirmation — see directive 018's
    reasoning for why a digital-confirmation supplier portal isn't assumed.
    """
    po = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.id == po_id,
        models.PurchaseOrder.restaurant_id == restaurant_id,
    ).first()
    if not po:
        raise PurchaseOrderError("Purchase order not found")
    if po.status != "PENDING":
        raise PurchaseOrderError(f"Purchase order is {po.status}, not awaiting approval")

    po.status = "SENT"
    db.commit()
    db.refresh(po)

    supplier = db.query(models.Supplier).filter(models.Supplier.id == po.supplier_id).first()
    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == po.inventory_item_id).first()

    if supplier and supplier.contact_phone:
        from ai.whatsapp import send_whatsapp_message
        msg = (
            f"Purchase order from {_restaurant_name(db, restaurant_id)}:\n"
            f"{po.quantity_ordered}{po.unit} {item.item_name if item else ''}\n"
            f"Please confirm and advise delivery timing. Thank you."
        )
        send_whatsapp_message(
            supplier.contact_phone, msg, db=db, restaurant_id=restaurant_id,
            message_type="purchase_order_sent", fallback_sms=True,
        )

    from ai.evaluation.tracker import write_audit_log
    write_audit_log(
        db, restaurant_id, "purchase_order_sent", "reorder_router",
        entity_type="purchase_order", entity_id=po.id,
        reasoning=f"PO #{po.id} approved and sent to {supplier.name if supplier else 'supplier'}: {po.quantity_ordered}{po.unit}.",
        approved_by=approved_by_email,
    )

    return po


def receive_purchase_order(
    db: Session, po_id: int, restaurant_id: int, quantity_received: float,
    received_by_user_id: int, notes: str = "",
) -> models.PurchaseOrder:
    """
    SENT -> DELIVERED (or PARTIAL if short). Writes the received quantity
    into InventoryItem.quantity via a StockMovement IN — the same "declared
    vs confirmed" mismatch pattern as stock_custody.py's transfer confirm,
    applied to the supplier leg: quantity_ordered is what was declared,
    quantity_received is the independently-counted reality. A shortfall
    doesn't block anything, it's just recorded and flagged.
    """
    po = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.id == po_id,
        models.PurchaseOrder.restaurant_id == restaurant_id,
    ).first()
    if not po:
        raise PurchaseOrderError("Purchase order not found")
    if po.status != "SENT":
        raise PurchaseOrderError(f"Purchase order is {po.status}, not awaiting receipt")
    if quantity_received < 0:
        raise PurchaseOrderError("quantity_received cannot be negative")

    po.quantity_received = quantity_received
    po.delivered_at = utcnow()
    po.status = "DELIVERED" if quantity_received >= po.quantity_ordered else "PARTIAL"
    if notes:
        po.notes = f"{po.notes}\n[received] {notes}".strip()

    item = None
    if po.inventory_item_id:
        item = db.query(models.InventoryItem).filter(models.InventoryItem.id == po.inventory_item_id).first()
        if item and quantity_received > 0:
            item.quantity += quantity_received
            db.add(models.StockMovement(
                inventory_item_id=item.id,
                movement_type=models.StockMovementType.IN,
                quantity=quantity_received,
                reason=f"Purchase order #{po.id} received",
                performed_by_user_id=received_by_user_id,
            ))

    db.commit()
    db.refresh(po)

    shortfall = po.quantity_ordered - quantity_received
    if shortfall > 0:
        from events.bus import emit_async, EventType
        emit_async(EventType.PURCHASE_ORDER_DELIVERED, {
            "restaurant_id": restaurant_id,
            "po_id": po.id,
            "item_name": item.item_name if item else "Unknown item",
            "quantity_ordered": po.quantity_ordered,
            "quantity_received": quantity_received,
            "shortfall": shortfall,
            "unit": po.unit,
        })

    return po


def _restaurant_name(db: Session, restaurant_id: int) -> str:
    r = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    return r.name if r else "your restaurant"
