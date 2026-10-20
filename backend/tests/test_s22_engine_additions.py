"""
S2.2 — three small engine additions the planted scenarios needed (figure 6.1), each pinned on its own:

  P3   pricing.check_delivery_margins says what one plate keeps through a platform and dine-in (integer cents);
  P7   cash_reconciliation.recurring_drawer_gaps finds the same weekday + shift coming up short again and again;
  P13  supply_chain.short_deliveries lists deliveries that arrived with less than was ordered.

All read-only. The scenarios themselves are asserted end to end in tests/evals/test_e4_demo_scenarios.py.
"""
from datetime import datetime, timedelta

import pytest

import models
from tests.fixtures import golden_restaurant as gr
from time_utils import utcnow


# ── P3: what one plate keeps ─────────────────────────────────────────────────

def test_a_burger_keeps_170_through_glovo_and_320_dine_in(db_session):
    """Figure 6.1 P3: a KES 600 burger costing KES 280, 25% Glovo commission. 600 × 0.75 − 280 = 170; 600 − 280 = 320."""
    from ai.pricing.recommendations import get_pricing_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_burger_delivery(db_session, g)
    gaps = get_pricing_intelligence(db_session, g.rid)["delivery_gaps"]
    burger = next(x for x in gaps if x["item_name"] == "Burger" and x["channel"] == "glovo")
    assert burger["delivery_keeps_cents"] == 17_000 and burger["dine_in_keeps_cents"] == 32_000
    assert burger["commission_pct"] == 25 and burger["effective_delivery_margin"] == pytest.approx(28.3, abs=0.05)
    bolt = next(x for x in gaps if x["item_name"] == "Burger" and x["channel"] == "bolt_food")
    assert bolt["delivery_keeps_cents"] == 600 * 100 * 0.8 - 28_000 == 20_000


# ── P7: the same shift short, again and again ────────────────────────────────

def _count(db, g, local_day, hour, short_cents, expected=60_000):
    """A drawer count for the window starting at `hour` Nairobi time on `local_day`; `short_cents` < 0 means over."""
    start = datetime(local_day.year, local_day.month, local_day.day, hour) - timedelta(hours=3)
    db.add(models.CashDrawerCount(restaurant_id=g.rid, window_start=start, window_end=start + timedelta(hours=7),
                                  expected_amount_cents=expected, counted_amount_cents=expected - short_cents,
                                  counted_by_user_id=g.manager.id, counted_at=start + timedelta(hours=7, minutes=10)))
    db.commit()


def _tuesdays(n, back=1):
    day, found = utcnow().date(), []
    while len(found) < n + back - 1:
        day -= timedelta(days=1)
        if day.weekday() == 1:
            found.append(day)
    return found[back - 1:]


def test_four_short_tuesday_evenings_are_a_pattern(db_session):
    from ai.cash_reconciliation.intelligence import recurring_drawer_gaps
    g = gr.build_skeleton(db_session)
    for d in _tuesdays(4):
        _count(db_session, g, d, 16, 52_000)
        _count(db_session, g, d, 8, 0)                                      # the day shift on the same day is fine
    found = recurring_drawer_gaps(db_session, g.rid)
    assert len(found) == 1
    p = found[0]
    assert (p.when, p.times_short, p.of_last) == ("Tuesday evening", 4, 4)
    assert p.average_short_cents == p.total_short_cents // 4 == 52_000


def test_three_of_the_last_four_is_enough_two_is_not(db_session):
    from ai.cash_reconciliation.intelligence import recurring_drawer_gaps
    g = gr.build_skeleton(db_session)
    days = _tuesdays(4)
    for d, short in zip(days, (52_000, 0, 48_000, 51_000)):
        _count(db_session, g, d, 16, short)
    assert [(p.times_short, p.of_last) for p in recurring_drawer_gaps(db_session, g.rid)] == [(3, 4)]
    g2 = gr.build_skeleton(db_session, suffix="two")
    for d, short in zip(days, (52_000, 0, 0, 51_000)):
        _count(db_session, g2, d, 16, short)
    assert recurring_drawer_gaps(db_session, g2.rid) == []


def test_only_the_latest_four_count_and_each_weekday_and_shift_stand_alone(db_session):
    from ai.cash_reconciliation.intelligence import recurring_drawer_gaps
    g = gr.build_skeleton(db_session)
    days = _tuesdays(6)
    for d, short in zip(days, (0, 0, 0, 0, 52_000, 52_000)):                # old shortages, then four clean weeks
        _count(db_session, g, d, 16, short)
    assert recurring_drawer_gaps(db_session, g.rid) == []
    for d in _tuesdays(3):                                                  # evening shortages on Tuesdays do not make the day shift one
        _count(db_session, g, d, 8, 50_000)
    assert [p.when for p in recurring_drawer_gaps(db_session, g.rid)] == ["Tuesday day"]


def test_overs_and_small_differences_are_not_short(db_session):
    from ai.cash_reconciliation.intelligence import recurring_drawer_gaps
    g = gr.build_skeleton(db_session)
    for d, short in zip(_tuesdays(4), (-50_000, -50_000, 15_000, 19_000)):   # two overs, two under the KES 200 tolerance
        _count(db_session, g, d, 16, short)
    assert recurring_drawer_gaps(db_session, g.rid) == []


