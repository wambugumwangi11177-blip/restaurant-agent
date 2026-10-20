"""
S3.2 — the Profit & Loss engine (owner/money/pnl.py) and its owner surfaces (docs/v2/SPEC.md S3.2, §7 #1, #2, #13).

The three worked examples are pinned exactly in tests/evals/test_e2_money_goldens.py. This file pins the rules around them:
periods, Nairobi day boundaries, what is a sale, where ingredients / wages / commissions come from, what a missing cost is,
and that the lines always add up.
"""
from datetime import date, datetime, timedelta

import pytest

import models
from owner.money.pnl import compute_pnl, nairobi_utc_range, pct, period_range
from tests.fixtures import golden_restaurant as gr

NOW = datetime(2026, 10, 14, 10, 0)             # Wednesday 13:00 in Nairobi
TODAY = date(2026, 10, 14)


def _g(db, suffix="gold"):
    return gr.build_skeleton(db, now=NOW, suffix=suffix)


def _pnl(db, g, start=date(2026, 10, 1), end=date(2026, 10, 31), **kw):
    return compute_pnl(db, g.rid, start, end, today=TODAY, **kw)


def _sell(db, g, dish, qty, at, price=None, **kw):
    item = g.items[dish]
    gr.add_order(db, g, [(item, qty, item.price if price is None else price)], at, **kw)
    db.commit()


# ── periods and percentages ──────────────────────────────────────────────────

def test_periods_are_calendar_periods():
    assert period_range("day", date(2026, 10, 14)) == (date(2026, 10, 14), date(2026, 10, 14))
    assert period_range("week", date(2026, 10, 14)) == (date(2026, 10, 12), date(2026, 10, 18))          # Monday .. Sunday
    assert period_range("week", date(2026, 10, 18)) == (date(2026, 10, 12), date(2026, 10, 18))
    assert period_range("month", date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert period_range("month", date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))
    assert period_range("year", date(2026, 10, 14)) == (date(2026, 1, 1), date(2026, 12, 31))
    with pytest.raises(ValueError):
        period_range("fortnight", TODAY)


def test_a_nairobi_day_is_21_hours_into_the_previous_utc_day():
    lo, hi = nairobi_utc_range(date(2026, 10, 14), date(2026, 10, 14))
    assert (lo, hi) == (datetime(2026, 10, 13, 21, 0), datetime(2026, 10, 14, 21, 0))


@pytest.mark.parametrize("part,whole,expected", [(1500, 10000, 15.0), (32_000, 105_000, 30.5), (25_000, 105_000, 23.8), (20_000, 105_000, 19.0),
                                                 (6_520_000, 41_200_000, 15.8), (1, 8, 12.5), (1, 16, 6.3), (0, 100, 0.0), (-500, 10_000, -5.0), (5, 0, None)])
def test_percentages_round_half_up_to_one_decimal(part, whole, expected):
    assert pct(part, whole) == expected


# ── sales ────────────────────────────────────────────────────────────────────

def test_an_order_belongs_to_its_nairobi_day(db_session):
    """00:30 in Nairobi on the 15th is 21:30 UTC on the 14th: it is the 15th's sale, not the 14th's."""
    g = _g(db_session)
    _sell(db_session, g, "Pilau", 1, datetime(2026, 10, 14, 21, 30))
    assert _pnl(db_session, g, date(2026, 10, 14), date(2026, 10, 14))["sales_cents"] == 0
    assert _pnl(db_session, g, date(2026, 10, 15), date(2026, 10, 15))["sales_cents"] == g.items["Pilau"].price
    _sell(db_session, g, "Pilau", 1, datetime(2026, 10, 14, 20, 59))              # 23:59 in Nairobi on the 14th
    assert _pnl(db_session, g, date(2026, 10, 14), date(2026, 10, 14))["sales_cents"] == g.items["Pilau"].price


def test_only_paid_orders_that_were_not_cancelled_are_sales(db_session):
    g = _g(db_session)
    at = NOW - timedelta(hours=2)
    _sell(db_session, g, "Pilau", 2, at)
    _sell(db_session, g, "Pilau", 1, at, paid=False, status=models.OrderStatus.PREP)
    _sell(db_session, g, "Pilau", 1, at, paid=False, status=models.OrderStatus.CANCELLED)
    _sell(db_session, g, "Pilau", 1, at, status=models.OrderStatus.CANCELLED)
    p = _pnl(db_session, g)
    assert p["sales_cents"] == 2 * g.items["Pilau"].price and p["orders"] == 1
    assert p["ingredients_cents"] == 2 * g.items["Pilau"].cost_price


