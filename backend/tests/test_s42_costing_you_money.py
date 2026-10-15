"""
S4.2 — "What's costing you money" (docs/v2/SPEC.md §3.1, ranking rule): what is happening now first, then ideas by what they
are worth in KES, then the ideas we cannot put an honest number on. The numbers are the engines' own: the decision layer
reshapes them (ai/decisions/adapters.py), it never makes one up.

The demo restaurant plants the problems (docs/v2/figures/scenarios.md): chips charged below the menu price (P2), a kitchen that
uses more beef than the sales explain (P5), a Tuesday-night drawer that is short every week (P7), a burger sold through
Glovo (P3), Quarter chicken priced under the owner's floor (P1).
"""
import math
from collections import Counter
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from ai.decisions.adapters import collect_decisions
from demo.generator import build
from tests.fixtures import golden_restaurant as gr
from time_utils import utcnow

OWNER, PASSWORD = "owner@demo-restaurant.example", "Demo-Passw0rd!x"


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    from owner.home import compose_home
    from owner.states import OwnerContext
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('s42') / 'demo.db'}", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    summary = build(db, OWNER, PASSWORD, now=utcnow())
    owner = db.query(models.User).filter(models.User.email == OWNER).one()
    rid = summary.restaurant_ids[0]
    ctx = OwnerContext(db, owner, db.get(models.Restaurant, rid))
    yield {"db": db, "rid": rid, "home": compose_home(ctx, "30d"), "ctx": ctx}
    db.close()
    engine.dispose()


def _decision(demo, agent, needle):
    found = [d for d in collect_decisions(demo["db"], demo["rid"]) if d.agent == agent and needle in d.action]
    assert found, f"no {agent} decision mentioning {needle!r}"
    return found[0]


def _block(demo, area, name):
    return demo["home"]["areas"][area]["blocks"][name]


# ── the ranking rule ─────────────────────────────────────────────────────────

def _tier(card):
    if card["tier"] == "now":
        return 0
    if card["kes_month"] is None:
        return 3
    return 1 if card["tier"] == "loss" else 2


def test_cards_are_now_then_money_going_out_then_money_to_make_then_what_cannot_be_priced(demo):
    costing = demo["home"]["costing_you_money"]
    ranked = costing["ranked"]
    assert [c["id"] for c in costing["cards"]] == [c["id"] for c in ranked[:5]] and costing["more"] == len(ranked) - 5
    assert [_tier(c) for c in ranked] == sorted(_tier(c) for c in ranked)                # nothing without a figure outranks one with a figure
    for tier in (1, 2):
        kes = [c["kes_month"] for c in ranked if _tier(c) == tier]
        assert kes == sorted(kes, reverse=True) and kes                                    # most money first inside each group
    assert all(c["kes_month"] is None or c["kes_month"] > 0 for c in ranked)             # never a KES 0 dressed as a figure
    assert {c["tier"] for c in ranked} == {"loss", "idea"} | ({"now"} if any(c["tier"] == "now" for c in ranked) else set())      # machine tokens: the screen words them


def test_a_gap_that_has_already_cost_money_outranks_a_price_rise_worth_more(demo):
    ranked = demo["home"]["costing_you_money"]["ranked"]
    biggest_idea = max(c["kes_month"] for c in ranked if c["tier"] == "idea" and c["kes_month"])
    smallest_loss = min(c["kes_month"] for c in ranked if c["tier"] == "loss" and c["kes_month"])
    assert biggest_idea > smallest_loss                                                   # the surge idea is worth more …
    first_idea = next(i for i, c in enumerate(ranked) if c["tier"] == "idea" and c["kes_month"])
    last_loss = max(i for i, c in enumerate(ranked) if c["tier"] == "loss" and c["kes_month"])
    assert last_loss < first_idea                                                         # … and still comes after every loss


def test_a_card_that_the_demo_planted_is_among_the_top_five(demo):
    sentences = " ".join(c["sentence"] + " " + c["why"] for c in demo["home"]["costing_you_money"]["cards"])
    assert "Beef" in sentences and "Quarter chicken" in sentences                         # the largest losses; the smaller ones are in `ranked`
    assert any("Chips" in c["sentence"] for c in demo["home"]["costing_you_money"]["ranked"])


def test_every_card_can_be_acknowledged_snoozed_or_dismissed_and_none_is_listed_twice(demo):
    ranked = demo["home"]["costing_you_money"]["ranked"]
    assert all(c["decision"] == {"options": ["approved", "later", "rejected"]} for c in demo["home"]["costing_you_money"]["cards"])
    assert len({c["id"] for c in ranked}) == len(ranked)
    assert Counter("set Quarter chicken to" in c["sentence"] or "Review margin on Quarter chicken" in c["sentence"] for c in ranked)[True] == 1   # the price idea and the margin leak are one problem


def test_the_rule_a_card_is_based_on_is_named_by_its_setting(demo):
    by = {c["sentence"].split(":")[0]: c for c in demo["home"]["costing_you_money"]["cards"]}
    beef = next(c for c in demo["home"]["costing_you_money"]["cards"] if "Beef" in c["sentence"])
    assert beef["assumption"] == {"setting": "missing_stock_flag_pct", "value": demo["ctx"].settings.missing_stock_flag_pct, "label": "Missing stock we flag"}
    reprice = next(c for c in demo["home"]["costing_you_money"]["cards"] if "Quarter chicken" in c["sentence"])
    assert reprice["assumption"]["setting"] == "margin_floor_pct"
    assert by                                                                               # (shape only; keeps the lookup honest)


