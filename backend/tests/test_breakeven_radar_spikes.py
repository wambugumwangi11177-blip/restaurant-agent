"""
S3.3 — costs covered (break-even), the bill radar and cost spikes: owner/money/{breakeven,radar,spikes}.py.

The worked examples (#9, #14) are pinned in tests/evals/test_e2_money_goldens.py; the planted scenarios P9, P10 in E4. This pins
the rules around them — what the reference month is, what counts as fixed, when a bill is paid, what a shortfall is, and the
cases where the honest answer is "not enough to say".
"""
from datetime import date, datetime, timedelta
from fractions import Fraction

import pytest

import models
from owner.money.breakeven import break_even, break_even_sales_cents, todays_progress
from owner.money.radar import bill_radar
from owner.money.spikes import expense_spike_pct, expense_spikes
from tests.fixtures import golden_restaurant as gr

TODAY = date(2026, 10, 3)
NOW = datetime(2026, 9, 25, 10, 0)              # September's data is seeded relative to this; "today" below is early October


def _g(db, suffix="gold", now=NOW):
    return gr.build_skeleton(db, now=now, suffix=suffix)


# ── break-even: the formula ──────────────────────────────────────────────────

@pytest.mark.parametrize("fixed,pct,expected", [
    (800_000, 32.0, 1_176_471), (800_000, 0.0, 800_000), (0, 30.0, 0), (1, 99.0, 100), (10_000, 50.0, 20_000),
    (123_457, 33.3, 185_093), (800_000, 100.0, None), (800_000, 140.0, None), (800_000, None, None)])
def test_break_even_is_fixed_costs_over_what_is_left_of_each_shilling(fixed, pct, expected):
    assert break_even_sales_cents(fixed, pct) == expected


def test_break_even_is_exact_and_rounds_half_up_to_the_cent():
    for fixed, pct in ((800_000, 32.0), (123_457, 33.3), (999_999, 28.7)):
        exact = Fraction(fixed) / (1 - Fraction(str(pct)) / 100)
        got = break_even_sales_cents(fixed, pct)
        assert abs(got - exact) <= Fraction(1, 2)
    with pytest.raises(ValueError):
        break_even_sales_cents(-1, 30.0)


# ── break-even: the reference month ──────────────────────────────────────────

def test_break_even_is_built_from_the_last_complete_month(db_session):
    """September (§7 #13): fixed lines 91,500 + wages 103,000 = 194,500 → 6,483.33 a day; ingredients 32.0% → KES 9,534 of sales."""
    g = _g(db_session)
    gr.seed_pnl_month(db_session, g)
    be = break_even(db_session, g.rid, TODAY)
    assert be["basis"]["kind"] == "last_month" and be["basis"]["label"] == "September 2026" and be["basis"]["days"] == 30
    assert be["basis"]["fixed_costs_cents"] == 19_450_000 and be["basis"]["labour_fixed_cents"] == 10_300_000 and be["basis"]["labour_basis"] == "shifts"
    assert be["fixed_per_day_cents"] == 648_333 and be["food_cost_pct"] == 32.0
    assert be["break_even_cents"] == break_even_sales_cents(648_333, 32.0) == 953_431
    assert {l["key"] for l in be["basis"]["fixed_lines"]} == {"premises", "kplc", "water", "security", "licences"}      # gas, marketing, repairs move with trade


def test_the_month_so_far_is_used_when_there_is_no_complete_month(db_session):
    g = _g(db_session, now=datetime(2026, 10, 25, 10, 0))
    gr.seed_pnl_month(db_session, g)
    be = break_even(db_session, g.rid, date(2026, 10, 25))
    assert be["basis"]["kind"] == "month_so_far" and be["basis"]["label"] == "October 2026 so far" and be["basis"]["days"] == 25
    assert be["fixed_per_day_cents"] == round(19_450_000 / 25)


def test_no_costs_or_no_sales_means_no_break_even(db_session):
    g = _g(db_session)
    assert break_even(db_session, g.rid, TODAY) is None
    pilau = g.items["Pilau"]
    gr.add_order(db_session, g, [(pilau, 5, pilau.price)], NOW - timedelta(days=3))
    db_session.commit()
    assert break_even(db_session, g.rid, TODAY) is None                                   # sales, but no cost entered yet
    gr.seed_expenses(db_session, g, [("premises", 6_000_000)], paid_on=date(2026, 9, 4))
    assert break_even(db_session, g.rid, TODAY)["fixed_per_day_cents"] == 200_000


