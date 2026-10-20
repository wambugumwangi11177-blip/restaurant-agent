"""
The four small sums behind SPEC §7 #4, #10, #11, #12 (owner/menu_math.py, owner/kitchen.py).

The spec's own numbers are pinned in tests/evals/test_e2_money_goldens.py; these tests are about the edges the worked examples do not touch: the
price step is an input, a price is never below its target and one step lower would be, a negative order is not an order, and bad input is refused
in words instead of becoming a quiet wrong number.
"""
from fractions import Fraction

import pytest

from owner.kitchen import market_list, prep_raw_quantity
from owner.menu_math import combo_margin_pct, combo_summary, month_gain_cents, target_price_cents
from owner.settings import DEFAULTS

STEP = DEFAULTS.price_step_cents                   # the owner's rounding step (KES 5), a setting and not a number in these sums
FLOOR = DEFAULTS.margin_floor_pct


# ── target price ─────────────────────────────────────────────────────────────

def test_target_price_on_each_step():
    assert target_price_cents(26_000, 55.0, step_cents=100) == 57_800        # §7 #4
    assert target_price_cents(26_000, 55.0, STEP) == 58_000                  # the owner's default KES 5 step
    assert target_price_cents(26_000, 40.0, STEP) == 43_500                  # §7 #3: 433.33 → 435
    assert target_price_cents(26_000, 40.0, step_cents=1) == 43_334          # to the cent, rounded up


def test_target_price_that_is_already_on_a_step_is_not_pushed_up():
    assert target_price_cents(30_000, 40.0, step_cents=500) == 50_000        # exactly 500.00
    assert target_price_cents(0, 50.0, STEP) == 0


@pytest.mark.parametrize("cost", [1, 99, 26_000, 123_457, 9_999_999])
@pytest.mark.parametrize("margin", [0.0, 12.5, 33.3, 40.0, 55.0, 70.0, 94.9])
@pytest.mark.parametrize("step", [1, 100, 500])
def test_target_price_is_the_lowest_price_on_the_step_that_keeps_the_margin(cost, margin, step):
    price = target_price_cents(cost, margin, step)
    assert price % step == 0
    keeps = lambda p: Fraction(p - cost, p) * 100 >= Fraction(str(margin)) if p > 0 else False
    assert keeps(price)                                                       # never below the target
    if price - step > 0:
        assert not keeps(price - step)                                        # and one step lower would be


def test_month_gain():
    assert month_gain_cents(40_000, 57_800, 300) == 5_340_000                # KES 53,400
    assert month_gain_cents(40_000, 40_000, 300) == 0
    assert month_gain_cents(40_000, 35_000, 100) == -500_000                 # a cut is a negative gain, not an error
    with pytest.raises(ValueError):
        month_gain_cents(40_000, 50_000, -1)


@pytest.mark.parametrize("args", [(-1, 40.0), (100, -0.1), (100, 95.0), (100, 120.0)])
def test_target_price_refuses_nonsense(args):
    with pytest.raises(ValueError):
        target_price_cents(*args, STEP)


def test_the_thresholds_are_not_defaulted_here():
    """SPEC §0.3: one source of truth for thresholds. The caller passes the owner's step and floor; leaving one out is a TypeError, not a quiet 500 / 40."""
    with pytest.raises(TypeError):
        target_price_cents(26_000, 55.0)
    with pytest.raises(TypeError):
        combo_summary([65_000, 55_000], 105_000, [26_000, 20_000])


def test_target_price_refuses_a_step_below_one_cent():
    with pytest.raises(ValueError):
        target_price_cents(26_000, 40.0, step_cents=0)


# ── combo ────────────────────────────────────────────────────────────────────

def test_combo_margin_and_summary():
    assert combo_margin_pct(105_000, [26_000, 20_000]) == 56.2
    s = combo_summary([65_000, 55_000], 105_000, [26_000, 20_000], FLOOR)
    assert s == {"regular_cents": 120_000, "combo_cents": 105_000, "discount_cents": 15_000, "cost_cents": 46_000,
                 "margin_pct": 56.2, "above_floor": True}


def test_combo_below_the_floor_says_so():
    s = combo_summary([65_000, 55_000], 70_000, [26_000, 20_000], FLOOR)
    assert s["margin_pct"] == 34.3 and s["above_floor"] is False
    assert combo_summary([65_000, 55_000], 70_000, [26_000, 20_000], 30.0)["above_floor"] is True


