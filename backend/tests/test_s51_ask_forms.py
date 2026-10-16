"""
S5.1 — Ask LEVIII answers in five forms (docs/v2/SPEC.md §4 P5): what · why · what-if · what should I do · compare.

What this pins:
  * the question is routed to a form and a topic by plain rules (no model), and every topic the registry names can answer;
  * every number in an answer's sentence is one of the numbers in its rows, drivers or assumptions (code computes, words
    only repeat) — the grounding rule of SPEC §0.3, checked on every form;
  * WHY (P12) lists the drivers in the spec's order — holiday, the top dish running out, staffing, cancelled sales — says
    what it checked and found nothing in, and invents no cause for an ordinary day;
  * WHAT-IF shows the assumption it used and equals the simulator's own figures, and changes nothing;
  * WHAT SHOULD I DO is Home's ranking by KES, the very same list;
  * COMPARE (P14) puts the branches side by side from the same engines, and a period against the one before it;
  * the endpoint validates, is owner-only and never shows another tenant's branches.
"""
import re
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import auth
import models
from demo.generator import build
from owner import answers, ask, registry
from owner.home import compose_home
from owner.states import STATES, OwnerContext
from time_utils import eat_date, utcnow

OWNER, PASSWORD = "owner@demo-restaurant.example", "Demo-Passw0rd!x"
HOLIDAY_NOW = datetime(2026, 10, 28, 13, 0)          # a Wednesday after Mashujaa Day (Tuesday 2026-10-20)
HOLIDAY = date(2026, 10, 20)