# ── each signal carries the engine's own figure ──────────────────────────────

def test_the_chips_card_is_the_till_price_gap_and_carries_its_month_loss(demo):
    chips = next(d for d in _all(demo) if d.agent == "profit_intelligence" and "Chips" in d.action)
    gap = next(d for d in _block(demo, "cash", "below_menu_price")["dishes"] if d["dish"] == "Chips")
    assert chips.impact_cents_month == round(gap["month_loss"] * 100)                       # the card and the block are one number
    assert "300" in chips.action and "270" in chips.action
    assert not any(word in (chips.action + chips.rationale).lower() for word in ("theft", "stealing", "fraud", "steal"))   # a signal, not a verdict
    card = next(c for c in demo["home"]["costing_you_money"]["ranked"] if "Chips" in c["sentence"])
    assert card["kes_month"] == gap["month_loss"] and card["tier"] == "loss"


def test_the_beef_card_is_the_missing_stock_over_a_month(demo):
    beef = _decision(demo, "stock_custody", "Beef")
    row = next(i for i in _block(demo, "store", "missing")["items"] if i["item"] == "Beef")
    assert beef.impact_cents_month == pytest.approx(row["missing_value"] * 100 * 30 / 7, abs=3)     # the 7-day gap, said as a month
    assert "33" in beef.rationale or "32" in beef.rationale or "34" in beef.rationale        # how far off it is, in the owner's words
    assert not any(word in (beef.action + beef.rationale).lower() for word in ("theft", "stealing", "fraud", "steal"))


def test_only_the_planted_item_is_a_missing_stock_decision(demo):
    assert [d.action for d in collect_decisions(demo["db"], demo["rid"]) if d.agent == "stock_custody"] == [_decision(demo, "stock_custody", "Beef").action]


def test_tuesday_night_is_a_cash_decision_worth_what_it_loses_in_a_month(demo):
    tuesday = _decision(demo, "cash_reconciliation", "Tuesday evening")
    pattern = next(p for p in _block(demo, "cash", "patterns")["patterns"] if p["when"] == "Tuesday evening")
    assert tuesday.impact_cents_month == pytest.approx(pattern["total"] * 100 * 30 / 28, abs=2)
    assert "4 of the last 4" in tuesday.rationale
    assert tuesday.meta["assumption"]["setting"] == "cash_tolerance_kes"


def test_a_burger_sold_through_glovo_is_a_delivery_decision(demo):
    burger = _decision(demo, "pricing_intelligence", "Burger on Glovo")
    gap = next(g for g in _block(demo, "sales_dishes", "delivery")["delivery_gaps"] if g["dish"] == "Burger" and g["channel"] == "Glovo")
    assert "Burger" in burger.action and burger.impact_cents_month and burger.impact_cents_month > 0
    assert burger.meta["assumption"]["setting"] == "commission_glovo_pct"
    assert gap["keeps"] == 170.0                                                              # the figure the owner reads is the figure the decision is built on


# ── profit leaks are measured to the owner's floor, not to an aspiration ─────

def test_a_profit_leak_is_the_shortfall_to_the_floor_not_to_the_target(demo):
    from ai.profit.intelligence import get_profit_intelligence
    profit = get_profit_intelligence(demo["db"], demo["rid"])
    leak = next(l for l in profit["profit_leaks"] if l["item_name"] == "Quarter chicken")
    floor_pct = demo["ctx"].settings.margin_floor_pct
    qty = next(c["qty_30d"] for c in profit["contribution_margins"] if c["item_name"] == "Quarter chicken")
    step = demo["ctx"].settings.price_step_cents
    floor_price = math.ceil(Decimal(26_000) / (1 - Decimal(str(floor_pct)) / 100) / step) * step
    assert leak["floor_price"] == floor_price == 43_500
    assert leak["monthly_leak_cents"] == (floor_price - 40_000) * qty
    assert leak["suggested_price"] > floor_price                                              # the target is still there, as the price to aim for
    ideas = _block(demo, "sales_dishes", "price_ideas")
    assert next(l for l in ideas["priced_too_low"] if l["dish"] == "Quarter chicken")["month_gain"] == leak["monthly_leak_cents"] / 100


# ── a healthy restaurant has none of this ────────────────────────────────────

def test_a_restaurant_with_nothing_wrong_gets_no_signal_cards(db_session):
    g = gr.build_skeleton(db_session)
    gr.seed_pnl_month(db_session, g)
    agents = {d.agent for d in collect_decisions(db_session, g.rid)}
    assert not agents & {"stock_custody", "cash_reconciliation"}


def _all(demo):
    return collect_decisions(demo["db"], demo["rid"])


def test_rank_is_a_pure_ordering_rule():
    from owner.home import _rank
    cards = [
        {"id": "idea-big", "impact_cents_month": 900_000, "kind": "idea"},
        {"id": "no-figure", "impact_cents_month": None},
        {"id": "loss-small", "impact_cents_month": 50_000, "kind": "loss"},
        {"id": "fact", "now": True},
        {"id": "zero", "impact_cents_month": 0, "kind": "loss"},                       # a zero is not a figure
        {"id": "loss-big", "impact_cents_month": 400_000, "kind": "loss"},
        {"id": "idea-small", "impact_cents_month": 10_000, "kind": "idea"},
    ]
    assert [c["id"] for c in _rank(cards)] == ["fact", "loss-big", "loss-small", "idea-big", "idea-small", "no-figure", "zero"]
    assert _rank([]) == []
