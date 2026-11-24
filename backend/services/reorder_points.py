"""Reorder point = daily usage × lead time + safety stock; par = ROP + order quantity."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from time_utils import utcnow

SAFETY_DAYS = 1.0


def _daily_usage(db: Session, item_id: int, days: int = 14) -> float:
    since = utcnow() - timedelta(days=days)
    total = (
        db.query(func.coalesce(func.sum(models.StockMovement.quantity), 0.0))
        .filter(
            models.StockMovement.inventory_item_id == item_id,
            models.StockMovement.movement_type == models.StockMovementType.OUT,
            models.StockMovement.created_at >= since,
        )
        .scalar()
    )
    return float(total or 0) / max(days, 1)


def sync_item_reorder_fields(
    db: Session,
    item: models.InventoryItem,
    *,
    lead_days: float | None = None,
    order_qty: float | None = None,
) -> dict:
    """Update low_stock_threshold (ROP) and par_level on the item. Returns snapshot."""
    lead = lead_days
    if lead is None and item.default_supplier_id:
        supplier = db.query(models.Supplier).filter(models.Supplier.id == item.default_supplier_id).first()
        lead = float(supplier.avg_lead_days or 1.0) if supplier else 1.0
    lead = max(float(lead or 1.0), 0.5)
    daily = _daily_usage(db, item.id)
    if daily <= 0:
        daily = max(item.quantity / 30.0, 0.1) if (item.quantity or 0) > 0 else 0.5
    rop = daily * lead + daily * SAFETY_DAYS
    qty = order_qty if order_qty is not None else max(daily * lead * 2, rop)
    par = rop + qty
    item.low_stock_threshold = round(rop, 2)
    item.par_level = round(par, 2)
    return {
        "daily_usage": round(daily, 3),
        "lead_days": lead,
        "reorder_point": item.low_stock_threshold,
        "par_level": item.par_level,
        "order_qty": round(qty, 2),
    }


def sync_restaurant(db: Session, restaurant_id: int) -> int:
    items = (
        db.query(models.InventoryItem)
        .filter(
            models.InventoryItem.restaurant_id == restaurant_id,
            models.InventoryItem.default_supplier_id.isnot(None),
        )
        .all()
    )
    for item in items:
        sync_item_reorder_fields(db, item)
    return len(items)