def _session(tmp_path_factory, name):
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp(name) / 'demo.db'}", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """The demo restaurant on the real clock: two branches, every scenario planted."""
    engine, db = _session(tmp_path_factory, "s51")
    summary = build(db, OWNER, PASSWORD, now=utcnow())
    owner = db.query(models.User).filter(models.User.email == OWNER).one()
    ctxs = {k: OwnerContext(db, owner, db.get(models.Restaurant, rid)) for k, rid in zip(("A", "B"), summary.restaurant_ids)}
    yield {"db": db, "owner": owner, "A": ctxs["A"], "B": ctxs["B"], "rid": dict(zip(("A", "B"), summary.restaurant_ids))}
    db.close()
    engine.dispose()


@pytest.fixture(scope="module")
def holiday(tmp_path_factory):
    """The demo built so that a Kenyan public holiday falls on a Tuesday inside the window (P12), asked about a week later."""
    engine, db = _session(tmp_path_factory, "s51h")
    summary = build(db, OWNER, PASSWORD, now=HOLIDAY_NOW)
    assert summary.planted["P12"] == HOLIDAY.isoformat()
    owner = db.query(models.User).filter(models.User.email == OWNER).one()
    ctx = OwnerContext(db, owner, db.get(models.Restaurant, summary.restaurant_ids[0]))
    ctx.now = HOLIDAY_NOW
    yield {"db": db, "ctx": ctx, "rid": summary.restaurant_ids[0]}
    db.close()
    engine.dispose()


# ═════════════════════════════════════════════════════════════════════════════
# Routing: a question → a form and a topic, by rules
# ═════════════════════════════════════════════════════════════════════════════

ROUTES = [
    ("Why was Tuesday bad?", "why", None),
    ("Why are my sales down this week", "why", None),
    ("What happened to sales yesterday?", "why", None),
    ("What if I raise the price of Chips to 350?", "what_if", None),
    ("what would happen if I cut Burger by 10%", "what_if", None),
    ("What should I do to make more money?", "what_to_do", None),
    ("Where do I start?", "what_to_do", None),
    ("How can I find KES 20,000 more a month?", "what_to_do", None),
    ("Compare my branches", "compare", None),
    ("This week vs last week", "compare", None),
    ("Is Kasarani doing better than Westlands?", "compare", None),
    ("How is my cash count looking?", "what", "cash"),
    ("Was the till short on any night?", "what", "cash"),
    ("Anything to check at the till? Any voids?", "what", "things_to_check"),
    ("How are my suppliers doing?", "what", "suppliers"),
    ("Which guests haven't come back?", "what", "win_back"),
    ("What has LEVIII saved me?", "what", "savings"),
    ("How complete are my costs?", "what", "data_trust"),
    ("Am I making a profit this month?", "what", "money"),
    ("Which bills are due soon?", "what", "money"),
    ("What will run out soon?", "what", "stock"),
    ("What are my best-selling dishes?", "what", "menu"),
]


@pytest.mark.parametrize("question,form,topic", ROUTES)
def test_a_question_is_routed_to_a_form_and_topic(question, form, topic):
    got_form, got_topic = ask.classify(question)
    assert got_form == form, (question, got_form)
    if topic is not None:
        assert got_topic == topic, (question, got_topic)


def test_every_topic_the_registry_names_can_answer_and_the_forms_are_topics_too():
    topics = set(ask.topics())
    assert {"why", "what_if", "what_to_do", "compare"} <= topics
    for engine in registry.ENGINES:
        assert set(engine.os_topics) <= topics, (engine.key, engine.os_topics)
    assert ask.FORMS == ("what", "why", "what_if", "what_to_do", "compare")


WHAT_SAMPLES = {
    "stock": "What will run out soon?", "revenue": "How are my sales this week?", "bookings": "How many bookings today?",
    "kitchen": "What is slowing my kitchen down?", "staff": "Who is working today?", "menu": "Which dishes earn the most?",
    "pricing": "Which prices should I change?", "profit": "Where am I losing money?", "ops": "How is my restaurant doing?",
    "cash": "How is my cash count looking?", "things_to_check": "Anything to check at the till?",
    "suppliers": "How are my suppliers doing?", "win_back": "Which guests haven't come back?",
    "savings": "What has LEVIII saved me?", "data_trust": "How complete are my costs?", "money": "Am I making a profit this month?",
}


def test_the_samples_cover_exactly_the_what_topics():
    assert set(WHAT_SAMPLES) == set(ask.what_topics())


@pytest.mark.parametrize("topic", sorted(WHAT_SAMPLES))
def test_every_what_topic_answers_from_the_demo_with_a_state_and_a_sentence(demo, topic):
    out = ask.ask(demo["A"], WHAT_SAMPLES[topic], topic=topic)
    assert out["form"] == "what" and out["topic"] == topic
    assert out["state"] in STATES and out["headline"].strip()
    assert out["state"] != "unavailable", out
    assert out["topic_label"]
    if out["state"] in ("no_data", "unavailable"):
        assert out["reason"]


def test_the_what_form_for_the_old_topics_is_still_the_old_handlers_answer(demo):
    from routers import ai_ask
    out = ask.ask(demo["A"], "What will run out soon?")
    card = ai_ask._HANDLERS["stock"](demo["db"], demo["rid"]["A"], "What will run out soon?")
    assert out["answer"]["finding"] == card["finding"] and out["headline"] == card["finding"]


# ── the grounding rule, on every form ────────────────────────────────────────

OLD_TOPICS = {"stock", "revenue", "bookings", "kitchen", "staff", "menu", "pricing", "profit", "ops"}      # the old handlers' own sentences, unchanged
GROUNDING_QUESTIONS = ([WHAT_SAMPLES[t] for t in sorted(WHAT_SAMPLES) if t not in OLD_TOPICS] + [
    "What if I raise the price of Chips to 350?", "What should I do to make more money?", "How can I find KES 20,000 more a month?",
    "Compare my branches", "This week vs last week", "Why were sales down last Wednesday?",
])


@pytest.mark.parametrize("question", GROUNDING_QUESTIONS)
def test_every_number_in_the_sentence_is_a_number_in_the_rows(demo, question):
    out = ask.ask(demo["A"], question)
    stray = answers.ungrounded(out)
    assert stray == [], f"{question!r}: numbers in the sentence that no row backs: {stray} in {out['headline']!r}"


def test_the_grounding_check_catches_an_invented_number():
    out = {"question": "q", "headline": "You will earn KES 9,999 more and sales rose 42%.",
           "rows": [{"label": "Sales", "value": 1200.0, "unit": "kes"}], "drivers": [], "assumptions": []}
    assert set(answers.ungrounded(out)) == {9999.0, 42.0}


def test_numbers_are_read_the_way_an_owner_writes_them():
    assert answers.numbers_in("KES 12,345.50 is 37.5% of 3 plates, 19:00, 4 Mar") == [12345.5, 37.5, 3.0, 19.0, 0.0, 4.0]
    assert answers.ungrounded({"question": "", "headline": "Nothing at 0 today.", "rows": [], "drivers": [], "assumptions": []}) == []   # zero is "nothing"


# ═════════════════════════════════════════════════════════════════════════════
# WHY — P12: a holiday Tuesday with chips gone at 19:00
# ═════════════════════════════════════════════════════════════════════════════

def _day_sales(db, rid, day):
    from owner.money.pnl import nairobi_utc_range
    lo, hi = nairobi_utc_range(day, day)
    cents = db.query(func.coalesce(func.sum(models.Order.total), 0)).filter(
        models.Order.restaurant_id == rid, models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= lo, models.Order.created_at < hi).scalar()
    return cents / 100.0


def test_why_was_tuesday_bad_finds_the_holiday_then_the_chips(holiday):
    out = ask.ask(holiday["ctx"], "Why was Tuesday last week bad?")
    assert out["form"] == "why" and out["state"] in ("live", "stale")
    assert out["day"] == HOLIDAY.isoformat() and out["weekday"] == "Tuesday"
    found = [d for d in out["drivers"] if d["found"]]
    assert [d["key"] for d in found][:2] == ["holiday", "stock_out"]                   # the spec's order
    assert "Mashujaa Day" in found[0]["label"] or "Mashujaa Day" in found[0]["note"]
    chips = found[1]
    assert "Chips" in chips["label"] and chips["value"] > 0 and chips["unit"] == "kes"     # what the missing plates would have brought
    from datetime import timedelta as _td
    rid = holiday["rid"]
    chips_id = holiday["db"].query(models.MenuItem.id).filter_by(restaurant_id=rid, name="Chips").scalar()
    from owner.money.pnl import nairobi_utc_range
    lo, hi = nairobi_utc_range(HOLIDAY, HOLIDAY)
    last = holiday["db"].query(func.max(models.Order.created_at)).join(models.OrderItem, models.OrderItem.order_id == models.Order.id).filter(
        models.Order.restaurant_id == rid, models.OrderItem.menu_item_id == chips_id, models.Order.created_at >= lo, models.Order.created_at < hi).scalar()
    local = last + _td(hours=3)
    said = f"{local.hour % 12 or 12}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"
    assert said in chips["note"], (said, chips["note"])                                        # says when the last plate sold
    sales = next(r for r in out["rows"] if r["key"] == "sales")
    usual = next(r for r in out["rows"] if r["key"] == "usual")
    assert sales["value"] == pytest.approx(_day_sales(holiday["db"], holiday["rid"], HOLIDAY), abs=0.01)
    assert sales["value"] < 0.6 * usual["value"]
    assert answers.ungrounded(out) == []


def test_why_understands_the_day_however_the_owner_says_it(holiday):
    ctx = holiday["ctx"]                                                                 # asked on Wednesday 28 Oct 2026
    for words, day in [("Why was Tuesday last week bad?", "2026-10-20"), ("Why was 20 Oct bad?", "2026-10-20"), ("Why was October 20 bad?", "2026-10-20"),
                       ("Why was Tuesday the 20th bad?", "2026-10-20"), ("Why was 2026-10-20 bad?", "2026-10-20"), ("Why was Tuesday bad?", "2026-10-27"),
                       ("Why was yesterday bad?", "2026-10-27"), ("Why was Monday slow?", "2026-10-26")]:
        assert ask.ask(ctx, words)["day"] == day, words


def test_why_says_what_it_checked_even_where_it_found_nothing(holiday):
    out = ask.ask(holiday["ctx"], "Why was Tuesday last week bad?")
    assert [d["key"] for d in out["drivers"]] == ["holiday", "stock_out", "staffing", "cancelled_sales"]
    for d in out["drivers"]:
        assert d["label"] and (d["found"] or d["note"])                                  # "nothing unusual" is said, not left blank


def test_why_invents_no_cause_for_an_ordinary_day(holiday):
    out = ask.ask(holiday["ctx"], "Why were sales low last Friday?")                     # 2026-10-23: nothing planted
    assert out["form"] == "why"
    found = [d for d in out["drivers"] if d["found"]]
    assert found == [] or all(d["key"] not in ("holiday",) for d in found)
    assert "holiday" not in out["headline"].lower()


def test_why_asked_about_a_day_with_no_sales_does_not_guess(holiday):
    ctx = holiday["ctx"]
    out = ask.ask(ctx, "Why was 2020-01-07 bad?")
    assert out["state"] in ("no_data", "learning") and out["reason"]


def test_why_with_no_day_named_looks_at_yesterday(holiday):
    out = ask.ask(holiday["ctx"], "Why are my sales down?")
    assert out["day"] == (HOLIDAY_NOW.date() - timedelta(days=1)).isoformat()


# ═════════════════════════════════════════════════════════════════════════════
# WHAT-IF — the simulator, with its assumption shown
# ═════════════════════════════════════════════════════════════════════════════

def _item(demo, name):
    return demo["db"].query(models.MenuItem).filter(models.MenuItem.restaurant_id == demo["rid"]["A"], models.MenuItem.name == name).one()


def test_what_if_a_price_to_a_figure_equals_the_simulator(demo):
    from ai.simulation.engine import simulate_price_change
    chips = _item(demo, "Chips")
    out = ask.ask(demo["A"], "What if I raise the price of Chips to 350?")
    sim = simulate_price_change(demo["db"], demo["rid"]["A"], chips.id, 35_000, demo["A"].settings)
    assert out["form"] == "what_if" and out["state"] in ("live", "stale", "learning")
    rows = {r["key"]: r for r in out["rows"]}
    assert rows["price_from"]["value"] == chips.price / 100 and rows["price_to"]["value"] == 350.0
    assert rows["profit_change_month"]["value"] == pytest.approx(sim["deltas"]["profit_cents_month"] / 100, abs=0.01)
    assert rows["sales_change_pct"]["value"] == sim["deltas"]["sales_pct"]
    assert rows["margin_to"]["value"] == sim["projected"]["margin_pct"]
    assert answers.ungrounded(out) == []


def test_what_if_shows_the_assumption_it_used(demo):
    out = ask.ask(demo["A"], "What if I raise the price of Chips to 350?")
    by_setting = {a.get("setting"): a for a in out["assumptions"] if a.get("setting")}
    assert by_setting["price_sensitivity"]["value"] == demo["A"].settings.price_sensitivity
    texts = " ".join(a["text"] for a in out["assumptions"])
    assert "elasticity" not in texts.lower()                                             # owner words, not the model's name
    assert "guess" in texts.lower() or "rough" in texts.lower()


def test_what_if_a_percentage_cut_is_a_new_price(demo):
    burger = _item(demo, "Burger")
    out = ask.ask(demo["A"], "What if I cut Burger by 10%?")
    rows = {r["key"]: r for r in out["rows"]}
    assert rows["price_to"]["value"] == pytest.approx(burger.price / 100 * 0.9, abs=0.5)
    assert rows["price_to"]["value"] < rows["price_from"]["value"]


def test_what_if_names_a_verdict_in_owner_words_not_a_command(demo):
    out = ask.ask(demo["A"], "What if I raise the price of Chips to 350?")
    assert out["verdict"] in ("Worth trying", "Be careful", "Not worth it")


def test_what_if_does_not_change_anything(demo):
    before = [(m.id, m.price) for m in demo["db"].query(models.MenuItem).filter_by(restaurant_id=demo["rid"]["A"]).order_by(models.MenuItem.id)]
    ask.ask(demo["A"], "What if I raise the price of Chips to 350?")
    ask.ask(demo["A"], "What if I cut Burger by 10%?")
    after = [(m.id, m.price) for m in demo["db"].query(models.MenuItem).filter_by(restaurant_id=demo["rid"]["A"]).order_by(models.MenuItem.id)]
    assert before == after


def test_what_if_asks_instead_of_guessing_a_dish_or_a_price(demo):
    unknown = ask.ask(demo["A"], "What if I raise the price of Unicorn steak to 900?")
    assert unknown["state"] == "unavailable" and "Unicorn steak" in unknown["reason"]
    names = {m.name for m in demo["db"].query(models.MenuItem).filter_by(restaurant_id=demo["rid"]["A"])}
    assert unknown["next"] and all(any(n in suggestion for n in names) for suggestion in unknown["next"])     # offers real dishes
    no_price = ask.ask(demo["A"], "What if I change the price of Chips?")
    assert no_price["state"] == "unavailable" and "price" in no_price["reason"].lower()
    nothing = ask.ask(demo["A"], "What if?")
    assert nothing["state"] == "unavailable"


def test_what_if_never_reaches_another_restaurants_dish(demo):
    # branch B asked about a dish id that only exists in A's menu: the dish is found by NAME inside B's own menu
    out = ask.ask(demo["B"], "What if I raise the price of Chips to 350?")
    chips_b = demo["db"].query(models.MenuItem).filter_by(restaurant_id=demo["rid"]["B"], name="Chips").one()
    rows = {r["key"]: r for r in out["rows"]}
    assert rows["price_from"]["value"] == chips_b.price / 100


# ═════════════════════════════════════════════════════════════════════════════
# WHAT SHOULD I DO — Home's ranking by KES
# ═════════════════════════════════════════════════════════════════════════════

def test_what_to_do_is_the_home_ranking_by_kes(demo):
    out = ask.ask(demo["A"], "What should I do to make more money?")
    ranked = compose_home(demo["A"], "30d")["costing_you_money"]["ranked"]
    assert out["form"] == "what_to_do" and out["state"] in ("live", "stale")
    assert [r["id"] for r in out["rows"]] == [c["id"] for c in ranked[: len(out["rows"])]]
    assert len(out["rows"]) == min(5, len(ranked))
    assert all(r["unit"] == "kes" and r["value"] > 0 and r["action"] for r in out["rows"])
    assert answers.ungrounded(out) == []


def test_what_to_do_with_a_goal_adds_up_the_ideas_until_it_is_met(demo):
    out = ask.ask(demo["A"], "How can I find KES 5,000 more a month?")
    assert out["goal_kes"] == 5000.0
    assert out["covered_by"] <= len(out["rows"]) and out["total_kes"] == pytest.approx(sum(r["value"] for r in out["rows"][: out["covered_by"]]), abs=0.01)
    assert out["total_kes"] >= 5000.0
    assert any("estimate" in a["text"].lower() for a in out["assumptions"])              # the ideas are estimates and say so


def test_what_to_do_with_a_goal_larger_than_every_idea_says_so(demo):
    out = ask.ask(demo["A"], "How can I find KES 90,000,000 more a month?")
    assert out["covered_by"] is None and "not enough" in out["headline"].lower()


def test_what_to_do_on_a_restaurant_with_nothing_to_say_is_honest():
    # a fresh tenant: nothing recorded, so no ranking and no invented advice
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = models.Tenant(name="Empty")
    db.add(tenant)
    db.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Empty", address="x")
    db.add(restaurant)
    owner = models.User(tenant_id=tenant.id, email="e@e.test", hashed_password="x", role=models.Role.STAFF, staff_role=models.StaffRole.OWNER, token_version=0)
    db.add(owner)
    db.commit()
    out = ask.ask(OwnerContext(db, owner, restaurant), "What should I do?")
    assert out["state"] in ("no_data", "unavailable") and out["rows"] == [] and out["reason"]
    db.close()
    engine.dispose()


# ═════════════════════════════════════════════════════════════════════════════
# COMPARE — P14 branches, and a period against the one before it
# ═════════════════════════════════════════════════════════════════════════════

def test_compare_branches_puts_the_two_food_costs_side_by_side(demo):
    out = ask.ask(demo["A"], "Compare my branches")
    assert out["form"] == "compare" and out["kind"] == "branches"
    cols = {c["name"]: c for c in out["columns"]}
    assert set(cols) == {"Demo Restaurant", "Demo Restaurant – Kasarani"}
    a, b = cols["Demo Restaurant"], cols["Demo Restaurant – Kasarani"]
    assert 28.0 <= a["food_cost_pct"] <= 30.0 and 36.0 <= b["food_cost_pct"] <= 38.0      # P14: 29% vs 37%
    from owner import areas
    assert a["food_cost_pct"] == areas._money_cost_dials(demo["A"])["food_cost_pct"]         # the very figure on that branch's Home
    assert b["food_cost_pct"] == areas._money_cost_dials(demo["B"])["food_cost_pct"]
    assert out["rows"][0]["key"] == "food_cost_pct"
    assert "Kasarani" in out["headline"] and answers.pct_text(b["food_cost_pct"]) in out["headline"] and answers.pct_text(a["food_cost_pct"]) in out["headline"]
    assert answers.ungrounded(out) == []


def test_compare_branches_names_the_gap_in_points_and_in_kes(demo):
    out = ask.ask(demo["A"], "Compare my branches")
    gap = next(r for r in out["rows"] if r["key"] == "food_cost_gap")
    assert gap["value"] > 5 and gap["unit"] == "pct_points"
    cost = next(r for r in out["rows"] if r["key"] == "gap_kes_month")
    assert cost["value"] > 0 and cost["unit"] == "kes"
    assert any("estimate" in a["text"].lower() for a in out["assumptions"])


def test_compare_is_the_same_from_either_branch(demo):
    a = ask.ask(demo["A"], "Compare my branches")
    b = ask.ask(demo["B"], "Compare my branches")
    assert [(c["name"], c["food_cost_pct"]) for c in a["columns"]] == [(c["name"], c["food_cost_pct"]) for c in b["columns"]]


def test_compare_periods_matches_the_sales_in_each_week_for_the_same_finished_days(demo):
    """Like for like: the days of this week that are over, against the same days of last week. On a Monday nothing of this week
    is over, so the answer says so and compares last week with the one before it."""
    from owner.money.pnl import period_range
    ctx = demo["A"]
    out = ask.ask(ctx, "This week vs last week")
    assert out["kind"] == "periods"
    today = eat_date(ctx.now)
    monday = period_range("week", today)[0]
    finished = (today - monday).days                                                        # Monday … yesterday
    if finished:
        this_lo, last_lo, days = monday, monday - timedelta(days=7), finished
    else:
        this_lo, last_lo, days = monday - timedelta(days=7), monday - timedelta(days=14), 7
    cols = {c["key"]: c for c in out["columns"]}
    assert cols["this"]["days"] == cols["last"]["days"] == days
    assert cols["this"]["sales"] == pytest.approx(sum(_day_sales(demo["db"], demo["rid"]["A"], this_lo + timedelta(days=i)) for i in range(days)), abs=0.01)
    assert cols["last"]["sales"] == pytest.approx(sum(_day_sales(demo["db"], demo["rid"]["A"], last_lo + timedelta(days=i)) for i in range(days)), abs=0.01)
    texts = " ".join(a["text"].lower() for a in out["assumptions"])
    assert "finished days" in texts
    if not finished:
        assert "no finished day" in out["headline"].lower() or "no finished day" in texts
    assert answers.ungrounded(out) == []


def test_compare_a_month_with_the_last(demo):
    out = ask.ask(demo["A"], "How is this month compared with last month?")
    assert out["kind"] == "periods" and [c["key"] for c in out["columns"]] == ["this", "last"]


def test_compare_branches_on_a_one_branch_restaurant_says_so_and_offers_periods(db_session):
    g = _tenant(db_session, "solo", branches=1)
    out = ask.ask(OwnerContext(db_session, g["owner"], g["restaurants"][0]), "Compare my branches")
    assert out["state"] == "no_data" and "one branch" in out["reason"].lower()
    assert any("last week" in n.lower() for n in out["next"])


def _tenant(db, name, branches=1):
    tenant = models.Tenant(name=f"Tenant {name}")
    db.add(tenant)
    db.flush()
    restaurants = []
    for i in range(branches):
        r = models.Restaurant(tenant_id=tenant.id, name=f"{name} branch {i + 1}", address="x")
        db.add(r)
        restaurants.append(r)
    owner = models.User(tenant_id=tenant.id, email=f"{name}@o.test", hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF,
                        staff_role=models.StaffRole.OWNER, token_version=0)
    db.add(owner)
    db.commit()
    return {"owner": owner, "restaurants": restaurants}


def test_compare_never_shows_another_tenants_branches(db_session):
    mine = _tenant(db_session, "mine", branches=2)
    other = _tenant(db_session, "other", branches=2)
    out = ask.ask(OwnerContext(db_session, mine["owner"], mine["restaurants"][0]), "Compare my branches")
    names = {c["name"] for c in out.get("columns", [])}
    assert names <= {r.name for r in mine["restaurants"]}
    assert not names & {r.name for r in other["restaurants"]}
    assert "other branch" not in str(out)


# ═════════════════════════════════════════════════════════════════════════════
# The endpoint
# ═════════════════════════════════════════════════════════════════════════════

API = "/api/v1/owner"


def _headers(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': 0})}"}


@pytest.fixture
def solo(db_session):
    return _tenant(db_session, "solo", branches=1)


def test_the_endpoint_takes_a_form_and_rejects_an_unknown_one(client, solo):
    h = _headers(solo["owner"])
    ok = client.post(f"{API}/ask", headers=h, json={"question": "Compare my branches", "form": "compare"})
    assert ok.status_code == 200 and ok.json()["form"] == "compare"
    assert client.post(f"{API}/ask", headers=h, json={"question": "Compare my branches", "form": "poetry"}).status_code == 422
    assert client.post(f"{API}/ask", headers=h, json={"question": "hi"}).status_code == 422


def test_the_form_the_owner_picks_beats_the_words_of_the_question(client, solo):
    h = _headers(solo["owner"])
    out = client.post(f"{API}/ask", headers=h, json={"question": "sales on Tuesday", "form": "why"}).json()
    assert out["form"] == "why"


def test_the_endpoint_is_owner_only(client, db_session):
    g = _tenant(db_session, "staffer", branches=1)
    cashier = models.User(tenant_id=g["owner"].tenant_id, email="c@staffer.test", hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF,
                          staff_role=models.StaffRole.MANAGER, token_version=0)
    db_session.add(cashier)
    db_session.commit()
    res = client.post(f"{API}/ask", headers=_headers(cashier), json={"question": "Compare my branches"})
    assert res.status_code in (401, 403)


def test_the_endpoint_never_leaks_internals_when_an_engine_fails(client, solo, monkeypatch):
    from owner import answer_compare
    monkeypatch.setattr(answer_compare, "build", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("engine exploded")))
    res = client.post(f"{API}/ask", headers=_headers(solo["owner"]), json={"question": "Compare my branches"})
    assert res.status_code == 200 and res.json()["state"] == "unavailable"
    assert "engine exploded" not in res.text and "Traceback" not in res.text


SYSTEM_WORDS = ("Plowhorse", "Puzzle", "REPRICE", "SURGE", "STIMULATE", "DISPUTED", "variance", "theoretical", "COGS", "reconciliation",
                "contribution", "elasticity", "custody", "par level", "voids", "EWM")


def test_no_system_word_and_no_cents_reach_the_owner_in_any_form(demo):
    texts = []
    for q in GROUNDING_QUESTIONS:
        out = ask.ask(demo["A"], q)
        texts.append((q, out))

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from walk(v, f"{path}.{k}")
                yield path, k, v
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, f"{path}[{i}]")
    for q, out in texts:
        for path, key, value in walk({k: v for k, v in out.items() if k != "answer"}):        # `answer` is the old handlers' card, unchanged
            assert "cents" not in key, (q, path, key)
            if key in ("headline", "label", "note", "text", "reason", "verdict", "topic_label") and isinstance(value, str):        # `why` is the "Why?" detail, where system words are allowed (SPEC §3.4)
                for word in SYSTEM_WORDS:
                    assert not re.search(rf"\b{re.escape(word)}\b", value), f"{word!r} in {q!r}: {value!r}"
    for q, out in texts:
        assert out["state"] in STATES and out["form"] in ask.FORMS


# ═════════════════════════════════════════════════════════════════════════════
# WHY — the "ran out" evidence, pinned on a small restaurant where every row is known
# ═════════════════════════════════════════════════════════════════════════════

TUESDAY = date(2026, 10, 20)
NOW_WED = datetime(2026, 10, 28, 10, 0)


def _utc(day, hour, minute=0):
    """A Nairobi wall-clock time as the naive UTC the database stores."""
    return datetime(day.year, day.month, day.day, hour, minute) - timedelta(hours=3)


def _chips_world(db, *, still_selling_after_empty=False, ledger_on_the_day=True):
    """Seven earlier Tuesdays with chips sold evenings; on the Tuesday the potatoes run short at 17:50 (Nairobi) and burgers go on to 21:00."""
    from tests.fixtures import golden_restaurant as gr
    g = gr.build_skeleton(db, now=NOW_WED, suffix="chips")
    chips, burger, potatoes = g.items["Chips"], g.items["Burger"], g.inventory["Potatoes"]
    for k in range(1, 8):
        d = TUESDAY - timedelta(days=7 * k)
        for hour in (12, 13, 15, 18, 19, 20, 20, 21):
            gr.add_order(db, g, [(chips, 4, 30_000), (burger, 1, 60_000)], _utc(d, hour, 5))
    for hour, minute in ((12, 10), (13, 5), (15, 0), (17, 50)):
        gr.add_order(db, g, [(chips, 1, 30_000)], _utc(TUESDAY, hour, minute))
    for hour in (19, 20, 21):
        gr.add_order(db, g, [(burger, 1, 60_000)], _utc(TUESDAY, hour, 0))
    if still_selling_after_empty:
        gr.add_order(db, g, [(chips, 1, 30_000)], _utc(TUESDAY, 19, 30))
    if ledger_on_the_day:
        # 1.2 kg at the start of the day; four plates of 0.30 kg leave 0.9, 0.6, 0.3, 0.0 — the shelf holds less than one serving after the 17:50 plate
        db.add(models.StockMovement(inventory_item_id=potatoes.id, movement_type=models.StockMovementType.ADJUST, quantity=0.0, reason="count", created_at=_utc(TUESDAY, 6)))
        for hour, minute in ((12, 10), (13, 5), (15, 0), (17, 50)):
            db.add(models.StockMovement(inventory_item_id=potatoes.id, movement_type=models.StockMovementType.OUT, quantity=0.3, reason="sale", created_at=_utc(TUESDAY, hour, minute)))
        db.add(models.StockMovement(inventory_item_id=potatoes.id, movement_type=models.StockMovementType.IN, quantity=20.0, reason="delivery", created_at=_utc(TUESDAY + timedelta(days=2), 8)))
        potatoes.quantity = 20.0                                                           # the delivery two days later is on the shelf now
        # the start of the Tuesday must come out as 1.2 kg: now (20.0) less the delivery (20.0) less the day's movements (-1.2)
    else:
        potatoes.quantity = 0.0
    db.commit()
    return g


def test_a_shelf_that_is_empty_in_the_ledger_but_unrecorded_that_day_is_not_called_empty(db_session):
    from owner import answer_why
    g = _chips_world(db_session, ledger_on_the_day=False)
    ctx = OwnerContext(db_session, g.owner, g.restaurant)
    ctx.now = NOW_WED
    assert answer_why._ran_short_at(ctx, g.inventory["Potatoes"], TUESDAY, 0.3) is None
    driver = answer_why._stock_out(ctx, TUESDAY, [TUESDAY - timedelta(days=7 * k) for k in range(1, 8)], 0.5)
    assert driver["found"] is False


def test_the_ledger_is_replayed_from_the_start_of_the_day_whatever_came_in_later(db_session):
    """The shelf at the start of the Tuesday is today's quantity, less everything recorded since — including a delivery two days later."""
    from owner import answer_why
    g = _chips_world(db_session)
    ctx = OwnerContext(db_session, g.owner, g.restaurant)
    ctx.now = NOW_WED
    short = answer_why._ran_short_at(ctx, g.inventory["Potatoes"], TUESDAY, 0.3)
    assert short is not None and short.date() == TUESDAY
    assert (short.hour, short.minute) == (17, 50)                                          # Nairobi wall clock: the fourth plate left 0.0 on the shelf


