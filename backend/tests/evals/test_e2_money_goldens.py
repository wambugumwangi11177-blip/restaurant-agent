"""
E2 — Money goldens (docs/v2/SPEC.md §5, §7).

Three kinds of test, so the sixteen worked examples are each pinned exactly once and nothing is
silently missing:

  LIVE         today's engines are run on the golden restaurant (tests/fixtures/golden_restaurant.py)
               and must produce today's numbers. This is characterisation: it captures behaviour
               BEFORE v2 changes it. Where today's answer differs from the spec (D16: KES 433.50 not
               435; #7: 33.3% not 25%) the live test asserts what the code does today and says so.
  PENDING      the example belongs to a later sprint. `xfail(strict=True)`: it fails today for the
               right reason (the feature does not exist) and turns the build RED the moment the
               feature lands without this test being flipped to a live assertion.
  ARITHMETIC   `TestSpecArithmetic` re-derives every spec result with exact integer / Fraction maths,
               independent of any engine, so a typo in the spec cannot hide behind a green engine.

`test_every_worked_example_has_a_golden` fails if any of the 16 has no test of any kind.
"""
import math
import re
from fractions import Fraction

import pytest

import models
from tests.fixtures import golden_restaurant as gr

# ═════════════════════════════════════════════════════════════════════════════
# LIVE — what today's engines say
# ═════════════════════════════════════════════════════════════════════════════


def test_ex01_weekly_pnl_today_gives_revenue_food_cost_gross_but_no_kept_or_prime(db_session):
    """§7 #1: 100,000 − 32,000 = 68,000 gross. Today's engines can state sales, ingredients and gross;
    'kept 15,000 (15%)' and 'prime 57%' need the P&L engine (S3.2) — see the pending test below."""
    from routers.overview import _summarize, _eat_range
    from ai.profit.intelligence import get_profit_intelligence
    from ai.labor.intelligence import get_labor_intelligence

    g = gr.build_skeleton(db_session)
    gr.seed_pnl_week(db_session, g)

    start, end = _eat_range("7d")
    assert _summarize(db_session, g.rid, start, end) == {"revenue": 100_000.0, "orders": 100}

    summary = get_profit_intelligence(db_session, g.rid)["summary"]
    assert summary["total_revenue_30d"] == 10_000_000
    assert summary["total_food_cost_30d"] == 3_200_000
    assert summary["total_gross_profit_30d"] == 6_800_000          # KES 68,000
    assert summary["gross_margin_pct"] == 68.0
    assert summary["food_cost_pct"] == 32.0

    labor = get_labor_intelligence(db_session, g.rid)["summary"]
    assert labor["total_labor_cost_30d"] == 2_500_000               # KES 25,000
    assert labor["labor_pct"] == 25.0


def test_ex02_price_rise_today_gives_food_and_labour_percentages(db_session):
    """§7 #2: same plates, +KES 5,000 of sales → food 30.5%, labour 23.8%. (opex 26.7% and profit 19.0%
    need the P&L engine — pending S3.2.)"""
    from ai.profit.intelligence import get_profit_intelligence
    from ai.labor.intelligence import get_labor_intelligence

    g = gr.build_skeleton(db_session)
    gr.seed_pnl_week(db_session, g, price_rise=True)

    assert get_profit_intelligence(db_session, g.rid)["summary"]["total_revenue_30d"] == 10_500_000
    assert get_profit_intelligence(db_session, g.rid)["summary"]["food_cost_pct"] == 30.5
    assert get_labor_intelligence(db_session, g.rid)["summary"]["labor_pct"] == 23.8


def _chicken_reprice(db_session):
    from ai.pricing.recommendations import get_pricing_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_chicken_reprice(db_session, g)
    data = get_pricing_intelligence(db_session, g.rid)
    return next(r for r in data["recommendations"] if r["item_name"] == "Quarter chicken")


def test_ex03_quarter_chicken_reprice_today_is_433_50_not_435_defect_d16(db_session):
    """§7 #3 — TODAY's answer. The spec's KES 435 / KES 10,500 needs the KES-5 step (D16, S1.3):
    260/(1−0.40) = 433.33 and today's code rounds UP to the nearest KES 0.50 → 433.50."""
    rec = _chicken_reprice(db_session)
    assert rec["type"] == "REPRICE"
    assert rec["current_price"] == 40_000 and rec["cost_price"] == 26_000
    assert rec["margin_pct"] == 35.0
    assert rec["suggested_price"] == 43_350                       # KES 433.50  (spec: 435)
    assert rec["monthly_impact_cents"] == 1_005_000                # KES 10,050 (spec: 10,500)
    assert rec["new_margin_pct"] == 40.0
    assert rec["qty_30d"] == 300