def test_fixed_costs_follow_the_owners_own_fixed_flag(db_session):
    g = _g(db_session)
    gr.seed_pnl_month(db_session, g)
    base = break_even(db_session, g.rid, TODAY)["basis"]["fixed_costs_cents"]
    gas = db_session.query(models.ExpenseCategory).filter_by(restaurant_id=g.rid, key="gas").one()
    gas.is_fixed = True
    db_session.commit()
    assert break_even(db_session, g.rid, TODAY)["basis"]["fixed_costs_cents"] == base + 950_000


def test_entered_salaries_replace_the_shifts_as_the_fixed_wages(db_session):
    g = _g(db_session)
    gr.seed_pnl_month(db_session, g)
    gr.seed_expenses(db_session, g, [("salaries", 9_000_000), ("casuals", 800_000)], paid_on=date(2026, 9, 28))
    be = break_even(db_session, g.rid, TODAY)
    assert be["basis"]["labour_basis"] == "entered" and be["basis"]["labour_fixed_cents"] == 9_000_000      # casual labour moves with trade


# ── break-even: today's progress ─────────────────────────────────────────────

def test_todays_sales_cross_the_line_at_the_order_that_gets_them_there(db_session):
    g = _g(db_session, now=datetime(2026, 10, 3, 14, 0))
    pilau = g.items["Pilau"]
    for hour, qty in ((6, 10), (8, 10), (9, 10)):                         # 06:00, 08:00, 09:00 UTC = 09:00, 11:00, 12:00 in Nairobi
        gr.add_order(db_session, g, [(pilau, qty, 35_000)], datetime(2026, 10, 3, hour, 0))
    gr.add_order(db_session, g, [(pilau, 50, 35_000)], datetime(2026, 10, 3, 10, 0), paid=False, status=models.OrderStatus.PREP)       # not paid: not sales
    gr.add_order(db_session, g, [(pilau, 50, 35_000)], datetime(2026, 10, 3, 10, 5), status=models.OrderStatus.CANCELLED)
    gr.add_order(db_session, g, [(pilau, 10, 35_000)], datetime(2026, 10, 2, 20, 59))                                                 # 23:59 yesterday in Nairobi
    db_session.commit()
    p = todays_progress(db_session, g.rid, 800_000, date(2026, 10, 3))
    assert p["sales_so_far_cents"] == 1_050_000 and p["crossed_at"] == datetime(2026, 10, 3, 9, 0) and p["to_go_cents"] == 0     # 350k, 700k, 1,050k: the third order gets past 800k
    p = todays_progress(db_session, g.rid, 2_000_000, date(2026, 10, 3))
    assert p["crossed_at"] is None and p["to_go_cents"] == 950_000


# ── spikes ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("this,prior,expected", [(1_860_000, [1_460_000, 1_410_000, 1_430_000], 29.8), (1_000, [1_000], 0.0), (1_250, [1_000, 1_000, 1_000], 25.0),
                                                 (500, [1_000, 1_000, 1_000], -50.0), (1, [], None), (100, [0, 0, 0], None), (0, [100, 100], -100.0)])
def test_the_spike_percentage(this, prior, expected):
    assert expense_spike_pct(this, prior) == expected


def _gas(db, g, this_month, prior=(1_460_000, 1_410_000, 1_430_000), today=date(2026, 10, 12)):
    for i, cents in enumerate(prior):                              # July, August, September
        gr.seed_expenses(db, g, [("gas", cents)], paid_on=date(2026, 7 + i, 14))
    if this_month:
        gr.seed_expenses(db, g, [("gas", this_month)], paid_on=date(2026, 10, 5))


def test_gas_30_percent_above_its_three_month_average_is_flagged(db_session):
    g = _g(db_session)
    _gas(db_session, g, 1_860_000)
    out = expense_spikes(db_session, g.rid, date(2026, 10, 12))
    assert out["eligible"] == 1 and out["threshold_pct"] == 25.0
    (spike,) = out["spikes"]
    assert (spike["key"], spike["name"], spike["this_month_cents"], spike["usual_cents"], spike["pct"], spike["extra_cents"]) == \
        ("gas", "Cooking gas", 1_860_000, 1_433_333, 29.8, 426_667)
    assert out["months"] == ["2026-07-01", "2026-08-01", "2026-09-01"]


def test_the_owners_threshold_decides(db_session):
    from owner.settings import update_settings
    g = _g(db_session)
    _gas(db_session, g, 1_860_000)
    update_settings(db_session, g.rid, g.owner.id, {"expense_spike_pct": 30})
    assert expense_spikes(db_session, g.rid, date(2026, 10, 12))["spikes"] == []              # 29.8 is under 30
    update_settings(db_session, g.rid, g.owner.id, {"expense_spike_pct": 10})
    assert len(expense_spikes(db_session, g.rid, date(2026, 10, 12))["spikes"]) == 1