def test_a_dish_that_ran_out_is_found_with_the_time_of_its_last_plate(db_session):
    g = _chips_world(db_session)
    ctx = OwnerContext(db_session, g.owner, g.restaurant)
    ctx.now = NOW_WED
    out = ask.ask(ctx, "Why was Tuesday last week bad?")
    stock = next(d for d in out["drivers"] if d["key"] == "stock_out")
    assert stock["found"] and stock["dish"] == "Chips" and stock["ingredient"] == "Potatoes"
    assert "5:50 pm" in stock["note"] and "9:00 pm" in stock["note"]                         # its last plate, and when the restaurant stopped taking orders


def test_a_dish_that_kept_selling_after_the_ledger_says_empty_is_not_called_out(db_session):
    """If chips sold at 19:30 the potatoes were not gone: the ledger is wrong or incomplete, and the answer does not blame a stock-out."""
    g = _chips_world(db_session, still_selling_after_empty=True)
    ctx = OwnerContext(db_session, g.owner, g.restaurant)
    ctx.now = NOW_WED
    out = ask.ask(ctx, "Why was Tuesday last week bad?")
    assert next(d for d in out["drivers"] if d["key"] == "stock_out")["found"] is False


def test_a_stock_out_only_counts_if_the_restaurant_kept_trading(db_session):
    """No order after the shelf emptied → the restaurant closed, it did not run out of a dish."""
    from owner import answer_why
    g = _chips_world(db_session)
    db_session.query(models.Order).filter(models.Order.restaurant_id == g.rid, models.Order.created_at >= _utc(TUESDAY, 18, 0),
                                          models.Order.created_at < _utc(TUESDAY + timedelta(days=1), 0, 0)).delete()
    db_session.commit()
    ctx = OwnerContext(db_session, g.owner, g.restaurant)
    ctx.now = NOW_WED
    driver = answer_why._stock_out(ctx, TUESDAY, [TUESDAY - timedelta(days=7 * k) for k in range(1, 8)], 0.5)
    assert driver["found"] is False