@pytest.mark.xfail(strict=True, reason="S1.3 (D16): round suggested prices up to the price_step_kes setting (5)")
def test_ex03_quarter_chicken_reprice_after_d16_is_435_and_10500(db_session):
    rec = _chicken_reprice(db_session)
    assert rec["suggested_price"] == 43_500                       # KES 435
    assert rec["monthly_impact_cents"] == 1_050_000                # KES 10,500 / month


def test_ex05_chips_sold_below_menu_price_today(db_session):
    """§7 #5: (300 − 270) × 400 × 30/14 = KES 25,714. Today the engine calls this 'portion_drift'
    (D15: it measures sales below menu price; renamed `till_price_gap` in S1.3)."""
    from ai.profit.intelligence import get_profit_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_chips_below_menu(db_session, g)

    drift = get_profit_intelligence(db_session, g.rid)["portion_drift"]
    chips = next(d for d in drift if d["item_name"] == "Chips")
    assert chips["menu_price"] == 30_000
    assert chips["avg_captured_price"] == 27_000
    assert chips["drift_pct"] == 10.0
    assert chips["order_count"] == 400
    assert chips["estimated_monthly_leak"] == 2_571_428            # KES 25,714.28 ≈ the spec's 25,714
    assert chips["estimated_monthly_leak"] == int((30_000 - 27_000) * 400 * (30 / 14))


def test_ex06_burger_delivery_keeps_170_vs_320(db_session):
    """§7 #6: Glovo takes 25% of KES 600 (150): the plate keeps 600 − 150 − 280 = 170 against 320 dine-in."""
    from ai.profit.intelligence import get_profit_intelligence
    from ai.pricing.recommendations import get_pricing_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_burger_delivery(db_session, g)

    channels = {c["channel"]: c for c in get_profit_intelligence(db_session, g.rid)["channel_analysis"]}
    glovo, walk_in = channels["glovo"], channels["walk_in"]
    assert glovo["orders"] == 6 and walk_in["orders"] == 6
    assert glovo["profit"] // glovo["orders"] == 17_000            # KES 170 per plate
    assert walk_in["profit"] // walk_in["orders"] == 32_000        # KES 320 per plate
    assert glovo["commission_included"] is True and walk_in["commission_included"] is False

    gap = next(d for d in get_pricing_intelligence(db_session, g.rid)["delivery_gaps"]
               if d["channel"] == "glovo" and d["item_name"] == "Burger")
    assert gap["commission_pct"] == 25
    assert gap["current_margin_pct"] == 53.3
    assert gap["effective_delivery_margin"] == 28.3                # below the 40% floor
    assert gap["recommended_delivery_price"] == 80_000             # KES 800 keeps the 40% floor after 25%


def test_ex07_beef_variance_10kg_missing_engine_reports_33_percent_not_25(db_session):
    """§7 #7: 50 + 30 − 40 = 40 kg used; 120 × 0.25 = 30 kg expected → 10 kg missing, flagged (> 3%).
    The spec says 25% (gap ÷ used); the engine's definition is gap ÷ EXPECTED = 33.3% (PROGRESS §0)."""
    from ai.stock_custody import compute_variance_report
    g = gr.build_skeleton(db_session)
    gr.seed_beef_variance(db_session, g)

    rows = compute_variance_report(db_session, g.rid, hours=24 * 8)
    assert len(rows) == 1
    beef = rows[0]
    assert beef.item_name == "Beef" and beef.unit == "kg"
    assert beef.theoretical_usage == pytest.approx(30.0)
    assert beef.actual_usage == pytest.approx(40.0)
    assert beef.actual_usage - beef.theoretical_usage == pytest.approx(10.0)       # 10 kg missing
    assert beef.variance_pct == pytest.approx(10 / 30)                              # engine: 33.3%
    assert 10 / 40 == 0.25                                                          # spec: 25%
    assert beef.flagged is True
    assert g.inventory["Beef"].quantity == 40.0                                     # closing count


