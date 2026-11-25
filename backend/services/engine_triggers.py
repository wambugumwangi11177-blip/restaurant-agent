"""
Run deterministic engines after normal restaurant entry points commit.

POS sales, deliveries, handovers, price confirms, and day close should refresh
stock views, drafts, variance signals, and dish costs without a manual cron tap.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

import models

logger = logging.getLogger("services.engine_triggers")


def after_pos_sale(db: Session, restaurant_id: int, order_id: int, *, inserted: bool) -> None:
    """QuickSell / POS mirror mapped a paid sale to an order."""
    from events.bus import emit_async, EventType

    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id, models.Order.restaurant_id == restaurant_id)
        .first()
    )
    if order is None:
        return
    payload = {
        "restaurant_id": restaurant_id,
        "order_id": order.id,
        "total": order.total,
        "is_paid": bool(order.is_paid),
    }
    if inserted:
        emit_async(EventType.ORDER_CREATED, payload)
    emit_async(EventType.ORDER_PAID, payload)
    after_inventory_touch(db, restaurant_id)
    maybe_variance_alert(db, restaurant_id)


def after_inventory_touch(db: Session, restaurant_id: int) -> None:
    """Stock qty or cost changed — refresh par/ROP drafts and low-stock signals."""
    maybe_draft_reorders(db, restaurant_id)
    _emit_low_stock_events(db, restaurant_id)


def after_delivery_received(db: Session, restaurant_id: int, receipt_id: int) -> None:
    from events.bus import emit_async, EventType

    emit_async(
        EventType.STOCK_RECEIVED,
        {"restaurant_id": restaurant_id, "receipt_id": receipt_id},
    )
    after_inventory_touch(db, restaurant_id)


def after_handover(db: Session, restaurant_id: int, handover_id: int) -> None:
    del handover_id
    after_inventory_touch(db, restaurant_id)
    maybe_variance_alert(db, restaurant_id)


def after_prices_confirmed(db: Session, restaurant_id: int) -> None:
    from services.dish_cost import sync_menu_cost_prices

    sync_menu_cost_prices(db, restaurant_id)
    db.commit()


def after_day_close(db: Session, restaurant_id: int) -> None:
    maybe_variance_alert(db, restaurant_id)
    after_inventory_touch(db, restaurant_id)


def after_restock_decision(db: Session, restaurant_id: int, po_id: int, *, approved: bool) -> None:
    if not approved:
        return
    from events.bus import emit_async, EventType

    po = (
        db.query(models.PurchaseOrder)
        .filter(models.PurchaseOrder.id == po_id, models.PurchaseOrder.restaurant_id == restaurant_id)
        .first()
    )
    if po is None:
        return
    item = (
        db.query(models.InventoryItem).filter(models.InventoryItem.id == po.inventory_item_id).first()
    )
    emit_async(
        EventType.PURCHASE_ORDER_APPROVED,
        {
            "restaurant_id": restaurant_id,
            "po_id": po.id,
            "item_name": item.item_name if item else "",
            "quantity": po.quantity_ordered,
            "unit": po.unit or "",
        },
    )
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if restaurant:
        from services.approval_workflow import ensure_reminder_row
        from services.restock_workflow import placement_actor_role

        ensure_reminder_row(
            db,
            restaurant_id,
            "restock_place",
            po.id,
            po.requested_by_user_id,
            actor_role=placement_actor_role(restaurant),
        )


def maybe_draft_reorders(db: Session, restaurant_id: int) -> int:
    """Draft PENDING POs for items at reorder point. Returns count drafted."""
    from ai.reorder import draft_purchase_order, find_reorder_candidates
    from services.reorder_points import sync_restaurant

    try:
        sync_restaurant(db, restaurant_id)
        db.flush()
        drafted = 0
        for candidate in find_reorder_candidates(db, restaurant_id):
            draft_purchase_order(db, restaurant_id, candidate, commit=True)
            drafted += 1
        return drafted
    except Exception:
        logger.exception("[engine_triggers] reorder draft failed restaurant_id=%s", restaurant_id)
        return 0


def maybe_variance_alert(db: Session, restaurant_id: int) -> bool:
    """Emit STOCK_VARIANCE_FLAGGED when custody math finds flagged items (24h window)."""
    from ai.stock_custody import flagged_items
    from events.bus import emit_async, EventType

    try:
        items = flagged_items(db, restaurant_id, hours=24)
        if not items:
            return False
        emit_async(
            EventType.STOCK_VARIANCE_FLAGGED,
            {
                "restaurant_id": restaurant_id,
                "items": [
                    {
                        "item_name": i.item_name,
                        "variance_pct": i.variance_pct,
                        "theoretical": i.theoretical_usage,
                        "actual": i.actual_usage,
                    }
                    for i in items
                ],
            },
        )
        return True
    except Exception:
        logger.exception("[engine_triggers] variance check failed restaurant_id=%s", restaurant_id)
        return False


def _emit_low_stock_events(db: Session, restaurant_id: int) -> None:
    from events.bus import emit_async, EventType

    items = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.restaurant_id == restaurant_id)
        .all()
    )
    for item in items:
        threshold = float(item.low_stock_threshold or 0)
        qty = float(item.quantity or 0)
        if threshold <= 0 or qty > threshold:
            continue
        level = EventType.STOCK_CRITICAL if qty <= 0 else EventType.STOCK_LOW
        emit_async(
            level,
            {
                "restaurant_id": restaurant_id,
                "inventory_item_id": item.id,
                "item_name": item.item_name,
                "quantity": qty,
                "unit": item.unit,
                "threshold": threshold,
            },
        )