def _staff(db, g, name="Wanjiru"):
    member = models.StaffMember(restaurant_id=g.rid, name=name, role_title="Waiter", hourly_rate=10_000)
    db.add(member)
    db.flush()
    return member


def _shifts(db, g, member, on, hours):
    db.add(models.LaborShift(restaurant_id=g.rid, staff_member_id=member.id, shift_date=on, actual_hours=hours, labor_cost=int(hours * 10_000)))


def test_fewer_staff_hours_than_a_usual_day_is_a_driver_and_says_how_many(db_session):
    from owner import answer_why
    g = _chips_world(db_session)
    member = _staff(db_session, g)
    for k in range(1, 8):
        _shifts(db_session, g, member, TUESDAY - timedelta(days=7 * k), 8.0)
        _shifts(db_session, g, _staff(db_session, g, f"Otieno{k}"), TUESDAY - timedelta(days=7 * k), 8.0)
    _shifts(db_session, g, member, TUESDAY, 8.0)                                            # one person where there are usually two
    db_session.commit()
    ctx = OwnerContext(db_session, g.owner, g.restaurant)
    d = answer_why._staffing(ctx, TUESDAY, [TUESDAY - timedelta(days=7 * k) for k in range(1, 8)], "Tuesday")
    assert d["found"] and d["value"] == 8.0 and d["unit"] == "hours"
    assert "8 staff hours" in d["note"] and "16" in d["note"]


