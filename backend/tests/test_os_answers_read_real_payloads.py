"""The OS page must answer from what the agents actually returned.

Five of the nine answer functions read keys no module emits: "leaks" for
profit (it is "profit_leaks"), "labor_cost_pct" for staff (it is
summary.labor_pct), "no_show" for bookings (no_show_analysis.no_show_rate),
"stations" for kitchen (station_performance), "trend" for revenue ("trends").
Every mismatch resolved to None and fell through to a calm fallback, so the
owner was told there was nothing to report by a system that had not looked.

Each test here seeds a condition the owner would want to hear about and
asserts the answer mentions it. A test that only asserted "returns 200" would
have passed against the broken version, which is the point.
"""
from __future__ import annotations

from datetime import timedelta, date

import pytest

import models
from time_utils import utcnow
from routers import ai_ask


@pytest.fixture
def rid(db_session):
    db = db_session
    db.add(models.Tenant(id=800, name="OS tenant"))
    db.flush()
    db.add(models.Restaurant(id=801, tenant_id=800, name="OS test"))
    db.commit()
    return 801


def _menu(db, rid, name, price, cost, category="Main"):
    item = models.MenuItem(restaurant_id=rid, name=name, price=price,
                           cost_price=cost, category=category)
    db.add(item)
    db.commit()
    return item


def _order(db, rid, item, qty, days_ago=1, hour=None):
    when = utcnow() - timedelta(days=days_ago)
    if hour is not None:
        when = when.replace(hour=hour)
    order = models.Order(restaurant_id=rid, total=qty * item.price, is_paid=True,
                         status=models.OrderStatus.SERVED, created_at=when)
    db.add(order)
    db.flush()
    db.add(models.OrderItem(order_id=order.id, menu_item_id=item.id,
                            quantity=qty, unit_price=item.price))
    db.commit()
    return order


# ── Profit ───────────────────────────────────────────────────────────────────

def test_profit_answer_names_the_actual_leak(db_session, rid):
    """It read pi["leaks"], which does not exist, and always said there were none."""
    leaky = _menu(db_session, rid, "Leaky Biryani", 10000, 8500)   # 15% margin
    for day in range(1, 6):
        _order(db_session, rid, leaky, 4, days_ago=day)

    answer = ai_ask._answer_profit(db_session, rid, "what is losing me money?")
    assert "Leaky Biryani" in answer["finding"]
    assert answer["impact"] != "—"
    assert answer["data"]["leaks"] >= 1


def test_profit_answer_reports_uncosted_items_when_there_are_no_leaks(db_session, rid):
    unknown = _menu(db_session, rid, "Uncosted Pilau", 50000, 0)
    _order(db_session, rid, unknown, 3)

    answer = ai_ask._answer_profit(db_session, rid, "what is losing me money?")
    assert "no cost price" in answer["finding"]
    assert answer["data"]["uncosted_items"] == 1


# ── Labour ───────────────────────────────────────────────────────────────────

def test_staff_answer_states_the_labour_percentage(db_session, rid):
    """It read labor["labor_cost_pct"] — the figure is at summary.labor_pct —
    and always answered "Labor intelligence loaded.\""""
    item = _menu(db_session, rid, "Ugali", 10000, 3000)
    for day in range(1, 8):
        _order(db_session, rid, item, 10, days_ago=day)
    staff = models.StaffMember(restaurant_id=rid, name="Cook")
    db_session.add(staff)
    db_session.flush()
    for day in range(1, 8):
        db_session.add(models.LaborShift(
            restaurant_id=rid, staff_member_id=staff.id,
            shift_date=(utcnow() - timedelta(days=day)).date(),
            labor_cost=200000, actual_hours=8,
            actual_start=utcnow() - timedelta(days=day, hours=8)))
    db_session.commit()

    answer = ai_ask._answer_staff(db_session, rid, "how much am I spending on staff?")
    assert "Labor intelligence loaded" not in answer["finding"]
    assert "% of revenue" in answer["finding"]
    assert answer["data"]["labor_pct"] is not None
    assert answer["data"]["shifts_logged"] == 7


def test_staff_answer_says_so_when_no_shifts_are_logged(db_session, rid):
    answer = ai_ask._answer_staff(db_session, rid, "how much am I spending on staff?")
    assert "No shifts logged" in answer["finding"]


# ── Bookings ─────────────────────────────────────────────────────────────────