def test_sales_split_into_food_and_drinks_and_nothing_is_lost(db_session):
    g = _g(db_session)
    soda = models.MenuItem(restaurant_id=g.rid, name="Soda", category="Drinks", price=12_000, cost_price=4_500, is_available=True)
    db_session.add(soda)
    db_session.flush()
    gr.add_order(db_session, g, [(g.items["Pilau"], 1, 35_000), (soda, 2, 12_000)], NOW - timedelta(hours=1))
    db_session.commit()
    p = _pnl(db_session, g)
    assert (p["food_sales_cents"], p["drinks_sales_cents"], p["other_income_cents"]) == (35_000, 24_000, 0)
    assert p["food_sales_cents"] + p["drinks_sales_cents"] + p["other_income_cents"] == p["sales_cents"]
    order = db_session.query(models.Order).one()
    order.total += 5_000                                                      # a service charge that is not a dish
    db_session.commit()
    p = _pnl(db_session, g)
    assert p["other_income_cents"] == 5_000 and p["sales_cents"] == 64_000


# ── ingredients ──────────────────────────────────────────────────────────────

def test_ingredients_are_recipe_cost_times_dishes_sold_and_dishes_with_no_cost_are_named(db_session):
    g = _g(db_session)
    free = models.MenuItem(restaurant_id=g.rid, name="Mystery stew", category="Mains", price=50_000, cost_price=0, is_available=True)
    db_session.add(free)
    db_session.flush()
    gr.add_order(db_session, g, [(g.items["Pilau"], 3, 35_000), (free, 4, 50_000)], NOW - timedelta(hours=1))
    db_session.commit()
    p = _pnl(db_session, g)
    assert p["ingredients_cents"] == 3 * g.items["Pilau"].cost_price and p["ingredients_basis"] == "recipe"
    assert p["missing_costs"] == [{"dish": "Mystery stew", "units": 4, "sales_cents": 200_000}]
    assert p["gross_profit_cents"] == p["sales_cents"] - p["ingredients_cents"]           # the missing cost makes profit look bigger: and is flagged


def _purchase(db, g, total_cents, at):
    db.add(models.PurchaseOrder(restaurant_id=g.rid, supplier_id=g.supplier.id, inventory_item_id=g.inventory["Beef"].id, quantity_ordered=10,
                                quantity_received=10, unit="kg", cost_per_unit=total_cents // 10, total_cost=total_cents, status="DELIVERED",
                                ordered_at=at - timedelta(days=1), expected_at=at, delivered_at=at))
    db.commit()


def test_when_almost_no_dish_has_a_cost_ingredients_come_from_purchases_and_say_so(db_session):
    g = _g(db_session)
    for item in g.items.values():
        item.cost_price = 0
    db_session.commit()
    _sell(db_session, g, "Pilau", 10, NOW - timedelta(hours=1))
    assert _pnl(db_session, g)["ingredients_cents"] == 0                      # nothing to go on yet
    _purchase(db_session, g, 1_234_500, NOW - timedelta(days=2))
    _purchase(db_session, g, 99_999, NOW - timedelta(days=60))               # last quarter: not this month
    p = _pnl(db_session, g)
    assert (p["ingredients_cents"], p["ingredients_basis"]) == (1_234_500, "purchases")
    for item in g.items.values():                                             # once the dishes are costed, recipes win again
        item.cost_price = 10_000
    db_session.commit()
    p = _pnl(db_session, g)
    assert p["ingredients_basis"] == "recipe" and p["ingredients_cents"] == 100_000


# ── wages ────────────────────────────────────────────────────────────────────

def _shift(db, g, day, cost):
    m = db_staff(db, g)
    db.add(models.LaborShift(restaurant_id=g.rid, staff_member_id=m.id, shift_date=day, scheduled_hours=8.0, actual_hours=8.0, labor_cost=cost))
    db.commit()


def db_staff(db, g):
    m = db.query(models.StaffMember).filter_by(restaurant_id=g.rid).first()
    if m is None:
        m = models.StaffMember(restaurant_id=g.rid, name="Crew", role_title="Waiter", hourly_rate=12_500)
        db.add(m)
        db.flush()
    return m