def test_ex07b_handover_mismatch_is_disputed(db_session, monkeypatch):
    """Store declares 40 kg, kitchen counts 38 → the transfer is DISPUTED (the 'handover doesn't match' signal)."""
    from ai.stock_custody import confirm_transfer
    emitted = []
    monkeypatch.setattr("events.bus.emit_async", lambda event_type, payload: emitted.append(payload))
    g = gr.build_skeleton(db_session)
    transfer = gr.seed_handover(db_session, g)

    done = confirm_transfer(db_session, transfer.id, g.rid, g.kitchen.id, 38.0)
    assert done.status == models.StockTransferStatus.DISPUTED
    assert done.quantity == 40.0 and done.confirmed_quantity == 38.0
    assert len(emitted) == 1 and emitted[0]["declared_quantity"] == 40.0


def test_ex08_cash_tolerance_flags_520_short_but_not_150_short(db_session, monkeypatch):
    """§7 #8: tolerance = max(KES 200, 1% × KES 35,000) = KES 350; short KES 520 → flagged.
    A second KES 20,000 shift that is KES 150 short stays inside the KES 200 floor."""
    from ai.cash_reconciliation.intelligence import record_drawer_count, compute_reconciliation_report
    emitted = []
    monkeypatch.setattr("events.bus.emit_async", lambda event_type, payload: emitted.append(payload))
    g = gr.build_skeleton(db_session)
    (a_start, a_end, a_exp, a_cnt), (b_start, b_end, b_exp, b_cnt) = gr.seed_cash_drawers(db_session, g)
    assert (a_exp, b_exp) == (3_500_000, 2_000_000)

    a = record_drawer_count(db_session, g.rid, g.manager.id, a_cnt, a_start, a_end)
    b = record_drawer_count(db_session, g.rid, g.manager.id, b_cnt, b_start, b_end)
    assert (a.expected_amount_cents, a.counted_amount_cents) == (3_500_000, 3_448_000)

    by_id = {v.count_id: v for v in compute_reconciliation_report(db_session, g.rid).drawer_variances}
    assert by_id[a.id].variance_cents == -52_000 and by_id[a.id].flagged is True       # short KES 520 > 350
    assert by_id[b.id].variance_cents == -15_000 and by_id[b.id].flagged is False      # short KES 150 ≤ 200
    assert [e["count_id"] for e in emitted] == [a.id]                                   # only the real gap alerts


def test_ex15_decision_score_weights_sum_to_82_5():
    """§7 #15: 0.9×45 + 0.6×25 + 0.8×15 + 1.0×15 = 82.5, using the engine's own weights."""
    from ai.decisions.ranking import W_IMPACT, W_CONFIDENCE, W_RISK, W_EASE
    assert (W_IMPACT, W_CONFIDENCE, W_RISK, W_EASE) == (0.45, 0.25, 0.15, 0.15)
    total = 0.9 * W_IMPACT * 100 + 0.6 * W_CONFIDENCE * 100 + 0.8 * W_RISK * 100 + 1.0 * W_EASE * 100
    assert total == pytest.approx(82.5)


def test_ex15b_decision_engine_cannot_reach_a_risk_term_of_0_8():
    """The engine's risk term is 1 − (risk−1)/4 ∈ {1, .75, .5, .25, 0}; the spec's 0.8 is not reachable, so a
    real decision with impact≈0.9, confidence 60, risk 2, difficulty 1 scores 81.75 and ranks as priority 82."""
    from ai.decisions.model import Decision
    from ai.decisions.ranking import score, rank, _norm_impact, IMPACT_REFERENCE_CENTS
    impact = round(math.expm1(0.9 * math.log1p(IMPACT_REFERENCE_CENTS)))
    assert _norm_impact(impact) == pytest.approx(0.9, abs=1e-6)
    decision = Decision(agent="x", category="pricing", action="a", rationale="r", confidence_pct=60,
                        risk=2, difficulty=1, impact_cents_month=impact)
    assert score(decision) * 100 == pytest.approx(81.75, abs=1e-3)
    assert rank([decision])[0]["priority_score"] == 82


def test_ex16_kes_beats_percent():
    """§7 #16: a 30% hit on KES 500 × 1,000 is far bigger than 70% on KES 500 × 10 — rank decisions by KES."""
    assert 500 * Fraction(30, 100) * 1000 == 150_000
    assert 500 * Fraction(70, 100) * 10 == 3_500


