"""
The arithmetic behind the two numbers owners read as headlines.

Three methodological defects fixed 2026-07-08:

  1. Star/Dog classification used the RAW MEAN of units sold as the popularity
     cutoff. Unit sales are right-skewed — a couple of bestsellers drag the mean
     above what a healthy mid-list item sells — so the raw mean systematically
     over-condemns the menu. Standard menu engineering (Kasavana & Smith) uses
     0.7 x mean. The dashboard surfaces "N Dog items" as a headline risk.

  2. The 0-100 "menu optimization score" was
     `stars_pct*130 + (1-dogs_pct)*70 - food_cost*0.5 + rising_count*3`.
     `rising_count` is an unbounded item count, so it could dominate everything
     else and peg a genuinely bad menu near 100.

  3. `day_over_day_change` reported a flat 0% for any yesterday under KES 1,000,
     masking real movement for low-volume venues.
"""

from collections import Counter
from datetime import timedelta

import pytest

import models
from time_utils import utcnow
from ai import menu_engineer
from ai.menu_engineer import _menu_optimization_score, POPULARITY_INDEX


# ── 1. Popularity cutoff ──────────────────────────────────────────────────────
#
# Five items, all with identical margins (so profitability never decides the
# quadrant and we isolate popularity). One bestseller at 100 units, four solid
# mid-list items at 40 units each.
#
#   total = 100 + 4*40 = 260,  mean = 52,  0.7 x mean = 36.4
#
# A 40-unit item is BELOW the raw mean (52) but ABOVE the 0.7 index (36.4). Under
# the old cutoff all four were written off; under the correct one they are Stars.

BESTSELLER_QTY = 100
MIDLIST_QTY = 40


@pytest.fixture
def skewed_menu(db_session):
    db_session.add(models.Restaurant(id=1, tenant_id=None, name="Skewed", address="x"))
    # price 1000, cost 400 -> identical margin 600 for every item
    for i in range(1, 6):
        db_session.add(models.MenuItem(
            id=i, restaurant_id=1, name=f"Item{i}", price=1000, cost_price=400,
            category="main",
        ))
    db_session.commit()

    def _sell(menu_item_id, units):
        o = models.Order(
            restaurant_id=1, status=models.OrderStatus.SERVED,
            payment_method=models.PaymentMethod.CASH, is_paid=True,
            total=1000 * units, created_at=utcnow() - timedelta(days=3),
        )
        db_session.add(o)
        db_session.flush()
        db_session.add(models.OrderItem(
            order_id=o.id, menu_item_id=menu_item_id, quantity=units, unit_price=1000,
        ))

    _sell(1, BESTSELLER_QTY)
    for i in range(2, 6):
        _sell(i, MIDLIST_QTY)
    db_session.commit()
    return db_session


def test_the_fixture_really_is_skewed():
    """The test only proves anything if the mid-list item straddles the two cutoffs."""
    total = BESTSELLER_QTY + 4 * MIDLIST_QTY
    raw_mean = total / 5
    indexed = POPULARITY_INDEX * raw_mean
    assert indexed <= MIDLIST_QTY < raw_mean, "fixture no longer distinguishes the two cutoffs"


def test_midlist_item_is_a_star_not_a_dog(skewed_menu):
    result = menu_engineer.get_menu_engineering(skewed_menu, 1)
    by_name = {m["name"]: m for m in result["matrix"]}

    # Under the raw mean these four sat below the cutoff and, being exactly at
    # the average margin, were classified Puzzle — "profitable but nobody buys
    # it" — for items selling 40% of the bestseller's volume.
    for i in range(2, 6):
        assert by_name[f"Item{i}"]["classification"] == "Star", by_name[f"Item{i}"]

    assert by_name["Item1"]["classification"] == "Star"
    assert result["summary"]["dogs"] == 0


def test_solid_seller_on_a_thin_margin_is_a_plowhorse_not_a_dog(skewed_menu):
    """
    The "N Dog items" headline. A mid-list item is condemned as a Dog only when
    it is ALSO below average margin — otherwise the raw mean files it as a
    Puzzle. This is that case: 40 units (same as its healthy-margin siblings) but
    a thin margin.

        total = 100 + 4*40 + 40 = 300 over 6 items -> mean 50, 0.7 x mean 35

    40 < 50, so the raw mean called it a Dog: "cut this item". 40 >= 35, so it is
    what it actually is — a Plowhorse: it sells, it just needs repricing.
    """
    db = skewed_menu
    db.add(models.MenuItem(id=6, restaurant_id=1, name="ThinMargin", price=1000,
                           cost_price=900, category="main"))
    db.commit()
    o = models.Order(
        restaurant_id=1, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True,
        total=40_000, created_at=utcnow() - timedelta(days=3),
    )
    db.add(o)
    db.flush()
    db.add(models.OrderItem(order_id=o.id, menu_item_id=6, quantity=MIDLIST_QTY, unit_price=1000))
    db.commit()

    result = menu_engineer.get_menu_engineering(db, 1)
    by_name = {m["name"]: m for m in result["matrix"]}
    assert by_name["ThinMargin"]["classification"] == "Plowhorse"
    assert result["summary"]["dogs"] == 0   # was 1 under the raw mean