def test_a_partial_month_under_the_usual_is_not_finished_and_not_flagged(db_session):
    g = _g(db_session)
    _gas(db_session, g, 700_000)
    assert expense_spikes(db_session, g.rid, date(2026, 10, 12))["spikes"] == []
    _gas_none = _g(db_session, "other")
    _gas(db_session, _gas_none, 0)
    assert expense_spikes(db_session, _gas_none.rid, date(2026, 10, 12))["spikes"] == []


def test_a_cost_needs_all_three_prior_months_before_it_has_a_usual(db_session):
    g = _g(db_session)
    gr.seed_expenses(db_session, g, [("gas", 1_400_000)], paid_on=date(2026, 8, 14))
    gr.seed_expenses(db_session, g, [("gas", 1_400_000)], paid_on=date(2026, 9, 14))                 # no July
    gr.seed_expenses(db_session, g, [("gas", 9_000_000)], paid_on=date(2026, 10, 5))
    out = expense_spikes(db_session, g.rid, date(2026, 10, 12))
    assert out["eligible"] == 0 and out["spikes"] == []
    assert out["history_days"] == (date(2026, 10, 12) - date(2026, 8, 14)).days + 1


def test_voided_entries_and_other_restaurants_do_not_count(db_session):
    a, b = _g(db_session, "a"), _g(db_session, "b")
    _gas(db_session, a, 1_860_000)
    _gas(db_session, b, 0, prior=(1_000_000, 1_000_000, 1_000_000))
    gr.seed_expenses(db_session, b, [("gas", 9_000_000)], paid_on=date(2026, 10, 5))
    voided = db_session.query(models.Expense).filter(models.Expense.restaurant_id == a.rid, models.Expense.amount_cents == 1_860_000).one()
    voided.voided_at = NOW
    db_session.commit()
    assert expense_spikes(db_session, a.rid, date(2026, 10, 12))["spikes"] == []
    assert [s["key"] for s in expense_spikes(db_session, b.rid, date(2026, 10, 12))["spikes"]] == ["gas"]
    assert expense_spikes(db_session, b.rid, date(2026, 10, 12))["spikes"][0]["this_month_cents"] == 9_000_000


# ── the bill radar ───────────────────────────────────────────────────────────

def _bill(db, g, name, cents, due_day, key="premises", freq="monthly"):
    db_cat = db.query(models.ExpenseCategory).filter_by(restaurant_id=g.rid, key=key).first()
    if db_cat is None:
        from owner.money.categories import ensure_categories
        ensure_categories(db, g.rid)
        db_cat = db.query(models.ExpenseCategory).filter_by(restaurant_id=g.rid, key=key).one()
    b = models.RecurringBill(restaurant_id=g.rid, category_id=db_cat.id, name=name, amount_cents=cents, frequency=freq, due_day=due_day,
                             start_on=date(2026, 1, 1), supplier="", note="", is_active=True)
    db.add(b)
    db.commit()
    return b


RADAR_TODAY = date(2026, 10, 1)


def _flat(sales_cents, days=30):
    return {RADAR_TODAY + timedelta(days=i): sales_cents for i in range(days)}


def _radar(db, g, forecast, **kw):
    gr.seed_pnl_month(db, g)                                       # September: ingredients 32.0%, wages 103,000 / 30 days = 343,333 cents a day
    return bill_radar(db, g.rid, RADAR_TODAY, forecast=forecast, **kw)


def test_rent_on_the_4th_dips_the_balance_below_zero_and_says_by_how_much(db_session):
    """Figure R4: forecast sales − bills due; 'you'll be KES x short on the 4th'. Opening cash 0 (nothing set aside)."""
    g = _g(db_session)
    _bill(db_session, g, "Rent", 7_000_000, 4)
    _bill(db_session, g, "Supplier", 1_200_000, 11, key="repairs")
    r = _radar(db_session, g, _flat(1_500_000))
    assert r["available"] and r["opening_cents"] == 0 and r["horizon_days"] == 30 and len(r["days"]) == 30
    assert r["food_cost_pct"] == 32.0 and r["food_cost_assumed"] is False and r["wages_per_day_cents"] == 343_333
    per_day = 1_020_000 - 343_333                                  # 15,000 × 0.68 − 3,433.33 wages
    assert r["days"][0]["left_after_costs_cents"] == per_day == 676_667
    assert [d["balance_cents"] for d in r["days"][:4]] == [per_day, 2 * per_day, 3 * per_day, 4 * per_day - 7_000_000]
    (first, second) = r["shortfalls"][0], r["shortfalls"][1] if len(r["shortfalls"]) > 1 else None
    assert first["date"] == "2026-10-04" and first["short_by_cents"] == 7_000_000 - 4 * per_day and first["bills"] == ["Rent"]
    assert r["lowest"] == {"date": "2026-10-04", "balance_cents": 4 * per_day - 7_000_000}
    assert [(u["name"], u["due_on"], u["days_away"]) for u in r["upcoming"]] == [("Rent", "2026-10-04", 3), ("Supplier", "2026-10-11", 10)]
    assert r["days"][-1]["balance_cents"] == 30 * per_day - 7_000_000 - 1_200_000                  # and it recovers: 30 days of sales cover both


