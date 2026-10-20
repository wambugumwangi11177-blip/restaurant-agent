"""
A gap smaller than one serving is rounding, not missing stock (found by the S5.2 gate on the real clock).

The flag is the owner's percentage (`missing_stock_flag_pct`). On a small item (two portions of tilapia in a
week) a weekly waste write-off of 0.03 kg is 4% of 0.6 kg: over the line, but less than the smallest portion any dish
takes, and worth KES 15. Such a gap cannot be told from a measuring error, so it is not "worth a look". A gap of one
serving or more still is, however small the percentage is against a big base.
"""
from datetime import timedelta

import pytest

import models
from ai.stock_custody import compute_variance_report, flagged_items
from owner.settings import DEFAULTS
from tests.fixtures import golden_restaurant as gr

WINDOW = 24 * 8


def _stews(db, g, n: int, drawn: float) -> None:
    """`n` beef stews (0.25 kg each, so n/4 kg expected) and `drawn` kg issued to the kitchen for them."""
    stew = g.items["Beef stew"]
    for i in range(n):
        gr.add_order(db, g, [(stew, 1, stew.price)], g.now - timedelta(minutes=30 * i))
    db.add(models.StockMovement(
        inventory_item_id=g.inventory["Beef"].id, movement_type=models.StockMovementType.OUT, quantity=drawn,
        reason="issued to kitchen", created_at=g.now - timedelta(hours=1), performed_by_user_id=g.kitchen.id))
    db.commit()


def _beef(db, g):
    return next(r for r in compute_variance_report(db, g.rid, hours=WINDOW) if r.item_name == "Beef")


def test_the_smallest_beef_portion_in_the_golden_menu_is_a_burger(db_session):
    """The floor below comes from the recipes, not from a number someone picked."""
    g = gr.build_skeleton(db_session)
    smallest = min(q for items in gr.RECIPES.values() for name, q in items if name == "Beef")
    assert smallest == 0.18


def test_a_gap_under_one_serving_is_not_flagged_even_over_the_percentage(db_session):
    g = gr.build_skeleton(db_session)
    _stews(db_session, g, 8, drawn=2.15)                       # expected 2.0 kg, 0.15 kg over: 7.5%, less than a 0.18 kg burger
    beef = _beef(db_session, g)
    assert beef.variance_pct == pytest.approx(0.075) and beef.variance_pct > DEFAULTS.missing_stock_flag_pct / 100
    assert beef.flagged is False
    assert flagged_items(db_session, g.rid, hours=WINDOW) == []


def test_a_gap_of_a_serving_or_more_is_flagged(db_session):
    g = gr.build_skeleton(db_session)
    _stews(db_session, g, 8, drawn=2.5)                        # 0.5 kg over: 25%, nearly three burgers
    beef = _beef(db_session, g)
    assert beef.flagged is True
    assert [i.item_name for i in flagged_items(db_session, g.rid, hours=WINDOW)] == ["Beef"]


def test_a_gap_of_exactly_one_serving_is_flagged(db_session):
    g = gr.build_skeleton(db_session)
    _stews(db_session, g, 16, drawn=4.18)                      # 0.18 kg over, exactly the smallest portion (4.18 - 4.0 is 0.17999999999999972 in floats)
    assert _beef(db_session, g).flagged is True


def test_a_shortfall_under_one_serving_is_not_flagged_either(db_session):
    """Less used than the sales explain is the same rounding in the other direction."""
    g = gr.build_skeleton(db_session)
    _stews(db_session, g, 8, drawn=1.85)
    beef = _beef(db_session, g)
    assert beef.variance_pct == pytest.approx(0.075) and beef.flagged is False


def test_the_percentage_still_decides_for_a_big_base(db_session):
    """The big-base case the engine was built for: 5% of 30 kg is 1.5 kg, many servings, and the owner's line decides."""
    g = gr.build_skeleton(db_session)
    gr.seed_beef_variance(db_session, g)
    beef = _beef(db_session, g)
    assert beef.flagged is True
    assert [i.item_name for i in flagged_items(db_session, g.rid, hours=WINDOW)] == ["Beef"]
