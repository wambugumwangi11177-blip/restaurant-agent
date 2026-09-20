"""A cost price of zero means "nobody entered one", not "this is free".

models.py defaults MenuItem.cost_price to 0, so the two are the same value in
the database. Treating them alike made an un-costed dish report a 100% margin,
sort to the top of the contribution table, and get skipped by leak detection —
the owner was shown the item nobody had costed as the best thing on their menu,
and the one most likely to be losing money was the one that could never appear
in the leak list.

The same zero also flowed into the restaurant-wide food-cost and gross-margin
headlines, and into the daypart and channel margins, making the business look
more profitable the less data had been entered.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import models
from time_utils import utcnow
from ai.profit.intelligence import get_profit_intelligence


@pytest.fixture
def restaurant(db_session):
    db = db_session
    db.add(models.Tenant(id=700, name="Profit tenant"))
    db.flush()
    db.add(models.Restaurant(id=701, tenant_id=700, name="Profit test"))
    db.commit()
    return 701


def _sell(db, rid, item, qty, when=None, channel=None):
    order = models.Order(
        restaurant_id=rid, total=qty * item.price, is_paid=True,
        status=models.OrderStatus.SERVED,
        created_at=when or (utcnow() - timedelta(days=1)),
        delivery_channel=channel or models.DeliveryChannel.WALK_IN,
    )
    db.add(order)
    db.flush()
    db.add(models.OrderItem(order_id=order.id, menu_item_id=item.id,
                            quantity=qty, unit_price=item.price))
    db.commit()
    return order


def _item(db, rid, name, price, cost):
    item = models.MenuItem(restaurant_id=rid, name=name, price=price,
                           cost_price=cost, category="Main")
    db.add(item)
    db.commit()
    return item


# ── The core claim ───────────────────────────────────────────────────────────

def test_an_uncosted_item_is_not_a_100_percent_margin(db_session, restaurant):
    item = _item(db_session, restaurant, "Uncosted Dish", 50000, 0)
    _sell(db_session, restaurant, item, 10)

    data = get_profit_intelligence(db_session, restaurant)
    row = next(r for r in data["contribution_margins"] if r["item_name"] == "Uncosted Dish")
    assert row["margin_pct"] is None
    assert row["status"] == "UNKNOWN_COST"
    assert row["total_profit_30d"] is None


def test_an_uncosted_item_does_not_outrank_a_real_earner(db_session, restaurant):
    """It used to sort first: its profit was being recorded as its whole revenue."""
    good = _item(db_session, restaurant, "Real Earner", 40000, 10000)
    unknown = _item(db_session, restaurant, "Uncosted Dish", 50000, 0)
    _sell(db_session, restaurant, good, 10)
    _sell(db_session, restaurant, unknown, 10)

    rows = get_profit_intelligence(db_session, restaurant)["contribution_margins"]
    assert rows[0]["item_name"] == "Real Earner"
    assert rows[-1]["item_name"] == "Uncosted Dish"


def test_the_headline_margin_ignores_uncosted_revenue(db_session, restaurant):
    """Half the revenue uncosted must not halve the apparent food cost."""
    costed = _item(db_session, restaurant, "Costed", 10000, 4000)     # 40% food cost
    unknown = _item(db_session, restaurant, "Uncosted", 10000, 0)
    _sell(db_session, restaurant, costed, 10)
    _sell(db_session, restaurant, unknown, 10)

    summary = get_profit_intelligence(db_session, restaurant)["summary"]
    # Food cost is 40% of the revenue we can actually measure, not 20% of all of it.
    assert summary["food_cost_pct"] == 40.0
    assert summary["gross_margin_pct"] == 60.0
    assert summary["cost_coverage_pct"] == 50.0
    assert summary["items_without_cost"] == 1


def test_coverage_and_uncosted_revenue_are_reported(db_session, restaurant):
    costed = _item(db_session, restaurant, "Costed", 10000, 4000)
    unknown = _item(db_session, restaurant, "Uncosted", 20000, 0)
    _sell(db_session, restaurant, costed, 1)
    _sell(db_session, restaurant, unknown, 3)

    summary = get_profit_intelligence(db_session, restaurant)["summary"]
    assert summary["uncosted_revenue_30d"] == 60000
    assert summary["costed_revenue_30d"] == 10000
    assert summary["cost_coverage_pct"] == 14.3


def test_missing_costs_are_raised_as_a_recommendation(db_session, restaurant):
    """An item excluded from leak detection is exactly the one most likely to
    be leaking, so its absence has to be said out loud."""
    unknown = _item(db_session, restaurant, "Uncosted Dish", 50000, 0)
    _sell(db_session, restaurant, unknown, 4)

    data = get_profit_intelligence(db_session, restaurant)
    gaps = [r for r in data["recommendations"] if r["type"] == "missing_cost_data"]
    assert len(gaps) == 1
    assert gaps[0]["priority"] == "CRITICAL"
    assert "Uncosted Dish" in gaps[0]["message"]
    assert data["uncosted_items"][0]["item_name"] == "Uncosted Dish"


def test_a_real_low_margin_item_is_still_caught_as_a_leak(db_session, restaurant):
    """The fix must not suppress genuine leaks — only unmeasurable ones."""
    leaky = _item(db_session, restaurant, "Leaky", 10000, 8000)   # 20% margin
    _sell(db_session, restaurant, leaky, 5)

    data = get_profit_intelligence(db_session, restaurant)
    names = [leak["item_name"] for leak in data["profit_leaks"]]
    assert "Leaky" in names


def test_a_daypart_margin_is_withheld_when_most_of_it_is_uncosted(db_session, restaurant):
    """A margin drawn from a fifth of the window's revenue is not the window's
    margin, and stating it sends the owner after the wrong service period."""
    costed = _item(db_session, restaurant, "Costed", 10000, 4000)
    unknown = _item(db_session, restaurant, "Uncosted", 10000, 0)
    lunch = (utcnow() - timedelta(days=1)).replace(hour=9)   # 12:00 EAT
    _sell(db_session, restaurant, costed, 1, when=lunch)
    _sell(db_session, restaurant, unknown, 9, when=lunch)

    dayparts = get_profit_intelligence(db_session, restaurant)["daypart_analysis"]
    lunch_row = next(d for d in dayparts if d["daypart"] == "lunch")
    assert lunch_row["margin_pct"] is None
    assert lunch_row["cost_coverage_pct"] == 10.0


def test_a_fully_costed_menu_reports_margins_as_before(db_session, restaurant):
    """No behaviour change for the case the module was written for."""
    a = _item(db_session, restaurant, "A", 10000, 3000)
    b = _item(db_session, restaurant, "B", 20000, 8000)
    _sell(db_session, restaurant, a, 5)
    _sell(db_session, restaurant, b, 5)

    data = get_profit_intelligence(db_session, restaurant)
    assert data["summary"]["cost_coverage_pct"] == 100.0
    assert data["summary"]["items_without_cost"] == 0
    assert all(r["margin_pct"] is not None for r in data["contribution_margins"])
    assert not [r for r in data["recommendations"] if r["type"] == "missing_cost_data"]