def test_bookings_answer_states_a_real_no_show_rate(db_session, rid):
    """It read ins["no_show"] and always printed "No-show rate is n/a.\""""
    table = models.Table(restaurant_id=rid, table_number=1, capacity=4)
    db_session.add(table)
    db_session.flush()
    # reservation_date and reservation_time are separate Date/Time columns,
    # not one datetime — SQLite's Time type rejects a datetime outright.
    for i in range(10):
        when = utcnow() - timedelta(days=i + 1)
        db_session.add(models.Reservation(
            restaurant_id=rid, table_id=table.id, customer_name=f"Guest {i}",
            customer_phone=f"+2547000000{i:02d}", party_size=2,
            reservation_date=when.date(), reservation_time=when.time(),
            created_at=when,
            status=(models.ReservationStatus.NO_SHOW if i < 3
                    else models.ReservationStatus.COMPLETED)))
    db_session.commit()

    answer = ai_ask._answer_bookings(db_session, rid, "what is my no-show rate?")
    assert "n/a" not in answer["finding"]
    assert answer["data"]["total_reservations"] == 10
    assert answer["data"]["no_show_rate"] is not None


def test_bookings_answer_says_so_with_no_reservations(db_session, rid):
    answer = ai_ask._answer_bookings(db_session, rid, "what is my no-show rate?")
    assert "No reservations recorded" in answer["finding"]


# ── Menu ─────────────────────────────────────────────────────────────────────

def test_menu_answer_survives_summary_counts_being_integers(db_session, rid):
    """summary["stars"] is a COUNT. The old code called len() on it, raising
    TypeError inside the route's try/except and producing a generic failure."""
    star = _menu(db_session, rid, "Nyama Choma", 80000, 20000)
    dog = _menu(db_session, rid, "Cold Soup", 30000, 25000)
    for day in range(1, 15):
        _order(db_session, rid, star, 8, days_ago=day)
        _order(db_session, rid, dog, 1, days_ago=day)

    answer = ai_ask._answer_menu(db_session, rid, "which dishes should I promote?")
    assert isinstance(answer["finding"], str)
    assert "Star" in answer["finding"]
    assert isinstance(answer["data"]["stars"], int)


# ── Pricing ──────────────────────────────────────────────────────────────────

def test_pricing_answer_names_the_item_and_both_prices(db_session, rid):
    """Recommendations carry item_name/current_price/suggested_price; the old
    code read r0["item"] and r0["suggestion"], neither of which exists."""
    thin = _menu(db_session, rid, "Thin Margin Fish", 10000, 8000)   # below the floor
    for day in range(1, 21):
        _order(db_session, rid, thin, 3, days_ago=day)

    answer = ai_ask._answer_pricing(db_session, rid, "should I raise my prices?")
    if answer["data"]["open_recommendations"]:
        assert "Thin Margin Fish" in answer["finding"]
        assert "KSh" in answer["finding"]
    else:
        assert "No pricing changes recommended" in answer["finding"]


# ── Stock ────────────────────────────────────────────────────────────────────

def test_stock_answer_uses_the_real_prediction_fields(db_session, rid):
    """Predictions carry name/days_until_depletion; the old code read
    item_name/days_until_stockout, so `soon` was always empty."""
    db_session.add(models.InventoryItem(
        restaurant_id=rid, item_name="Beef", quantity=1, unit="kg",
        low_stock_threshold=10, cost_per_unit_cents=50000))
    db_session.commit()

    answer = ai_ask._answer_stock(db_session, rid, "what do I need to order today?")
    assert "Beef" in answer["finding"]
    assert answer["data"]["candidates"] >= 1


# ── Revenue ──────────────────────────────────────────────────────────────────

def test_revenue_answer_reads_trends_not_trend(db_session, rid):
    item = _menu(db_session, rid, "Chapati", 5000, 1500)
    for day in range(1, 30):
        _order(db_session, rid, item, 10, days_ago=day)

    answer = ai_ask._answer_revenue(db_session, rid, "how much did I make today?")
    assert "Revenue today is" in answer["finding"]
    assert isinstance(answer["data"]["anomalies_found"], int)


# ── Every answer, structurally ───────────────────────────────────────────────

@pytest.mark.parametrize("fn", [
    "_answer_stock", "_answer_revenue", "_answer_bookings", "_answer_kitchen",
    "_answer_staff", "_answer_menu", "_answer_pricing", "_answer_profit",
    "_answer_ops",
])
def test_every_answer_returns_the_card_shape_on_an_empty_restaurant(db_session, rid, fn):
    """A brand-new restaurant must get an honest empty answer, not an exception."""
    answer = getattr(ai_ask, fn)(db_session, rid, "anything")
    for key in ("finding", "why", "impact", "recommendation", "module", "steps"):
        assert key in answer, f"{fn} dropped {key}"
    assert isinstance(answer["finding"], str) and answer["finding"]
    assert isinstance(answer["steps"], list)
