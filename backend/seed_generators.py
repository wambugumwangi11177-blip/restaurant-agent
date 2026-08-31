"""
Reusable demo-data generators.

Extracted from populate_production.py so the initial seed and the demo
re-seed script (scripts/reseed_demo.py) produce identical distributions.

Day-zero realism is built in when include_today=True:
- Orders: times clamp to hours that have actually elapsed — no order is
  fabricated for a future hour of today, and completions never land in
  the future.
- Reservations: same-day slots whose time hasn't come yet stay CONFIRMED
  instead of being randomly marked COMPLETED/NO_SHOW/CANCELLED.
- Stock usage: scaled to the fraction of the day elapsed.

A dashboard reading "now" must see a coherent picture, not a full day's
worth of data at 09:00.
"""

import random
from datetime import datetime, timedelta, time

from models import (
    Order, OrderItem, PrepTime, Reservation, StockMovement,
    OrderStatus, OrderType, ReservationStatus, StockMovementType,
)
from time_utils import utcnow


def _orders_for_day(weekday: int) -> int:
    if weekday >= 5:  # Saturday/Sunday
        return random.randint(25, 45)
    if weekday == 4:  # Friday
        return random.randint(20, 35)
    return random.randint(10, 25)


def generate_orders(db, restaurant_id, menu_items, days=30, include_today=True):
    """Seed `days` days of orders (plus today when include_today). Returns count."""
    today = utcnow()
    total_orders = 0
    offsets = range(days, -1, -1) if include_today else range(days, 0, -1)

    for day_offset in offsets:
        order_date = today - timedelta(days=day_offset)
        num_orders = _orders_for_day(order_date.weekday())

        for _ in range(num_orders):
            if random.random() < 0.4:
                hour = random.randint(11, 14)
            else:
                hour = random.randint(18, 22)
            order_time = order_date.replace(hour=hour, minute=random.randint(0, 59), second=0)

            if day_offset == 0 and order_time > today:
                continue  # that hour hasn't happened yet today

            order_type = random.choices(
                [OrderType.DINE_IN, OrderType.TAKEOUT, OrderType.DELIVERY],
                weights=[60, 25, 15],
            )[0]

            num_items = random.randint(1, 5)
            selected = random.sample(menu_items, min(num_items, len(menu_items)))
            total = 0

            order = Order(
                restaurant_id=restaurant_id,
                status=random.choices(
                    [OrderStatus.SERVED, OrderStatus.SERVED, OrderStatus.SERVED, OrderStatus.CANCELLED],
                    weights=[70, 15, 10, 5],
                )[0],
                order_type=order_type,
                table_number=random.randint(1, 12) if order_type == OrderType.DINE_IN else None,
                customer_name=f"Customer_{random.randint(100, 999)}",
                total=0,
                created_at=order_time,
                completed_at=order_time + timedelta(minutes=random.randint(15, 45)) if order_type != OrderType.DELIVERY else None,
            )
            if order.completed_at and order.completed_at > today:
                order.completed_at = today
            db.add(order)
            db.flush()

            for item in selected:
                qty = random.randint(1, 3)
                oi = OrderItem(
                    order_id=order.id,
                    menu_item_id=item.id,
                    quantity=qty,
                    unit_price=item.price,
                )
                db.add(oi)
                db.flush()
                total += qty * item.price

                actual_prep = item.avg_prep_minutes + random.uniform(-3, 5)
                db.add(PrepTime(
                    order_item_id=oi.id,
                    station=item.prep_station,
                    started_at=order_time,
                    completed_at=min(order_time + timedelta(minutes=actual_prep), today),
                    actual_minutes=round(actual_prep, 1),
                ))

            order.total = total
            total_orders += 1

    return total_orders


def generate_stock_movements(db, inv_items, days=30, include_today=True):
    """Daily usage OUT movements (+ Monday restocks) for each inventory item."""
    today = utcnow()
    offsets = range(days, -1, -1) if include_today else range(days, 0, -1)

    for day_offset in offsets:
        move_date = today - timedelta(days=day_offset)
        for inv in inv_items:
            daily_use = random.uniform(0.5, 3.0)
            if day_offset == 0:
                daily_use = max(0.1, daily_use * today.hour / 24)
            db.add(StockMovement(
                inventory_item_id=inv.id,
                movement_type=StockMovementType.OUT,
                quantity=round(daily_use, 1),
                reason="sale",
                created_at=move_date,
            ))
            if move_date.weekday() == 0:
                db.add(StockMovement(
                    inventory_item_id=inv.id,
                    movement_type=StockMovementType.IN,
                    quantity=round(random.uniform(10, 25), 1),
                    reason="purchase",
                    created_at=move_date,
                ))


def generate_reservations(db, restaurant_id, tables, days=30, include_today=True):
    """Seed `days` days of reservations (plus today when include_today)."""
    today = utcnow()
    offsets = range(days, -1, -1) if include_today else range(days, 0, -1)

    for day_offset in offsets:
        res_date = (today - timedelta(days=day_offset)).date()
        num_res = random.randint(3, 10)

        for _ in range(num_res):
            res_time = time(hour=random.choice([12, 13, 18, 19, 20]), minute=random.choice([0, 30]))
            table = random.choice(tables)

            if day_offset == 0 and datetime.combine(res_date, res_time) > today:
                status = ReservationStatus.CONFIRMED
            else:
                status = random.choices(
                    [ReservationStatus.COMPLETED, ReservationStatus.NO_SHOW, ReservationStatus.CANCELLED],
                    weights=[75, 15, 10],
                )[0]

            db.add(Reservation(
                restaurant_id=restaurant_id,
                table_id=table.id,
                customer_name=f"Guest_{random.randint(100, 999)}",
                customer_phone=f"+2547{random.randint(10000000, 99999999)}",
                party_size=random.randint(2, 8),
                reservation_date=res_date,
                reservation_time=res_time,
                duration_minutes=random.choice([60, 90, 120]),
                status=status,
                deposit_paid=random.random() < 0.3,
            ))
