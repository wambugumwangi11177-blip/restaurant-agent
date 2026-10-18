"""
E4 — Planted scenarios (docs/v2/SPEC.md §5, §6; figure 6.1 is transcribed in docs/v2/figures/scenarios.md).

"The demo is also the test": the generator plants each scenario on purpose, and this eval asserts that the REAL engine
finds it and that it shows up in the block the owner will look at. Each test says which engine and which block.

                                                                   status
  P1  Quarter chicken 400/260          profit leak · reprice to 435   asserted
  P2  Chips menu 300, charged 270      sold below menu price          asserted
  P3  Burger 600 on Glovo 25%          delivery keeps 170 vs 320      asserted
  P4  Afternoon 15–17h low margin      weakest hours                  asserted
  P5  Beef: kitchen draws extra        missing stock (kitchen zone)   asserted (scaled — see PROGRESS)
  P6  Handover: store 4.0 / kitchen 3.8 doesn't match                  asserted (scaled)
  P7  Tuesday night drawer short ×4    recurring pattern              asserted (new engine function)
  P8  3 'M-Pesa' sales, no statement   M-Pesa gap                     strict xfail — P6 phase (S6.x)
  P9  Gas +30% vs 3-month average      costs going up                 asserted (S3.3)
  P10 Rent 70k due on the 4th          bill radar shortfall           asserted (S3.3; the date is relative)
  P11 Star · Puzzle · Plowhorse · Dog                                 asserted
  P12 Holiday Tuesday + chips out 19:00  why was Tuesday bad          data asserted; the OS "why" form is S5.1
  P13 Kenchic delivers 56 of 60        short delivery                 asserted (scaled; new engine field)
  P14 Branch B food cost 37% vs A 29%  branch comparison              asserted (data, and the OS "compare" form)
  P15 Supplier with one delivery       must NOT show 100% reliable    asserted (regression of D3)
  P16 POS orders without M-Pesa receipt must NOT flood Home           asserted (regression of D1)

Strict xfail means: the day the feature lands without this test being flipped to a real assertion, the build goes RED.
`test_every_scenario_has_a_test` fails if any of the sixteen has no entry at all.

The engines read the real clock, so the demo here is built on `utcnow()`. P12 needs a Tuesday that is a Kenyan public
holiday inside the 120-day window; the generator plants it when one exists and says so when it does not
(`summary.planted`), so P12's data test pins a clock after Mashujaa Day (2026-10-20).
"""
import re
from collections import Counter
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import models
from demo.generator import build
from time_utils import eat_date, utcnow

OWNER, PASSWORD = "owner@demo-restaurant.example", "Demo-Passw0rd!x"