# ═════════════════════════════════════════════════════════════════════════════
# PENDING — owned by a later sprint (strict xfail: fails now, must be flipped when it lands)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=True, reason="S3.2 P&L engine: kept 15,000 (15%), prime cost 57%")
def test_ex01b_weekly_pnl_kept_and_prime_cost(db_session):
    from owner.money.pnl import compute_pnl                                     # noqa: F401  (does not exist yet)
    raise AssertionError("flip to: gross 6_800_000 · kept 1_500_000 (15.0%) · prime 57.0%")


@pytest.mark.xfail(strict=True, reason="S3.2 P&L engine: operating expenses 26.7% and profit 19.0% of 105,000")
def test_ex02b_price_rise_opex_and_profit_percentages(db_session):
    from owner.money.pnl import compute_pnl                                     # noqa: F401
    raise AssertionError("flip to: opex 26.7% · profit 19.0%")


@pytest.mark.xfail(strict=True, reason="UNOWNED: no sprint builds a target-margin price (the '55% target', never pitched). "
                                       "Rounding conflict to resolve first: spec says 578 (whole KES) but #3 rounds to the KES 5 step (580 → 54,000).")
def test_ex04_same_dish_to_55_percent_target(db_session):
    from owner.menu_math import target_price_cents                              # noqa: F401
    raise AssertionError("flip to: 260 / 0.45 → 578 → (578 − 400) × 300 = KES 53,400 / month")


@pytest.mark.xfail(strict=True, reason="S3.3 break-even: fixed costs per day ÷ (1 − food cost %)")
def test_ex09_break_even_sales(db_session):
    from owner.money.breakeven import break_even_sales_cents                    # noqa: F401
    raise AssertionError("flip to: 8,000 ÷ (1 − 0.32) = KES 11,765")


@pytest.mark.xfail(strict=True, reason="UNOWNED: no combo pricing engine exists and no sprint builds one")
def test_ex10_combo_margin(db_session):
    from owner.menu_math import combo_margin_pct                                # noqa: F401
    raise AssertionError("flip to: 650 + 550 = 1,200 → 1,050; cost 460 → 56.2% margin (above the 40% floor)")


@pytest.mark.xfail(strict=True, reason="UNOWNED: recipes have no cooked-yield concept anywhere in the code")
def test_ex11_prep_quantity_with_yield(db_session):
    from owner.kitchen import prep_raw_quantity                                 # noqa: F401
    raise AssertionError("flip to: 45 portions × 0.25 kg cooked ÷ 0.80 yield = 14.06 kg raw")


@pytest.mark.xfail(strict=True, reason="UNOWNED: ai/reorder.py is par − on-hand; the spec's market list is need + buffer − on-hand")
def test_ex12_market_list(db_session):
    from owner.kitchen import market_list                                       # noqa: F401
    raise AssertionError("flip to: beef 11 kg · chicken 48 · tomatoes 7 kg · rice 0")


@pytest.mark.xfail(strict=True, reason="S3.2 P&L engine: month totals")
def test_ex13_monthly_pnl(db_session):
    from owner.money.pnl import compute_pnl                                     # noqa: F401
    raise AssertionError("flip to: 412,000 − 131,800 = 280,200; kept 65,200 (15.8%); food 32.0%")


@pytest.mark.xfail(strict=True, reason="S3.3 expense spike: month vs 3-month average ≥ 25% (setting)")
def test_ex14_expense_spike(db_session):
    from owner.money.spikes import expense_spike_pct                            # noqa: F401
    raise AssertionError("flip to: (14,600 + 14,100 + 14,300)/3 = 14,333; 18,600 / 14,333 → +29.8%")


# ═════════════════════════════════════════════════════════════════════════════
# ARITHMETIC — the spec's own numbers, re-derived exactly (no engine involved)
# ═════════════════════════════════════════════════════════════════════════════

def ceil_to(value: Fraction, step: int) -> int:
    return math.ceil(value / step) * step