def test_the_owners_tolerance_decides_what_counts_as_short(db_session):
    from ai.cash_reconciliation.intelligence import recurring_drawer_gaps
    from owner.settings import update_settings
    g = gr.build_skeleton(db_session)
    for d in _tuesdays(4):
        _count(db_session, g, d, 16, 30_000)                                 # KES 300 short each time
    assert len(recurring_drawer_gaps(db_session, g.rid)) == 1                # over the default KES 200
    update_settings(db_session, g.rid, g.owner.id, {"cash_tolerance_kes": 400})
    assert recurring_drawer_gaps(db_session, g.rid) == []


def test_the_weekday_is_the_nairobi_weekday(db_session):
    """A window that starts at 01:30 Nairobi on Tuesday is 22:30 UTC on Monday: it is a Tuesday (day shift)."""
    from ai.cash_reconciliation.intelligence import recurring_drawer_gaps
    g = gr.build_skeleton(db_session)
    for d in _tuesdays(3):
        start = datetime(d.year, d.month, d.day, 1, 30) - timedelta(hours=3)
        assert start.weekday() == 0                                          # Monday in UTC
        db_session.add(models.CashDrawerCount(restaurant_id=g.rid, window_start=start, window_end=start + timedelta(hours=6),
                                              expected_amount_cents=60_000, counted_amount_cents=8_000, counted_by_user_id=g.manager.id))
    db_session.commit()
    assert [p.when for p in recurring_drawer_gaps(db_session, g.rid)] == ["Tuesday day"]


def test_recurring_gaps_are_tenant_scoped(db_session):
    from ai.cash_reconciliation.intelligence import recurring_drawer_gaps
    a = gr.build_skeleton(db_session, suffix="a")
    b = gr.build_skeleton(db_session, suffix="b")
    for d in _tuesdays(4):
        _count(db_session, a, d, 16, 52_000)
    assert len(recurring_drawer_gaps(db_session, a.rid)) == 1
    assert recurring_drawer_gaps(db_session, b.rid) == []


# ── P13: short deliveries ────────────────────────────────────────────────────

def _po(db, g, ordered, received, *, days_ago=3, cost=48_000, supplier=None, item="Beef"):
    delivered = utcnow() - timedelta(days=days_ago)
    po = models.PurchaseOrder(restaurant_id=g.rid, supplier_id=(supplier or g.supplier).id, inventory_item_id=g.inventory[item].id,
                              quantity_ordered=ordered, quantity_received=received, unit="kg", cost_per_unit=cost, total_cost=round((received or 0) * cost),
                              status="PARTIAL" if received is not None and received < ordered else "DELIVERED",
                              ordered_at=delivered - timedelta(days=1), expected_at=delivered, delivered_at=delivered if received is not None else None)
    db.add(po)
    db.commit()
    return po


def test_a_delivery_of_56_when_60_were_ordered_is_short(db_session):
    from ai.supply_chain.intelligence import get_supply_chain_intelligence, short_deliveries
    g = gr.build_skeleton(db_session)
    _po(db_session, g, 60, 56)
    rows = short_deliveries(db_session, g.rid)
    assert len(rows) == 1
    r = rows[0]
    assert (r["supplier"], r["item"], r["unit"], r["ordered"], r["received"], r["short_by"]) == ("Golden Meats", "Beef", "kg", 60, 56, 4)
    assert r["short_value_cents"] == 4 * 48_000
    assert get_supply_chain_intelligence(db_session, g.rid)["short_deliveries"] == rows


def test_a_few_grams_light_a_full_delivery_old_deliveries_and_open_orders_are_not_short(db_session):
    from ai.supply_chain.intelligence import short_deliveries
    g = gr.build_skeleton(db_session)
    _po(db_session, g, 60, 59.5)                                     # 0.8% light: rounding
    _po(db_session, g, 60, 60)
    _po(db_session, g, 60, 40, days_ago=45)                          # a short delivery, but six weeks ago
    _po(db_session, g, 60, None)                                     # not delivered yet
    assert short_deliveries(db_session, g.rid) == []


def test_the_biggest_shortfall_is_listed_first(db_session):
    from ai.supply_chain.intelligence import short_deliveries
    g = gr.build_skeleton(db_session)
    _po(db_session, g, 10, 8, cost=10_000, item="Beef")
    _po(db_session, g, 10, 9, cost=90_000, item="Tilapia")
    assert [r["item"] for r in short_deliveries(db_session, g.rid)] == ["Tilapia", "Beef"]
    assert [r["short_by"] for r in short_deliveries(db_session, g.rid)] == [1, 2]


def test_short_deliveries_are_tenant_scoped(db_session):
    from ai.supply_chain.intelligence import short_deliveries
    a = gr.build_skeleton(db_session, suffix="a")
    b = gr.build_skeleton(db_session, suffix="b")
    _po(db_session, a, 60, 56)
    assert len(short_deliveries(db_session, a.rid)) == 1
    assert short_deliveries(db_session, b.rid) == []


def test_a_short_delivery_does_not_count_against_on_time_reliability(db_session):
    """Short is a separate signal from late: a PARTIAL order is neither on time nor late (D3's learning rule is unchanged)."""
    from ai.supply_chain.intelligence import reliability_from_orders
    g = gr.build_skeleton(db_session)
    orders = [_po(db_session, g, 60, 56), _po(db_session, g, 60, 60), _po(db_session, g, 60, 60), _po(db_session, g, 60, 60)]
    pct, closed = reliability_from_orders(orders)
    assert closed == 3 and pct == 100.0