def test_cash_kept_aside_for_bills_is_the_opening_position(db_session):
    from owner.settings import update_settings
    g = _g(db_session)
    _bill(db_session, g, "Rent", 7_000_000, 4)
    update_settings(db_session, g.rid, g.owner.id, {"bill_reserve_kes": 50_000})
    r = _radar(db_session, g, _flat(1_500_000))
    assert r["opening_cents"] == 5_000_000
    assert r["shortfalls"] == [] and r["days"][3]["balance_cents"] == 5_000_000 + 4 * 676_667 - 7_000_000 > 0
    what_if = bill_radar(db_session, g.rid, RADAR_TODAY, forecast=_flat(1_500_000), opening_cents=0)                      # "and if I keep nothing aside?"
    assert what_if["opening_cents"] == 0 and what_if["shortfalls"][0]["date"] == "2026-10-04"


def test_a_bill_already_paid_is_not_due_again(db_session):
    g = _g(db_session)
    rent = _bill(db_session, g, "Rent", 7_000_000, 4)
    paid = models.Expense(restaurant_id=g.rid, category_id=rent.category_id, amount_cents=7_000_000, paid_on=date(2026, 9, 29), method="bank",
                          bill_id=rent.id, supplier="", note="")
    db_session.add(paid)
    db_session.commit()
    r = _radar(db_session, g, _flat(1_500_000))
    assert r["upcoming"] == [] and r["shortfalls"] == []                                  # paid on 29 Sept for the 4th: nothing owed
    paid.voided_at = NOW
    db_session.commit()
    assert [u["name"] for u in bill_radar(db_session, g.rid, RADAR_TODAY, forecast=_flat(1_500_000))["upcoming"]] == ["Rent"]          # void it: due again
    other = _bill(db_session, g, "KPLC", 1_800_000, 20, key="kplc")
    assert [u["name"] for u in bill_radar(db_session, g.rid, RADAR_TODAY, forecast=_flat(1_500_000))["upcoming"]] == ["Rent", "KPLC"]


def test_weekly_bills_fall_due_every_week_and_switched_off_bills_never(db_session):
    g = _g(db_session)
    _bill(db_session, g, "Fish supplier", 500_000, 2, key="repairs", freq="weekly")                      # Wednesdays
    off = _bill(db_session, g, "Old contract", 9_000_000, 10)
    off.is_active = False
    db_session.commit()
    r = _radar(db_session, g, _flat(1_500_000))
    assert [u["due_on"] for u in r["upcoming"]] == ["2026-10-07", "2026-10-14", "2026-10-21", "2026-10-28"]


def test_when_salaries_are_a_bill_wages_are_not_taken_off_twice(db_session):
    g = _g(db_session)
    _bill(db_session, g, "Payroll", 10_000_000, 25, key="salaries")
    r = _radar(db_session, g, _flat(1_500_000))
    assert r["salaries_are_a_bill"] is True and r["wages_per_day_cents"] == 0 and r["days"][0]["left_after_costs_cents"] == 1_020_000


def test_the_radar_says_so_when_it_cannot_look(db_session):
    g = _g(db_session)
    assert bill_radar(db_session, g.rid, RADAR_TODAY, forecast=_flat(100)) == {"available": False, "reason": "no_bills"}
    _bill(db_session, g, "Rent", 7_000_000, 4)
    assert bill_radar(db_session, g.rid, RADAR_TODAY)["available"] is False                           # no sales history to forecast from
    r = bill_radar(db_session, g.rid, RADAR_TODAY, forecast=_flat(1_000_000))                          # no reference month: the owner's own target stands in
    assert r["food_cost_assumed"] is True and r["food_cost_pct"] == 35.0 and r["wages_per_day_cents"] == 0


def test_the_radar_is_one_restaurants_only(db_session):
    a, b = _g(db_session, "a"), _g(db_session, "b")
    _bill(db_session, a, "Rent", 7_000_000, 4)
    assert bill_radar(db_session, b.rid, RADAR_TODAY, forecast=_flat(1_000_000)) == {"available": False, "reason": "no_bills"}