class TestSpecArithmetic:
    def test_01_weekly_pnl(self):
        gross = 100_000 - 32_000
        kept = gross - 25_000 - 28_000
        assert (gross, kept) == (68_000, 15_000)
        assert Fraction(kept, 100_000) == Fraction(15, 100)
        assert Fraction(32_000 + 25_000, 100_000) == Fraction(57, 100)                  # prime cost

    def test_02_price_rise(self):
        sales = 105_000
        pct = lambda n: round(float(Fraction(n, sales) * 100), 1)
        assert (pct(32_000), pct(25_000), pct(28_000), pct(20_000)) == (30.5, 23.8, 26.7, 19.0)

    def test_03_quarter_chicken_to_floor(self):
        exact = Fraction(260) / (1 - Fraction(40, 100))
        assert float(exact) == pytest.approx(433.3333, abs=1e-3)
        price = ceil_to(exact, 5)
        assert price == 435 and (price - 400) * 300 == 10_500
        assert ceil_to(exact * 100, 50) == 43_350                                        # today's KES 0.50 rounding (D16)

    def test_04_same_dish_to_55_percent(self):
        exact = Fraction(260) / (1 - Fraction(55, 100))
        assert float(exact) == pytest.approx(577.78, abs=1e-2)
        whole = math.ceil(exact)
        assert whole == 578 and (whole - 400) * 300 == 53_400                            # as written in the spec
        step5 = ceil_to(exact, 5)
        assert step5 == 580 and (step5 - 400) * 300 == 54_000                            # same rule as #3 would give

    def test_05_chips_sold_below_menu(self):
        assert float(Fraction((300 - 270) * 400 * 30, 14)) == pytest.approx(25_714.2857, abs=1e-3)

    def test_06_burger_delivery(self):
        assert 600 - 150 - 280 == 170 and 600 - 280 == 320
        assert Fraction(25, 100) * 600 == 150

    def test_07_beef_variance(self):
        used = 50 + 30 - 40
        expected = Fraction(120) * Fraction(1, 4)
        assert (used, expected, used - expected) == (40, 30, 10)
        assert Fraction(10, 40) == Fraction(25, 100)                                      # the spec's denominator
        assert round(float(Fraction(10, 30) * 100), 1) == 33.3                            # the engine's denominator

    def test_08_cash_tolerance(self):
        tolerance = max(200, Fraction(1, 100) * 35_000)
        assert tolerance == 350 and 520 > tolerance

    def test_09_break_even(self):
        assert round(float(Fraction(8_000) / (1 - Fraction(32, 100)))) == 11_765

    def test_10_combo(self):
        price, cost = 1_050, 260 + 200
        assert 650 + 550 == 1_200 and Fraction(1_200 - price, 1_200) == Fraction(1, 8)
        assert round(float(Fraction(price - cost, price) * 100), 1) == 56.2

    def test_11_prep(self):
        assert round(float(Fraction(45) * Fraction(1, 4) / Fraction(80, 100)), 2) == 14.06

    def test_12_market_list(self):
        need = lambda base, buffer, on_hand: max(Fraction(base) + buffer - on_hand, 0)
        assert [need(14, 5, 8), need(60, 20, 32), need(6, 2, 1), need(Fraction(27, 2), 10, 25)] == [11, 48, 7, 0]

    def test_13_monthly_pnl(self):
        gross = 412_000 - 131_800
        kept = gross - 103_000 - 112_000
        assert (gross, kept) == (280_200, 65_200)
        assert round(float(Fraction(kept, 412_000) * 100), 1) == 15.8
        assert round(float(Fraction(131_800, 412_000) * 100), 1) == 32.0

    def test_14_expense_spike(self):
        average = Fraction(14_600 + 14_100 + 14_300, 3)
        assert round(float(average)) == 14_333
        assert round(float((Fraction(18_600) / average - 1) * 100), 1) == 29.8

    def test_15_decision_score(self):
        assert Fraction(9, 10) * 45 + Fraction(6, 10) * 25 + Fraction(8, 10) * 15 + 1 * 15 == Fraction(165, 2)

    def test_16_kes_vs_percent(self):
        assert 500 * Fraction(30, 100) * 1_000 == 150_000 and 500 * Fraction(70, 100) * 10 == 3_500


def test_every_worked_example_has_a_golden():
    """All 16 §7 examples must have at least one test here (live, pending, or arithmetic)."""
    source = open(__file__, encoding="utf-8").read()
    live_or_pending = {int(n) for n in re.findall(r"def test_ex(\d\d)", source)}
    arithmetic = {int(n) for n in re.findall(r"    def test_(\d\d)_", source)}
    assert arithmetic == set(range(1, 17)), f"arithmetic missing: {set(range(1, 17)) - arithmetic}"
    missing = set(range(1, 17)) - live_or_pending
    # #13/#14 etc. are pending; #16 is live; every number must appear as an engine-level test too.
    assert missing == set(), f"examples with no engine-level golden (live or pending): {sorted(missing)}"