def test_the_same_staff_hours_as_a_usual_day_is_said_to_be_in_line(db_session):
    from owner import answer_why
    g = _chips_world(db_session)
    member = _staff(db_session, g)
    for k in range(0, 8):
        _shifts(db_session, g, member, TUESDAY - timedelta(days=7 * k), 8.0)
    db_session.commit()
    d = answer_why._staffing(OwnerContext(db_session, g.owner, g.restaurant), TUESDAY, [TUESDAY - timedelta(days=7 * k) for k in range(1, 8)], "Tuesday")
    assert d["found"] is False and "in line" in d["note"]


def test_no_staff_shifts_recorded_is_not_reported_as_nothing_unusual(db_session):
    from owner import answer_why
    g = _chips_world(db_session)
    d = answer_why._staffing(OwnerContext(db_session, g.owner, g.restaurant), TUESDAY, [TUESDAY - timedelta(days=7 * k) for k in range(1, 8)], "Tuesday")
    assert d["found"] is False and "No staff shifts recorded" in d["note"]


def _cancel(db, g, day, n):
    from tests.fixtures import golden_restaurant as gr
    for i in range(n):
        gr.add_order(db, g, [(g.items["Chips"], 1, 30_000)], _utc(day, 14, i), paid=False, status=models.OrderStatus.CANCELLED)


