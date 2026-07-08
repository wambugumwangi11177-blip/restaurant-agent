"""
The AI-dashboard hot path must not load a restaurant's entire order history.

Two modules were missed when every other analytics module was bounded to 30
days (fixed 2026-07-08):
  • menu_engineer         — GROUP BY over all order_items, no created_at filter
  • reservation_optimizer — `.all()` over every DINE_IN order, summed in Python

In production that's ~107k orders / 200k+ order_items materialized on every
dashboard load. These tests assert both halves of the fix: the emitted SQL
carries a date predicate, and the aggregates reflect only the recent window.

Note on the fixture: `analysis_clock.ANCHOR_SAMPLE_SIZE` is 30, so the analysis
anchor is the 30th-most-recent order — deliberately, to step over straggler
rows. A fixture with fewer than 30 recent orders would put the anchor back in
the ancient block and the window would swallow everything, so the recent block
must be at least that large.
"""

from datetime import datetime, time, timedelta

import pytest
from sqlalchemy import event

import models
from ai import menu_engineer, reservation_optimizer
from ai.analysis_clock import ANCHOR_SAMPLE_SIZE

ANCHOR = datetime(2026, 7, 1, 12, 0, 0)

RECENT_ORDERS = ANCHOR_SAMPLE_SIZE + 10   # enough to hold the anchor in-window
ANCIENT_ORDERS = 50
ANCIENT_QTY = 10                          # 500 units of long-dead popularity


def _add_order(db, days_ago: int, qty: int, unit_price: int = 1000):
    o = models.Order(
        restaurant_id=1, status=models.OrderStatus.SERVED,
        order_type=models.OrderType.DINE_IN,
        payment_method=models.PaymentMethod.CASH, is_paid=True,
        total=unit_price * qty, created_at=ANCHOR - timedelta(days=days_ago),
    )
    db.add(o)
    db.flush()
    db.add(models.OrderItem(order_id=o.id, menu_item_id=1, quantity=qty, unit_price=unit_price))


@pytest.fixture
def seeded(db_session):
    """A restaurant with a big ancient block and a smaller recent one."""
    db_session.add_all([
        models.Restaurant(id=1, tenant_id=None, name="Windowed Bistro", address="x"),
        models.MenuItem(id=1, restaurant_id=1, name="Nyama Choma", price=1000, category="main"),
    ])
    db_session.commit()

    for _ in range(ANCIENT_ORDERS):
        _add_order(db_session, days_ago=100, qty=ANCIENT_QTY)
    for _ in range(RECENT_ORDERS):
        _add_order(db_session, days_ago=2, qty=1)

    # One completed reservation inside the window, one far outside it.
    db_session.add_all([
        models.Reservation(
            restaurant_id=1, customer_name="Recent", customer_phone="1", party_size=4,
            reservation_date=(ANCHOR - timedelta(days=2)).date(), reservation_time=time(19, 0),
            status=models.ReservationStatus.COMPLETED,
        ),
        models.Reservation(
            restaurant_id=1, customer_name="Ancient", customer_phone="2", party_size=100,
            reservation_date=(ANCHOR - timedelta(days=100)).date(), reservation_time=time(19, 0),
            status=models.ReservationStatus.COMPLETED,
        ),
    ])
    db_session.commit()
    return db_session


def _captured_sql(db, fn):
    """Run `fn` and return (result, every SQL statement it emitted)."""
    statements = []

    def before_cursor_execute(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)
    return result, statements