def test_wages_are_the_shifts_until_the_owner_enters_them_and_never_both(db_session):
    g = _g(db_session)
    _sell(db_session, g, "Pilau", 10, NOW - timedelta(hours=1))
    assert _pnl(db_session, g)["labour_basis"] == "none"
    _shift(db_session, g, date(2026, 10, 12), 100_000)
    _shift(db_session, g, date(2026, 10, 13), 100_000)
    _shift(db_session, g, date(2026, 11, 2), 100_000)                          # next month: not in this P&L
    p = _pnl(db_session, g)
    assert (p["labour_cents"], p["labour_basis"]) == (200_000, "shifts")
    gr.seed_expenses(db_session, g, [("salaries", 5_000_000), ("casuals", 300_000), ("staff_meals", 100_000)], paid_on=date(2026, 10, 10))
    p = _pnl(db_session, g)
    assert (p["labour_cents"], p["labour_basis"], p["shifts_cost_cents"]) == (5_400_000, "entered", 200_000)    # entered wins; shifts not added on top
    assert all(s["key"] != "staff" for s in p["sections"])                    # wages are not also an "other cost"


# ── delivery commissions ─────────────────────────────────────────────────────

def test_delivery_commission_is_estimated_from_the_owners_rates_until_the_real_figure_is_entered(db_session):
    from owner.settings import update_settings
    g = _g(db_session)
    burger = g.items["Burger"]
    at = NOW - timedelta(hours=2)
    gr.add_order(db_session, g, [(burger, 1, 60_000)], at, channel=models.DeliveryChannel.GLOVO, payment=models.PaymentMethod.CARD)
    gr.add_order(db_session, g, [(burger, 1, 60_000)], at, channel=models.DeliveryChannel.BOLT_FOOD, payment=models.PaymentMethod.CARD)
    gr.add_order(db_session, g, [(burger, 1, 60_000)], at)                    # dine-in: no commission
    db_session.commit()
    p = _pnl(db_session, g)
    assert (p["delivery_commission_cents"], p["delivery_commission_basis"]) == (15_000 + 12_000, "estimated")      # 25% Glovo, 20% Bolt
    fees = next(s for s in p["sections"] if s["key"] == "fees")
    assert fees["lines"][0]["name"] == "Delivery app commissions" and fees["lines"][0]["basis"] == "estimated"
    assert p["sales_after_commission_cents"] == 180_000 - 27_000
    assert p["operating_profit_cents"] == p["gross_profit_cents"] - 27_000                                         # a cost, so it lowers what you kept
    update_settings(db_session, g.rid, g.owner.id, {"commission_glovo_pct": 30})
    assert _pnl(db_session, g)["delivery_commission_cents"] == 18_000 + 12_000                                     # the owner's rate, not a constant
    gr.seed_expenses(db_session, g, [("delivery_commissions", 2_600_000)], paid_on=date(2026, 10, 10))
    p = _pnl(db_session, g)
    assert (p["delivery_commission_cents"], p["delivery_commission_basis"]) == (2_600_000, "entered")              # the real figure replaces the estimate


# ── other costs ──────────────────────────────────────────────────────────────

def test_other_costs_are_grouped_by_section_and_line_and_voided_ones_are_left_out(db_session):
    g = _g(db_session)
    _sell(db_session, g, "Pilau", 10, NOW - timedelta(hours=1))
    gr.seed_expenses(db_session, g, [("premises", 6_000_000), ("kplc", 1_400_000), ("kplc", 100_000), ("gas", 900_000), ("marketing", 500_000)],
                     paid_on=date(2026, 10, 10))
    gone = db_session.query(models.Expense).filter(models.Expense.amount_cents == 500_000).one()
    gone.voided_at, gone.void_reason = NOW, "entered twice"
    gr.seed_expenses(db_session, g, [("premises", 7_777_700)], paid_on=date(2026, 9, 30))                            # last month
    db_session.commit()
    p = _pnl(db_session, g)
    sections = {s["key"]: s for s in p["sections"]}
    assert set(sections) == {"premises", "utilities"}                          # no marketing: voided; nothing else entered
    assert sections["premises"]["total_cents"] == 6_000_000
    assert sections["utilities"]["total_cents"] == 1_400_000 + 100_000 + 900_000
    kplc = next(l for l in sections["utilities"]["lines"] if l["key"] == "kplc")
    assert (kplc["amount_cents"], kplc["entries"], kplc["is_fixed"]) == (1_500_000, 2, True)
    assert [l["key"] for l in sections["utilities"]["lines"]] == ["kplc", "gas"]                                      # biggest first
    assert p["other_costs_cents"] == 6_000_000 + 2_400_000