def test_many_cancelled_sales_on_the_day_are_a_driver_that_names_no_one(db_session):
    from owner import answer_why
    g = _chips_world(db_session)
    _cancel(db_session, g, TUESDAY, 5)
    db_session.commit()
    d = answer_why._cancelled(OwnerContext(db_session, g.owner, g.restaurant), TUESDAY, [TUESDAY - timedelta(days=7 * k) for k in range(1, 8)], "Tuesday")
    assert d["found"] and d["value"] == 1500.0 and "5 sales were cancelled" in d["note"]
    assert "not a finding about anyone" in d["note"]


def test_a_few_cancelled_sales_in_line_with_a_usual_day_are_not_a_driver(db_session):
    from owner import answer_why
    g = _chips_world(db_session)
    for k in range(0, 8):
        _cancel(db_session, g, TUESDAY - timedelta(days=7 * k), 2)
    db_session.commit()
    d = answer_why._cancelled(OwnerContext(db_session, g.owner, g.restaurant), TUESDAY, [TUESDAY - timedelta(days=7 * k) for k in range(1, 8)], "Tuesday")
    assert d["found"] is False and "in line" in d["note"]


# ═════════════════════════════════════════════════════════════════════════════
# The saved conversation
# ═════════════════════════════════════════════════════════════════════════════