def test_a_genuinely_unpopular_item_is_still_a_dog(skewed_menu):
    """The index must not simply make everything a Star."""
    db = skewed_menu
    db.add(models.MenuItem(id=6, restaurant_id=1, name="Flop", price=1000,
                           cost_price=900, category="main"))  # margin 100 << avg
    db.commit()
    o = models.Order(
        restaurant_id=1, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True,
        total=1000, created_at=utcnow() - timedelta(days=3),
    )
    db.add(o)
    db.flush()
    db.add(models.OrderItem(order_id=o.id, menu_item_id=6, quantity=1, unit_price=1000))
    db.commit()

    result = menu_engineer.get_menu_engineering(db, 1)
    by_name = {m["name"]: m for m in result["matrix"]}
    assert by_name["Flop"]["classification"] == "Dog"   # 1 unit, thin margin
    assert result["summary"]["dogs"] == 1


# ── 2. Menu optimization score ────────────────────────────────────────────────

def test_score_is_bounded_even_when_every_item_is_rising():
    """
    The old formula added `rising_count * 3`. A 40-item menu of pure Dogs at 50%
    food cost, all trending up, scored 95 out of 100 (0 + 0 - 25 + 120, clamped).
    The score is now a weighted mean of ratios, so momentum alone cannot carry it.
    """
    score = _menu_optimization_score(
        Counter({"Dog": 40}), avg_food_cost=50.0, rising_count=40, falling_count=0,
        item_count=40,
    )
    assert score <= 20, f"an all-Dog, 50%-food-cost menu scored {score}"


def test_score_hits_its_endpoints():
    perfect = _menu_optimization_score(
        Counter({"Star": 10}), avg_food_cost=25.0, rising_count=10, falling_count=0,
        item_count=10,
    )
    disaster = _menu_optimization_score(
        Counter({"Dog": 10}), avg_food_cost=40.0, rising_count=0, falling_count=10,
        item_count=10,
    )
    assert perfect == 100
    assert disaster == 0


def test_score_stays_in_range_for_extreme_inputs():
    """Bounded by construction (weights sum to 1 over [0,1] components), not by a clamp."""
    for food_cost in (0.0, 25.0, 40.0, 100.0, 1000.0):
        for rising, falling in ((0, 0), (50, 0), (0, 50), (25, 25)):
            score = _menu_optimization_score(
                Counter({"Star": 20, "Dog": 30}), food_cost, rising, falling, 50,
            )
            assert 0 <= score <= 100, (food_cost, rising, falling, score)


def test_score_rewards_a_better_portfolio_at_equal_cost_and_momentum():
    good = _menu_optimization_score(Counter({"Star": 8, "Dog": 2}), 30.0, 0, 0, 10)
    bad = _menu_optimization_score(Counter({"Star": 2, "Dog": 8}), 30.0, 0, 0, 10)
    assert good > bad


def test_score_of_an_empty_menu_is_zero():
    assert _menu_optimization_score(Counter(), 0.0, 0, 0, 0) == 0


# ── 3. day_over_day_change on low-volume days ─────────────────────────────────

def test_low_volume_day_reports_real_movement(db_session):
    """
    KES 450 yesterday -> KES 900 today is a doubling. The old `>= 100_000` cents
    floor reported it as 0.0%, which the UI renders as a genuine "no change".
    """
    from ai import ops_manager

    db_session.add(models.Restaurant(id=1, tenant_id=None, name="Kibanda", address="x"))
    db_session.commit()

    now = utcnow()
    for created, total in ((now - timedelta(days=1), 45_000), (now, 90_000)):
        db_session.add(models.Order(
            restaurant_id=1, status=models.OrderStatus.SERVED,
            payment_method=models.PaymentMethod.CASH, is_paid=True,
            total=total, created_at=created,
        ))
    db_session.commit()

    stats = ops_manager.get_operations_dashboard(db_session, 1)["quick_stats"]
    assert stats["yesterday_revenue"] == 45_000
    assert stats["today_revenue"] == 90_000
    assert stats["day_over_day_change"] == 100.0


def test_zero_yesterday_still_guards_divide_by_zero(db_session):
    from ai import ops_manager

    db_session.add(models.Restaurant(id=1, tenant_id=None, name="Kibanda", address="x"))
    db_session.add(models.Order(
        restaurant_id=1, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True,
        total=90_000, created_at=utcnow(),
    ))
    db_session.commit()

    stats = ops_manager.get_operations_dashboard(db_session, 1)["quick_stats"]
    assert stats["yesterday_revenue"] == 0
    assert stats["day_over_day_change"] == 0