def test_the_lines_always_add_up(db_session):
    g = _g(db_session)
    gr.seed_pnl_month(db_session, g)
    gr.seed_expenses(db_session, g, [("delivery_commissions", 123_457)], paid_on=date(2026, 10, 5))
    _sell(db_session, g, "Burger", 3, NOW - timedelta(hours=1), channel=models.DeliveryChannel.UBER_EATS, payment=models.PaymentMethod.CARD)
    p = _pnl(db_session, g)
    assert p["gross_profit_cents"] == p["sales_cents"] - p["ingredients_cents"]
    assert p["operating_profit_cents"] == p["gross_profit_cents"] - p["labour_cents"] - p["other_costs_cents"] == p["net_before_tax_cents"]
    assert p["other_costs_cents"] == sum(s["total_cents"] for s in p["sections"]) == sum(l["amount_cents"] for s in p["sections"] for l in s["lines"])
    for key in ("sales_cents", "ingredients_cents", "gross_profit_cents", "labour_cents", "other_costs_cents", "operating_profit_cents", "delivery_commission_cents"):
        assert isinstance(p[key], int), key


# ── honesty: what has not been entered ───────────────────────────────────────

def test_no_costs_entered_is_not_a_profit_of_everything(db_session):
    g = _g(db_session)
    _sell(db_session, g, "Pilau", 10, NOW - timedelta(hours=1))
    p = _pnl(db_session, g)
    assert p["costs_entered"] is False and p["entered_up_to"] is None
    assert p["operating_profit_cents"] == p["gross_profit_cents"]              # the number exists, and the flag says it is not a real "kept"


def test_a_fixed_cost_entered_before_but_not_this_month_is_named(db_session):
    g = _g(db_session)
    _sell(db_session, g, "Pilau", 10, NOW - timedelta(hours=1))
    gr.seed_expenses(db_session, g, [("premises", 7_000_000), ("kplc", 1_800_000), ("gas", 400_000)], paid_on=date(2026, 9, 4))     # last month
    gr.seed_expenses(db_session, g, [("kplc", 1_900_000), ("gas", 450_000)], paid_on=date(2026, 10, 9))
    p = _pnl(db_session, g)
    assert p["missing_categories"] == [{"key": "premises", "name": "Rent & premises", "why": "entered before, nothing this period"}]    # gas is variable
    assert p["costs_entered"] is True and p["entered_up_to"] == date(2026, 10, 9)
    later = _pnl(db_session, g, date(2027, 3, 1), date(2027, 3, 31))
    assert later["missing_categories"] == []                                   # nothing entered in the 90 days before March: nothing to be missing


def test_a_period_that_has_not_ended_says_so(db_session):
    g = _g(db_session)
    p = _pnl(db_session, g, date(2026, 10, 1), date(2026, 10, 31))
    assert p["period"] == {"start": date(2026, 10, 1), "end": date(2026, 10, 31), "days": 31, "partial": True, "days_elapsed": 14}
    done = _pnl(db_session, g, date(2026, 9, 1), date(2026, 9, 30))
    assert done["period"]["partial"] is False and done["period"]["days_elapsed"] == 30
    with pytest.raises(ValueError):
        _pnl(db_session, g, date(2026, 10, 2), date(2026, 10, 1))


def test_an_empty_period_has_zeros_and_no_percentages(db_session):
    g = _g(db_session)
    p = _pnl(db_session, g, date(2026, 8, 1), date(2026, 8, 31))
    assert (p["sales_cents"], p["operating_profit_cents"], p["orders"]) == (0, 0, 0)
    assert all(p[k] is None for k in ("food_cost_pct", "labour_pct", "prime_cost_pct", "kept_pct", "gross_margin_pct"))


def test_the_pnl_is_one_restaurants_only(db_session):
    a, b = _g(db_session, "a"), _g(db_session, "b")
    _sell(db_session, a, "Pilau", 10, NOW - timedelta(hours=1))
    gr.seed_expenses(db_session, a, [("premises", 5_000_000)], paid_on=date(2026, 10, 3))
    _shift(db_session, a, date(2026, 10, 3), 100_000)
    _purchase(db_session, a, 500_000, NOW - timedelta(days=1))
    p = _pnl(db_session, b)
    assert (p["sales_cents"], p["other_costs_cents"], p["labour_cents"], p["costs_entered"]) == (0, 0, 0, False)
    assert _pnl(db_session, a)["other_costs_cents"] == 5_000_000