def _owner_with_conversation(db, name="talker"):
    g = _tenant(db, name, branches=1)
    g["owner"].role = models.Role.ADMIN                                                   # the conversation history is the owner's own
    conv = models.OwnerOSConversation(owner_user_id=g["owner"].id, restaurant_id=g["restaurants"][0].id, title="Chat")
    db.add(conv)
    db.commit()
    return g, conv


def test_an_answer_is_saved_in_the_owners_conversation_and_comes_back_when_asked_again(client, db_session):
    g, conv = _owner_with_conversation(db_session)
    h = _headers(g["owner"])
    first = client.post(f"{API}/ask", headers=h, json={"question": "Compare my branches", "conversation_id": conv.id, "client_message_id": "m1"}).json()
    assert first["conversation_id"] == conv.id and first["form"] == "compare"
    messages = db_session.query(models.OwnerOSMessage).filter_by(conversation_id=conv.id).order_by(models.OwnerOSMessage.id).all()
    assert [m.role for m in messages] == ["user", "assistant"] and messages[0].content == "Compare my branches"
    assert messages[1].answer_type == "owner_compare" and "headline" in messages[1].content
    again = client.post(f"{API}/ask", headers=h, json={"question": "Compare my branches", "conversation_id": conv.id, "client_message_id": "m1"}).json()
    assert again == first                                                                  # saved answer, not worked out twice
    assert db_session.query(models.OwnerOSMessage).filter_by(conversation_id=conv.id).count() == 2