def test_menu_engineering_counts_only_the_recent_window(seeded):
    result, statements = _captured_sql(
        seeded, lambda: menu_engineer.get_menu_engineering(seeded, 1)
    )

    item = {i["name"]: i for i in result["matrix"]}["Nyama Choma"]
    # RECENT_ORDERS units, NOT RECENT_ORDERS + 500: the ancient block is out of window.
    assert item["qty_sold"] == RECENT_ORDERS
    assert item["qty_sold"] != RECENT_ORDERS + ANCIENT_ORDERS * ANCIENT_QTY

    # ...and the exclusion happened in SQL, not in Python.
    grouped = [s for s in statements if "GROUP BY" in s.upper() and "order_items" in s]
    assert grouped, "expected a GROUP BY over order_items"
    assert all("created_at" in s for s in grouped), (
        "the menu aggregate must carry a created_at predicate:\n" + "\n\n".join(grouped)
    )


def test_reservation_revenue_is_bounded_and_aggregated_in_sql(seeded):
    result, statements = _captured_sql(
        seeded, lambda: reservation_optimizer.get_reservation_insights(seeded, 1)
    )

    impact = result["revenue_impact"]
    # Recent dine-in revenue only: RECENT_ORDERS x 1000 cents.
    assert impact["total_dine_in_revenue"] == RECENT_ORDERS * 1000

    # The rate divides windowed revenue by windowed COVERS (orders x avg party
    # size), never by the all-time reserved-guest count. Both the numerator and
    # the denominator are drawn from the same window; mixing them would have
    # collapsed the rate — and the three money estimates derived from it — by ~26x.
    # Window holds RECENT_ORDERS orders and one 4-top: covers = 40 x 4 = 160.
    assert impact["dine_in_orders"] == RECENT_ORDERS
    assert impact["avg_party_size"] == 4.0
    assert impact["estimated_covers"] == RECENT_ORDERS * 4
    assert impact["avg_spend_per_guest"] == (RECENT_ORDERS * 1000) // (RECENT_ORDERS * 4)

    # The revenue must come back as one aggregate row, not 90 ORM objects.
    dine_in_sums = [s for s in statements if "sum(" in s.lower() and "orders.total" in s.lower()]
    assert dine_in_sums, "dine-in revenue should be a SQL SUM, not a Python sum over .all()"
    assert any("created_at" in s for s in dine_in_sums), (
        "the dine-in revenue aggregate must carry a created_at predicate:\n"
        + "\n\n".join(dine_in_sums)
    )
    # And no statement should have selected whole order rows for this purpose.
    assert not any(
        s.lower().startswith("select") and "orders.mpesa_checkout_request_id" in s.lower()
        for s in dine_in_sums
    )


def test_degenerate_window_falls_back_to_all_time_rate(db_session):
    """
    Imported data whose orders and reservations don't overlap must not produce a
    zero (or absurd) spend-per-guest. Orders are recent, the only completed
    reservation is 300 days old — so the windowed guest count is 0 and the rate
    must fall back to the all-time ratio instead of dividing by max(...,1).
    """
    db_session.add_all([
        models.Restaurant(id=1, tenant_id=None, name="Imported", address="x"),
        models.MenuItem(id=1, restaurant_id=1, name="X", price=1000, category="main"),
    ])
    db_session.commit()

    for _ in range(RECENT_ORDERS):
        _add_order(db_session, days_ago=2, qty=1)   # 40 x 1000 = 40000 cents, recent
    db_session.add(models.Reservation(
        restaurant_id=1, customer_name="Old", customer_phone="1", party_size=4,
        reservation_date=(ANCHOR - timedelta(days=300)).date(), reservation_time=time(19, 0),
        status=models.ReservationStatus.COMPLETED,
    ))
    db_session.commit()

    impact = reservation_optimizer.get_reservation_insights(db_session, 1)["revenue_impact"]
    assert impact["total_dine_in_revenue"] == RECENT_ORDERS * 1000    # windowed orders exist
    # No completed reservation in the window, so party size falls back to the
    # all-time book (one 4-top) rather than to DEFAULT_PARTY_SIZE.
    assert impact["avg_party_size"] == 4.0
    assert impact["avg_spend_per_guest"] == (RECENT_ORDERS * 1000) // (RECENT_ORDERS * 4)
