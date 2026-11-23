"""Attribute paid orders to a shift window (team total only; no per-waiter split)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

import models


def shift_team_sales(db: Session, restaurant_id: int, window_start: datetime, window_end: datetime) -> dict:
    """
    Sum is_paid order totals whose completed_at (else created_at) falls in the window.
    Returns status \"coming\" when the restaurant has no paid POS receipts yet.
    """
    paid = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.is_paid.is_(True),
    )
    if paid.count() == 0:
        return {"status": "coming", "total_cents": None, "order_count": 0}
    total = 0
    count = 0
    for order in paid:
        stamp = order.completed_at or order.created_at
        if stamp is None:
            continue
        if window_start <= stamp <= window_end:
            total += order.total or 0
            count += 1
    return {"status": "ready", "total_cents": total, "order_count": count}