def test_the_saved_conversation_lists_in_previous_conversations_and_reads_back(client, db_session):
    g, conv = _owner_with_conversation(db_session, "reader")
    h = _headers(g["owner"])
    client.post(f"{API}/ask", headers=h, json={"question": "What should I do?", "conversation_id": conv.id, "client_message_id": "m1"})
    listed = client.get("/api/v1/ai/os/conversations", headers=h).json()["conversations"]
    assert [c["id"] for c in listed] == [conv.id]
    messages = client.get(f"/api/v1/ai/os/conversations/{conv.id}", headers=h).json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]


def test_a_conversation_of_another_owner_is_not_found_and_nothing_is_written(client, db_session):
    mine, _ = _owner_with_conversation(db_session, "mine2")
    theirs, theirs_conv = _owner_with_conversation(db_session, "theirs2")
    res = client.post(f"{API}/ask", headers=_headers(mine["owner"]), json={"question": "Compare my branches", "conversation_id": theirs_conv.id})
    assert res.status_code == 404
    assert db_session.query(models.OwnerOSMessage).filter_by(conversation_id=theirs_conv.id).count() == 0


def test_without_a_conversation_nothing_is_saved(client, db_session):
    g, conv = _owner_with_conversation(db_session, "nosave")
    client.post(f"{API}/ask", headers=_headers(g["owner"]), json={"question": "Compare my branches"})
    assert db_session.query(models.OwnerOSMessage).count() == 0


def test_my_best_seller_is_the_dish_that_sells_most_the_way_home_asks_it(demo):
    """Home links to "What if I raise the price of my best seller?": the dish is found, and the missing price is asked for."""
    top = (demo["db"].query(models.MenuItem.name, func.sum(models.OrderItem.quantity).label("n"))
           .join(models.OrderItem, models.OrderItem.menu_item_id == models.MenuItem.id).join(models.Order, models.Order.id == models.OrderItem.order_id)
           .filter(models.Order.restaurant_id == demo["rid"]["A"], models.MenuItem.restaurant_id == demo["rid"]["A"], models.MenuItem.price > 0)
           .group_by(models.MenuItem.id, models.MenuItem.name).order_by(func.sum(models.OrderItem.quantity).desc(), models.MenuItem.name).first())
    out = ask.ask(demo["A"], "What if I raise the price of my best seller?")
    assert out["form"] == "what_if" and out["state"] == "unavailable"
    assert top.name in out["reason"] and "price" in out["reason"].lower()
    done = ask.ask(demo["A"], "What if I raise my best seller by 10%?")
    assert done["state"] in ("live", "stale", "learning") and done["dish"] == top.name