def _session(tmp_path_factory, name):
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp(name) / 'demo.db'}", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """The whole demo, every scenario planted, built on the real clock; Home composed for each branch."""
    from owner.home import compose_home
    from owner.states import OwnerContext
    engine, db = _session(tmp_path_factory, "e4")
    summary = build(db, OWNER, PASSWORD, now=utcnow())
    owner = db.query(models.User).filter(models.User.email == OWNER).one()
    homes = {}
    for key, rid in zip(("A", "B"), summary.restaurant_ids):
        homes[key] = compose_home(OwnerContext(db, owner, db.get(models.Restaurant, rid)), "30d")
    ctx = {k: OwnerContext(db, owner, db.get(models.Restaurant, rid)) for k, rid in zip(("A", "B"), summary.restaurant_ids)}
    yield {"db": db, "summary": summary, "A": homes["A"], "B": homes["B"], "ctx": ctx, "rid": {"A": summary.restaurant_ids[0], "B": summary.restaurant_ids[1]}}
    db.close()
    engine.dispose()


def block(home, area, name):
    return home["areas"][area]["blocks"][name]


def cards(home):
    return home["costing_you_money"]["cards"]


# ── P1 ───────────────────────────────────────────────────────────────────────

def test_p01_quarter_chicken_is_a_profit_leak_and_the_idea_is_435(demo):
    """Engine: profit leak + pricing REPRICE. Block: sales_dishes.price_ideas (and the money leak list)."""
    ideas = block(demo["A"], "sales_dishes", "price_ideas")
    assert ideas["state"] == "live"
    idea = next(i for i in ideas["ideas"] if i["dish"] == "Quarter chicken")
    assert (idea["kind"], idea["from"], idea["to"]) == ("Priced too low", 400.0, 435.0)
    assert idea["month_gain"] > 0
    leak = next(l for l in ideas["priced_too_low"] if l["dish"] == "Quarter chicken")
    assert leak["keeps_pct"] == 35.0 and leak["month_gain"] > 0
    assert {a["setting"] for a in ideas["assumptions"]} == {"margin_floor_pct", "price_step_kes"}


def test_p01_is_one_of_the_things_costing_you_money(demo):
    """Zone 2 (costing_you_money): the repricing idea is a card with a KES figure and an action."""
    card = next(c for c in cards(demo["A"]) if "Quarter chicken" in c["sentence"] and "435" in c["sentence"])
    assert card["kes_month"] and card["kes_month"] > 0 and card["action"] and card["why"]


# ── P2 ───────────────────────────────────────────────────────────────────────

def test_p02_chips_are_charged_below_the_menu_price(demo):
    """Engine: profit.till_price_gap. Block: cash.below_menu_price."""
    below = block(demo["A"], "cash", "below_menu_price")
    chips = next(d for d in below["dishes"] if d["dish"] == "Chips")
    assert (chips["menu_price"], chips["charged"], chips["below_pct"]) == (300.0, 270.0, 10.0)
    assert chips["month_loss"] > 1000


def test_p02_is_one_of_the_things_costing_you_money(demo):
    """Ranked by KES with the other losses: Home shows the five largest, the rest sit under "more" (`ranked` lists them all)."""
    chips = next(c for c in demo["A"]["costing_you_money"]["ranked"] if "Chips" in c["sentence"])
    assert chips["kes_month"] and chips["kes_month"] > 1000 and chips["tier"] == "loss"


# ── P3 ───────────────────────────────────────────────────────────────────────

def test_p03_a_burger_sold_through_glovo_keeps_170_not_320(demo):
    """Engine: pricing delivery margins (owner's 25% Glovo commission). Block: sales_dishes.delivery."""
    delivery = block(demo["A"], "sales_dishes", "delivery")
    gap = next(g for g in delivery["delivery_gaps"] if g["dish"] == "Burger" and g["channel"] == "Glovo")
    assert gap["commission_pct"] == 25
    assert gap["keeps"] == 170.0 and gap["keeps_dine_in"] == 320.0
    assert gap["price_to_keep_floor"] > 600
    assert delivery["assumptions"][1]["setting"] == "commission_glovo_pct" or any(a["setting"] == "commission_glovo_pct" for a in delivery["assumptions"])
    glovo = next(c for c in delivery["channels"] if c["channel"] == "Glovo")
    assert glovo["orders"] >= 8 and glovo["pays_commission"] is True


# ── P4 ───────────────────────────────────────────────────────────────────────

def test_p04_the_afternoon_is_the_weakest_hours(demo):
    """Engine: profit daypart margins. Block: sales_dishes.delivery.best_and_weakest_hours."""
    hours = block(demo["A"], "sales_dishes", "delivery")["best_and_weakest_hours"]
    by = {h["hours"]: h for h in hours}
    weakest = min(hours, key=lambda h: h["keeps_pct"])
    best = max(hours, key=lambda h: h["keeps_pct"])
    assert weakest["hours"] == "afternoon"
    assert best["keeps_pct"] - weakest["keeps_pct"] >= 8
    assert by["afternoon"]["orders"] >= 40


# ── P5 ───────────────────────────────────────────────────────────────────────

def test_p05_the_kitchen_uses_more_beef_than_the_sales_explain(demo):
    """Engine: stock custody variance. Block: store.missing. (Scaled: see PROGRESS — the demo sells ~10 kg of beef a week.)"""
    missing = block(demo["A"], "store", "missing")
    beef = next(i for i in missing["items"] if i["item"] == "Beef")
    assert beef["check"] is True
    # The planted third more than the sales explain; the measured figure moves with the time of day (the kitchen draws at noon, the sales keep coming),
    # so the band is the planted third give or take a week's noise, not a single number.
    assert 25 <= beef["off_by_pct"] <= 42 and beef["missing"] >= 1.5
    assert beef["missing_value"] == pytest.approx(beef["missing"] * 800, rel=0.01) and beef["missing_value"] > 1000
    # Only the planted item is flagged. The engine forgives a gap smaller than one serving (ai/stock_custody.py): without that, the
    # Sunday waste write-off crossed 3% on a small item (2 portions of tilapia a week) on some days of the week, measured on the real clock.
    others = [i for i in missing["items"] if i["check"] and i["item"] != "Beef"]
    assert others == [], f"only the planted item should be flagged: {others}"
    head = demo["A"]["areas"]["store"]["summary"]
    assert head["status"] == "bad" and head["number"] == 1


def test_p05_is_one_of_the_things_costing_you_money(demo):
    assert any("Beef" in c["sentence"] and c["kes_month"] for c in cards(demo["A"]))


# ── P6 ───────────────────────────────────────────────────────────────────────

def test_p06_a_handover_that_does_not_match(demo):
    """Engine: stock custody transfers. Block: store.handover."""
    handover = block(demo["A"], "store", "handover")
    row = next(r for r in handover["doesnt_match"] if r["item"] == "Beef")
    assert (row["store_said"], row["kitchen_counted"], row["gap"]) == (4.0, 3.8, 0.2)
    assert len(handover["doesnt_match"]) == 1


# ── P7 ───────────────────────────────────────────────────────────────────────

def test_p07_tuesday_night_is_short_four_weeks_running(demo):
    """Engine: cash reconciliation recurring gaps. Block: cash.patterns (and the shifts table)."""
    patterns = block(demo["A"], "cash", "patterns")
    assert patterns["state"] == "live"
    row = next(p for p in patterns["patterns"] if p["when"] == "Tuesday evening")
    assert row["times_short"] == 4 and row["of_last"] == 4
    assert 450 <= row["short_each"] <= 650 and row["total"] == pytest.approx(row["short_each"] * 4, rel=0.02)
    assert len(patterns["patterns"]) == 1                                     # and nothing else repeats
    shifts = block(demo["A"], "cash", "shifts")
    assert sum(1 for s in shifts["shifts"] if s["check"]) >= 1               # the latest Tuesday is in the 14-day shift list


# ── P8 (the M-Pesa phase) ─────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="P6 phase (S6.x): the M-Pesa statement parser and matcher do not exist yet")
def test_p08_three_mpesa_sales_have_no_statement_line(demo):
    assert block(demo["A"], "cash", "mpesa")["state"] == "live"


def test_p09_gas_is_30_percent_above_its_three_month_average(demo):
    """Engine: owner/money/spikes (the owner's 25% setting). Block: money.spikes. §7 #14: 18,600 against (14,600 + 14,100 + 14,300) ÷ 3."""
    spikes = block(demo["A"], "money", "spikes")
    assert spikes["state"] == "as_entered" and spikes["assumption"] == {"setting": "expense_spike_pct", "value": 25.0, "label": "Cost increase we flag"}
    assert len(spikes["spikes"]) == 1                                         # and nothing else is flagged
    gas = spikes["spikes"][0]
    assert (gas["name"], gas["this_month_kes"], gas["usual_kes"], gas["up_pct"]) == ("Cooking gas", 18_600.0, 14_333.33, 29.8)
    assert gas["extra_kes"] == pytest.approx(4_266.67, abs=0.01)
    assert block(demo["B"], "money", "spikes")["spikes"] == []                  # the other branch's gas is as usual


def test_p10_rent_of_70k_falls_due_before_the_sales_can_cover_it(demo):
    """Engine: owner/money/radar. Blocks: money.bills (the radar) and coming_up.bills (Zone 4). Dates are relative, so the rent
    falls due three days from today; the radar starts from the KES 0 the owner keeps aside."""
    bills = block(demo["A"], "money", "bills")
    assert bills["state"] == "as_entered" and bills["opening_kes"] == 0.0
    assert bills["assumption"] == {"setting": "bill_reserve_kes", "value": 0, "label": "Cash you keep aside for bills"}
    rent = next(u for u in bills["upcoming"] if u["name"] == "Rent")
    assert (rent["amount_kes"], rent["days_away"], rent["short"]) == (70_000.0, 3, True)
    short = next(x for x in bills["shortfalls"] if x["bills"] == ["Rent"])
    assert short["bills_kes"] == 70_000.0 and 0 < short["short_by_kes"] < 70_000        # three or four days of sales cannot pay it all
    assert len(bills["days"]) == 30 and bills["lowest"]["balance_kes"] < 0
    coming = demo["A"]["coming_up"]["bills"]
    # Zone 4 lists bills by due date, and the other bills fall due on fixed days of the month, so on some dates (18 Oct: the electricity
    # on the 20th) one comes before the planted rent. Find the rent by name; the order is checked as an order.
    assert coming["state"] == "as_entered" and next(i for i in coming["items"] if i["name"] == "Rent")["short"] is True
    assert [i["days_away"] for i in coming["items"]] == sorted(i["days_away"] for i in coming["items"])
    assert {i["name"] for i in coming["items"]} >= {"Rent"} and all(i["days_away"] < 14 for i in coming["items"])


# ── P11 ──────────────────────────────────────────────────────────────────────

def test_p11_star_puzzle_plowhorse_and_dog(demo):
    """Engine: menu engineering. Block: sales_dishes.matrix (owner words, §3.4)."""
    matrix = block(demo["A"], "sales_dishes", "matrix")
    kind = {d["name"]: d["kind"] for d in matrix["dishes"]}
    assert kind["Nyama choma (goat)"] == "Best dish"
    assert kind["Fish fillet"] == "Earns well, few order it"
    assert kind["Chips"] == "Popular, earns little"
    assert kind["Spaghetti bolognese"] == "Consider removing"


# ── P12 (data) ───────────────────────────────────────────────────────────────

def test_p12_a_holiday_tuesday_with_chips_out_at_19(tmp_path_factory):
    """The Tuesday is a public holiday (the demand signal says so), sales are well down on other Tuesdays, and no chips
    were sold after 19:00 because the potatoes ran out. The OS 'why was Tuesday bad' answer that ranks these drivers is S5.1."""
    from ai.simulation.signals import demand_signals
    engine, db = _session(tmp_path_factory, "p12")
    try:
        now = datetime(2026, 10, 28, 13, 0)                                   # after Mashujaa Day, Tuesday 2026-10-20
        summary = build(db, OWNER, PASSWORD, now=now)
        assert summary.planted["P12"] == "2026-10-20"
        rid = summary.restaurant_ids[0]
        holiday = datetime(2026, 10, 20).date()
        assert demand_signals(holiday)["reasons"], "the holiday signal must be the one the twin uses"
        by_day = Counter()
        for total, created in db.query(models.Order.total, models.Order.created_at).filter(
                models.Order.restaurant_id == rid, models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED):
            if eat_date(created).weekday() == 1:
                by_day[eat_date(created)] += total
        usual = [v for d, v in by_day.items() if d != holiday and d >= holiday - timedelta(days=49)]
        assert len(usual) >= 5 and by_day[holiday] < 0.6 * (sum(usual) / len(usual))
        chips = db.query(models.MenuItem.id).filter(models.MenuItem.restaurant_id == rid, models.MenuItem.name == "Chips").scalar()
        late_chips = db.query(models.OrderItem).join(models.Order).filter(
            models.OrderItem.menu_item_id == chips, models.Order.restaurant_id == rid,
            models.Order.created_at >= datetime(2026, 10, 20, 16, 0), models.Order.created_at < datetime(2026, 10, 20, 21, 0)).count()
        assert late_chips == 0                                                 # 19:00-22:00 Nairobi
        early_chips = db.query(models.OrderItem).join(models.Order).filter(
            models.OrderItem.menu_item_id == chips, models.Order.restaurant_id == rid,
            models.Order.created_at >= datetime(2026, 10, 20, 5, 0), models.Order.created_at < datetime(2026, 10, 20, 16, 0)).count()
        assert early_chips > 0
        potatoes = db.query(models.InventoryItem.id).filter(models.InventoryItem.restaurant_id == rid, models.InventoryItem.item_name == "Potatoes").scalar()
        out = db.query(models.StockMovement).filter(models.StockMovement.inventory_item_id == potatoes,
                                                    models.StockMovement.movement_type == models.StockMovementType.ADJUST,
                                                    models.StockMovement.reason.like("%potatoes%out of chips by 19:00%")).all()
        assert len(out) == 1 and eat_date(out[0].created_at) == holiday and out[0].quantity < 0
    finally:
        db.close()
        engine.dispose()


def test_p12_the_os_why_form_names_the_holiday_then_the_chips(tmp_path_factory):
    """Engine: the OS "why" form (owner/answer_why.py). Screen: Ask LEVIII. The drivers come in the spec's order: holiday, then the dish that ran out."""
    from owner import ask
    from owner.states import OwnerContext
    engine, db = _session(tmp_path_factory, "p12os")
    try:
        now = datetime(2026, 10, 28, 13, 0)
        summary = build(db, OWNER, PASSWORD, now=now)
        owner = db.query(models.User).filter(models.User.email == OWNER).one()
        ctx = OwnerContext(db, owner, db.get(models.Restaurant, summary.restaurant_ids[0]))
        ctx.now = now
        out = ask.ask(ctx, "Why was Tuesday last week bad?")
        assert out["form"] == "why" and out["day"] == "2026-10-20"
        found = [d for d in out["drivers"] if d["found"]]
        assert [d["key"] for d in found] == ["holiday", "stock_out"]
        assert "Mashujaa Day" in found[0]["label"]
        assert found[1]["dish"] == "Chips" and found[1]["ingredient"] == "Potatoes"
        assert "ran short at" in found[1]["note"] and "Chips ran out" in out["headline"]
        sales = next(r for r in out["rows"] if r["key"] == "sales")["value"]
        usual = next(r for r in out["rows"] if r["key"] == "usual")["value"]
        assert sales < 0.6 * usual
    finally:
        db.close()
        engine.dispose()


def test_p12_is_not_invented_when_the_window_has_no_holiday_tuesday(tmp_path_factory):
    engine, db = _session(tmp_path_factory, "p12none")
    try:
        summary = build(db, OWNER, PASSWORD, now=datetime(2026, 10, 15, 13, 0), days=60)      # 2026-08-17 .. 2026-10-15: none
        assert summary.planted["P12"] is None
    finally:
        db.close()
        engine.dispose()


# ── P13 ──────────────────────────────────────────────────────────────────────

def test_p13_kenchic_delivered_56_of_every_60(demo):
    """Engine: supply chain short deliveries. Block: store.suppliers. (Scaled: the ratio 56/60 is kept — see PROGRESS.)"""
    suppliers = block(demo["A"], "store", "suppliers")
    short = suppliers["short_deliveries"]
    assert len(short) == 1
    row = short[0]
    assert row["supplier"] == "Kenchic" and row["item"] == "Chicken"
    assert row["received"] / row["ordered"] == pytest.approx(56 / 60, abs=0.01)
    assert row["short_by"] == pytest.approx(row["ordered"] - row["received"], abs=0.05) and row["short_value"] > 0
    kenchic = next(s for s in suppliers["suppliers"] if s["name"] == "Kenchic")
    assert kenchic["on_time_pct"] is not None


# ── P14 ──────────────────────────────────────────────────────────────────────

def test_p14_branch_b_spends_37_on_ingredients_branch_a_29(demo):
    """Engine: profit food cost, per branch. The OS 'compare' answer is S5.1; here, what it will compare."""
    a, b = (demo[k]["areas"]["money"]["blocks"]["cost_dials"]["food_cost_pct"] for k in ("A", "B"))
    assert 28.0 <= a <= 30.0, a
    assert 36.0 <= b <= 38.0, b
    assert demo["A"]["areas"]["money"]["summary"]["word"] == "Fine"
    assert demo["B"]["areas"]["money"]["summary"]["word"] == "Watch"          # over the owner's 35% ceiling, not yet 5 points over
    db = demo["db"]
    from ai.enterprise.benchmarking import benchmark_organization
    org = db.get(models.Restaurant, demo["rid"]["A"]).organization_id
    sites = benchmark_organization(db, org)
    assert len(sites["sites"]) == 2 and {s["name"] for s in sites["sites"]} == {"Demo Restaurant", "Demo Restaurant – Kasarani"}


def test_p14_the_os_compare_form_puts_the_branches_side_by_side(demo):
    """Engine: the OS "compare" form (owner/answer_compare.py). Screen: Ask LEVIII. The same figures as each branch's Home."""
    from owner import ask
    out = ask.ask(demo["ctx"]["A"], "Compare my branches")
    assert out["form"] == "compare" and out["kind"] == "branches"
    cols = {c["name"]: c for c in out["columns"]}
    assert set(cols) == {"Demo Restaurant", "Demo Restaurant – Kasarani"}
    a, b = cols["Demo Restaurant"], cols["Demo Restaurant – Kasarani"]
    assert a["food_cost_pct"] == demo["A"]["areas"]["money"]["blocks"]["cost_dials"]["food_cost_pct"]
    assert b["food_cost_pct"] == demo["B"]["areas"]["money"]["blocks"]["cost_dials"]["food_cost_pct"]
    assert 36.0 <= b["food_cost_pct"] <= 38.0 and 28.0 <= a["food_cost_pct"] <= 30.0
    assert "Kasarani" in out["headline"] and next(r for r in out["rows"] if r["key"] == "gap_kes_month")["value"] > 0


# ── P15 · P16 (regression guards) ────────────────────────────────────────────

def test_p15_a_supplier_with_one_delivery_is_not_100_percent_reliable(demo):
    """Regression of D3. Block: store.suppliers shows 'Learning', not a score."""
    suppliers = block(demo["A"], "store", "suppliers")["suppliers"]
    one = next(s for s in suppliers if s["closed_orders"] == 1)
    assert one["on_time_pct"] is None and one["word"] == "Learning"
    assert all(s["on_time_pct"] != 100.0 for s in suppliers if s["closed_orders"] < 3)
    db = demo["db"]
    sup = db.query(models.Supplier).filter(models.Supplier.name == one["name"], models.Supplier.restaurant_id == demo["rid"]["A"]).one()
    assert sup.reliability_score == 100.0                                      # nothing wrote a score while it was learning


def test_p16_pos_orders_without_an_mpesa_receipt_do_not_flood_home(demo):
    """Regression of D1: the demo has plenty of M-Pesa sales rung up on the till (no receipt, no STK push)."""
    db = demo["db"]
    pos_mpesa = db.query(models.Order).filter(models.Order.restaurant_id == demo["rid"]["A"], models.Order.payment_method == models.PaymentMethod.MPESA,
                                              models.Order.mpesa_checkout_request_id.is_(None), models.Order.is_paid.is_(True)).count()
    assert pos_mpesa > 150
    for key in ("A", "B"):
        text = " ".join(c["sentence"] + " " + c["why"] for c in cards(demo[key])).lower()
        assert "receipt" not in text and "m-pesa" not in text and "mpesa" not in text
        assert len(cards(demo[key])) <= 5


# ── completeness ─────────────────────────────────────────────────────────────

def test_every_scenario_has_a_test():
    source = open(__file__).read()
    covered = set(re.findall(r"^def test_p(\d{2})_", source, flags=re.M))
    assert covered == {f"{n:02d}" for n in range(1, 17)}, f"scenarios with no test: {sorted({f'{n:02d}' for n in range(1, 17)} - covered)}"