def test_combo_that_loses_money_is_a_negative_margin_not_an_error():
    assert combo_margin_pct(40_000, [26_000, 20_000]) == -15.0


def test_combo_floor_is_inclusive():
    assert combo_summary([1, 1], 100, [60, 0], 40.0)["above_floor"] is True


@pytest.mark.parametrize("price,costs", [(0, [1, 2]), (-5, [1, 2]), (1_000, [1]), (1_000, []), (1_000, [10, -1])])
def test_combo_refuses_nonsense(price, costs):
    with pytest.raises(ValueError):
        combo_margin_pct(price, costs)


# ── prep quantity ────────────────────────────────────────────────────────────

def test_prep_quantity_spec_example_and_no_loss():
    assert prep_raw_quantity(45, 0.25, 0.80) == 14.06
    assert prep_raw_quantity(45, 0.25, 1.0) == 11.25                        # a yield of 1 is "nothing is lost": raw = cooked
    assert prep_raw_quantity(0, 0.25, 0.80) == 0.0


def test_prep_quantity_rounds_half_up_not_to_even():
    assert prep_raw_quantity(1, 0.125, 1.0, places=2) == 0.13               # banker's rounding would give 0.12
    assert prep_raw_quantity(1, 0.125, 1.0, places=3) == 0.125


@pytest.mark.parametrize("portions", [1, 7, 45, 200])
@pytest.mark.parametrize("yield_fraction", [0.5, 0.7, 0.8, 0.95, 1.0])
def test_prep_raw_is_never_less_than_cooked(portions, yield_fraction):
    assert prep_raw_quantity(portions, 0.25, yield_fraction, places=4) + 1e-9 >= portions * 0.25


@pytest.mark.parametrize("args", [(-1, 0.25, 0.8), (10, -0.25, 0.8), (10, 0.25, 0), (10, 0.25, -0.5), (10, 0.25, 1.2)])
def test_prep_quantity_refuses_nonsense(args):
    with pytest.raises(ValueError):
        prep_raw_quantity(*args)


# ── market list ──────────────────────────────────────────────────────────────

def _line(item, need, buffer, on_hand, unit="kg"):
    return {"item": item, "unit": unit, "need": need, "buffer": buffer, "on_hand": on_hand}


def test_market_list_spec_example():
    rows = market_list([_line("Beef", 14, 5, 8), _line("Chicken", 60, 20, 32), _line("Tomatoes", 6, 2, 1), _line("Rice", 13.5, 10, 25)])
    assert [(r["item"], r["buy"]) for r in rows] == [("Beef", 11), ("Chicken", 48), ("Tomatoes", 7), ("Rice", 0)]


def test_market_list_keeps_the_input_fields_and_does_not_change_the_input():
    src = [_line("Beef", 14, 5, 8)]
    rows = market_list(src)
    assert rows[0]["unit"] == "kg" and rows[0]["need"] == 14 and rows[0]["on_hand"] == 8
    assert "buy" not in src[0]


def test_market_list_missing_buffer_and_on_hand_default_to_zero():
    assert market_list([{"item": "Salt", "unit": "kg", "need": 2}])[0]["buy"] == 2


def test_market_list_decimals_do_not_drift():
    # 0.1 + 0.2 − 0.3 is 5.5e-17 in floats; it must come out as exactly nothing to buy
    assert market_list([_line("Spice", 0.1, 0.2, 0.3)])[0]["buy"] == 0


@pytest.mark.parametrize("need,buffer,on_hand", [(0, 0, 0), (1, 0, 5), (3, 2, 9.5), (14, 5, 8), (0.5, 0.5, 0.25)])
def test_market_list_is_never_negative(need, buffer, on_hand):
    buy = market_list([_line("X", need, buffer, on_hand)])[0]["buy"]
    assert buy >= 0
    assert buy == max(round(need + buffer - on_hand, 2), 0)


@pytest.mark.parametrize("line", [_line("X", -1, 0, 0), _line("X", 1, -1, 0), _line("X", 1, 0, -1)])
def test_market_list_refuses_negative_quantities(line):
    with pytest.raises(ValueError, match="X"):
        market_list([line])
