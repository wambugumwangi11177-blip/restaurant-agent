"""Shift sales attribution (ready when POS has paid orders)."""
from datetime import datetime, timedelta

import models
from services.shift_sales import shift_team_sales
from tests.test_storekeeper_foundation import _tenant
from time_utils import utcnow


def test_shift_sales_coming_without_paid_orders(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "owner@eleven.leviii")
    start = utcnow()
    end = start + timedelta(hours=8)
    out = shift_team_sales(db_session, restaurant.id, start, end)
    assert out["status"] == "coming"
    assert out["total_cents"] is None


def test_shift_sales_sums_orders_in_window(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "owner2@eleven.leviii")
    start = utcnow() - timedelta(hours=2)
    end = utcnow() + timedelta(hours=2)
    db_session.add(
        models.Order(
            restaurant_id=restaurant.id,
            is_paid=True,
            total=1500,
            created_at=start + timedelta(minutes=30),
        )
    )
    db_session.add(
        models.Order(
            restaurant_id=restaurant.id,
            is_paid=True,
            total=2500,
            created_at=end + timedelta(hours=5),
        )
    )
    db_session.commit()
    out = shift_team_sales(db_session, restaurant.id, start, end)
    assert out["status"] == "ready"
    assert out["total_cents"] == 1500
    assert out["order_count"] == 1