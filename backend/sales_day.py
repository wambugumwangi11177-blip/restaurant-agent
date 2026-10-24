"""Trading-day sales for staff screens.

GET /api/v1/orders/ returns at most 200 rows. Summing that list drops every
order after the cap. This module counts the open Nairobi service day in the
database: paid, non-cancelled orders, the same window as Home.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from owner.states import kes
from time_utils import trading_window

_PAY = {"cash": "Cash", "mpesa": "M-Pesa", "card": "Card", "pending": "Unpaid"}
_CHANNEL = {
    "dine_in": "Dine in",
    "takeout": "Takeaway",
    "delivery": "Delivery",
    "uber_eats": "Uber Eats",
    "bolt_food": "Bolt Food",
    "glovo": "Glovo",
    "app": "App orders",
    "walk_in": "Walk in",
}


def _key(value) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _hour_label(hour: int) -> str:
    if hour == 0:
        return "12a"
    if hour < 12:
        return f"{hour}a"
    if hour == 12:
        return "12p"
    return f"{hour - 12}p"


def trading_day_sales(db: Session, restaurant_id: int, now: datetime | None = None) -> dict:
    """Paid sales for the open service day, in shillings, with the mixes the sales screen shows."""
    from time_utils import EAT_OFFSET

    from time_utils import service_caption

    start, end, day = trading_window("today", now)
    caption = service_caption(now)
    paid = (
        models.Order.restaurant_id == restaurant_id,
        models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= start,
        models.Order.created_at < end,
    )
    revenue_cents = int(db.query(func.coalesce(func.sum(models.Order.total), 0)).filter(*paid).scalar() or 0)
    order_count = int(db.query(func.count(models.Order.id)).filter(*paid).scalar() or 0)
    unpaid = int(db.query(func.count(models.Order.id)).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.is_paid.is_(False),
        models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= start,
        models.Order.created_at < end,
    ).scalar() or 0)

    pay_rows = db.query(models.Order.payment_method, func.count(models.Order.id), func.coalesce(func.sum(models.Order.total), 0)).filter(*paid).group_by(models.Order.payment_method).all()
    by_payment = []
    for method, count, total in pay_rows:
        key = _key(method) or "other"
        by_payment.append({"key": key, "label": _PAY.get(key, key), "count": int(count), "kes": kes(int(total or 0))})

    channel_rows = db.query(
        models.Order.order_type, models.Order.delivery_channel,
        func.count(models.Order.id), func.coalesce(func.sum(models.Order.total), 0),
    ).filter(*paid).group_by(models.Order.order_type, models.Order.delivery_channel).all()
    channels: dict[str, dict] = {}

    def add_channel(key: str, count: int, total: int) -> None:
        row = channels.setdefault(key, {"key": key, "label": _CHANNEL.get(key, key), "count": 0, "kes": 0.0})
        row["count"] += count
        row["kes"] = round(row["kes"] + (kes(total) or 0), 2)

    for order_type, delivery_channel, count, total in channel_rows:
        type_key = _key(order_type) or "dine_in"
        add_channel(type_key, int(count), int(total or 0))
        if type_key == "delivery":
            nested = _key(delivery_channel)
            if nested and nested != "walk_in":
                add_channel(nested, int(count), int(total or 0))

    stamps = db.query(models.Order.created_at, models.Order.total).filter(*paid).all()
    hours: dict[int, int] = defaultdict(int)
    for created_at, total in stamps:
        if created_at is None:
            continue
        hours[(created_at + EAT_OFFSET).hour] += int(total or 0)
    hourly = [{"hour": hour, "label": _hour_label(hour), "kes": kes(cents)} for hour, cents in sorted(hours.items())]

    item_rows = db.query(
        models.MenuItem.name,
        func.coalesce(func.sum(models.OrderItem.quantity), 0),
        func.coalesce(func.sum(models.OrderItem.quantity * models.OrderItem.unit_price), 0),
    ).join(models.OrderItem, models.OrderItem.menu_item_id == models.MenuItem.id).join(
        models.Order, models.Order.id == models.OrderItem.order_id,
    ).filter(*paid).group_by(models.MenuItem.id, models.MenuItem.name).order_by(
        func.sum(models.OrderItem.quantity * models.OrderItem.unit_price).desc(),
    ).limit(8).all()
    top_items = [{"name": name, "qty": int(qty or 0), "kes": kes(int(cents or 0))} for name, qty, cents in item_rows]

    revenue = kes(revenue_cents) or 0
    return {
        "window": "today",
        "window_label": caption,
        "service_day": day.isoformat(),
        "timezone": "Africa/Nairobi",
        "revenue_kes": revenue,
        "orders": order_count,
        "avg_kes": round(revenue / order_count, 2) if order_count else 0,
        "unpaid": unpaid,
        "by_payment": by_payment,
        "by_channel": list(channels.values()),
        "hourly": hourly,
        "top_items": top_items,
    }
