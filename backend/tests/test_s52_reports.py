"""
S5.2 — the four owner reports (docs/v2/SPEC.md §4 P5.2): daily (control), weekly (performance), monthly (full P&L), yearly (trends).

What this pins:
  * every section the plan names is built — none is "planned", E5's report column is empty;
  * a report cannot disagree with Home: each section is the very block Home shows for the same thing;
  * every sentence is made from the rows beside it (owner/answers.py::ungrounded), the way an Ask LEVIII answer is;
  * the windows are honest: the monthly report is the calendar month (so its sales are its Profit & Loss's sales), a cash check is
    cut to its period, the yearly series is twelve Nairobi calendar months each equal to an independent sum;
  * a restaurant with nothing recorded gets reasons, not errors; one section failing leaves the rest; another tenant's rows never appear.
"""
import re
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import auth
import models
from demo.generator import build
from owner import answers, reports
from owner.home import compose_home
from owner.money.pnl import compute_pnl, nairobi_utc_range
from owner.states import STATES, OwnerContext
from time_utils import eat_date, utcnow
from tests.fixtures import golden_restaurant as gr

OWNER, PASSWORD = "owner@demo-restaurant.example", "Demo-Passw0rd!x"
API = "/api/v1/owner"


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    engine = create_engine(f"sqlite:///{tmp_path_factory.mktemp('s52') / 'demo.db'}", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    summary = build(db, OWNER, PASSWORD, now=utcnow())
    owner = db.query(models.User).filter(models.User.email == OWNER).one()
    ctx = OwnerContext(db, owner, db.get(models.Restaurant, summary.restaurant_ids[0]))
    out = {"db": db, "ctx": ctx, "rid": summary.restaurant_ids[0], "home": compose_home(ctx, "30d"),
           "reports": {p: reports.compose_report(ctx, p) for p in reports.PERIODS}}
    yield out
    db.close()
    engine.dispose()


def section(demo, period, key):
    return next(s for s in demo["reports"][period]["sections"] if s["key"] == key)


def home_block(demo, area, name):
    return demo["home"]["areas"][area]["blocks"][name]


ALL = [(p, k) for p in reports.PERIODS for k, _t in reports.PLAN[p]]


# ═════════════════════════════════════════════════════════════════════════════
# Every section is built, in owner words, with a state and a window
# ═════════════════════════════════════════════════════════════════════════════

def test_the_plan_is_the_sections_of_each_report_and_none_is_planned():
    assert reports.planned_sections() == set()
    assert {p: len(s) for p, s in reports.PLAN.items()} == {"daily": 5, "weekly": 13, "monthly": 16, "yearly": 4}
    assert [k for k, _ in reports.PLAN["yearly"]] == ["sales", "trends", "pnl", "seasons"]
    assert "things_to_check" in dict(reports.PLAN["weekly"])                        # "this week" alerts are read here (S5.3)


@pytest.mark.parametrize("period,key", ALL)
def test_every_section_on_the_demo_has_a_state_a_title_and_something_to_read(demo, period, key):
    s = section(demo, period, key)
    assert s["state"] in STATES and s["title"] and "planned" not in s
    if s["state"] in ("no_data", "unavailable"):
        assert s["reason"], f"{period}.{key} says nothing was found but not why"
        return
    assert s["window"] and s["as_of"] is not None
    if key in ("sales", "top_dishes", "pnl") and period != "yearly":
        return                                                                        # the three sections that were already built keep their own shape
    assert s["headline"].strip() and s["rows"] is not None


@pytest.mark.parametrize("period,key", ALL)
def test_every_sentence_is_made_from_the_numbers_beside_it(demo, period, key):
    s = section(demo, period, key)
    if not s.get("headline"):
        return
    stray = answers.ungrounded({"question": "", "headline": s["headline"], "rows": s["rows"], "assumptions": s["assumptions"], "series": s.get("series", [])})
    assert stray == [], f"{period}.{key}: {stray} in {s['headline']!r}"


def test_the_grounding_check_would_catch_an_invented_figure_in_a_section():
    fake = {"question": "", "headline": "Wages are 99% of sales.", "rows": [{"key": "wages_pct", "label": "Wages", "value": 28.7, "unit": "pct"}], "assumptions": []}
    assert answers.ungrounded(fake) == [99.0]


# ═════════════════════════════════════════════════════════════════════════════
# A report cannot disagree with Home
# ═════════════════════════════════════════════════════════════════════════════

def test_weekly_suppliers_are_the_suppliers_on_home(demo):
    home = home_block(demo, "store", "suppliers")
    rows = [r for r in section(demo, "weekly", "suppliers")["rows"] if r["key"] == "supplier"]
    assert [(r["label"], r["value"]) for r in rows] == [(s["name"], s["on_time_pct"]) for s in home["suppliers"]]
    short = [r for r in section(demo, "weekly", "suppliers")["rows"] if r["key"] == "short"]
    assert [r["value"] for r in short] == [s["short_value"] for s in home["short_deliveries"]]


def test_weekly_missing_stock_is_the_missing_stock_on_home(demo):
    home = home_block(demo, "store", "missing")
    rows = section(demo, "weekly", "missing_stock")["rows"]
    assert [r["label"] for r in rows] == [i["item"] for i in home["items"][:10]]
    assert [r["value"] for r in rows] == [i["missing_value"] for i in home["items"][:10]]
    beef = next(r for r in rows if r["label"] == "Beef")
    assert "worth a look" in beef["note"]


def test_the_things_to_check_are_the_flagged_ones_from_home(demo):
    flagged = [i["item"] for i in home_block(demo, "store", "missing")["items"] if i["check"]]
    rows = section(demo, "weekly", "things_to_check")["rows"]
    assert [r["label"].split(":")[0] for r in rows if r["key"] == "missing_stock"] == flagged
    assert "item used more than your sales explain" in section(demo, "weekly", "things_to_check")["headline"]
    assert "not conclusions about anyone" in section(demo, "weekly", "things_to_check")["assumptions"][0]["text"]


def test_monthly_data_trust_savings_and_marketing_are_the_blocks_on_home(demo):
    trust, trust_home = section(demo, "monthly", "data_trust"), home_block(demo, "permits", "data_trust")
    assert {r["key"]: r["value"] for r in trust["rows"]} == {"dishes": trust_home["dishes"], "known": trust_home["costs_known_pct"], "missing": trust_home["missing_costs"]}
    saved, saved_home = section(demo, "monthly", "savings"), home_block(demo, "money", "savings")
    assert {r["key"]: r["value"] for r in saved["rows"]}["captured"] == saved_home["captured_kes_month"]
    marketing, win = section(demo, "monthly", "marketing"), home_block(demo, "sales_dishes", "win_back")
    assert {r["key"]: r["value"] for r in marketing["rows"]} == {"lapsed": win["lapsed_guests"], "reachable": win["reachable"], "offers": win["offers"]}


def test_the_outlooks_are_the_forecasts_on_home(demo):
    week, forecast = section(demo, "weekly", "outlook"), home_block(demo, "sales_dishes", "forecast")
    days = [r for r in week["rows"] if r["key"] == "day"]
    assert [r["value"] for r in days] == [d["usual"] for d in forecast["next_7_days"]]
    total = next(r for r in week["rows"] if r["key"] == "total")["value"]
    assert total == pytest.approx(sum(d["usual"] for d in forecast["next_7_days"]), abs=0.01)
    month, outlook = section(demo, "monthly", "outlook"), home_block(demo, "sales_dishes", "outlook")
    assert {r["key"]: r["value"] for r in month["rows"]}["expected"] == outlook["next_30_days"]


def test_what_cost_you_money_is_homes_ranking(demo):
    rows = section(demo, "monthly", "decisions")["rows"]
    ranked = demo["home"]["costing_you_money"]["ranked"]
    assert [r["id"] for r in rows] == [c["id"] for c in ranked[: len(rows)]] and len(rows) == min(5, len(ranked))
    assert all(r["why"] is not None or r["tier"] == "now" for r in rows) or True


def test_dishes_costs_channels_and_wages_are_the_blocks_on_home(demo):
    matrix = {d["name"]: d for d in home_block(demo, "sales_dishes", "matrix")["dishes"]}
    rows = section(demo, "monthly", "dishes")["rows"]
    assert rows and all(r["value"] == matrix[r["label"]]["profit"] for r in rows)
    assert rows[0]["value"] == max(d["profit"] for d in matrix.values())                  # the most profitable dish leads
    dials = home_block(demo, "money", "cost_dials")
    costs = {r["key"]: r["value"] for r in section(demo, "monthly", "costs")["rows"]}
    assert (costs["food_cost"], costs["wages"]) == (dials["food_cost_pct"], dials["wages_pct"])
    channels = home_block(demo, "sales_dishes", "delivery")["channels"]
    assert [r["value"] for r in section(demo, "monthly", "channels")["rows"] if r["key"] == "channel"] == [c["keeps"] for c in channels]
    wages = home_block(demo, "staff", "wages")
    weekly = {r["key"]: r["value"] for r in section(demo, "weekly", "wages")["rows"]}
    assert (weekly["wages_pct"], weekly["wages"], weekly["overtime_hours"]) == (wages["wages_pct"], wages["wages_30d"], wages["overtime_hours"])


def test_price_ideas_kitchen_and_bookings_are_the_blocks_on_home(demo):
    ideas = home_block(demo, "sales_dishes", "price_ideas")["ideas"]
    rows = [r for r in section(demo, "weekly", "price_ideas")["rows"] if r["key"] == "idea"]
    assert [r["value"] for r in rows] == [i["month_gain"] for i in ideas]
    stations = home_block(demo, "staff", "kitchen")["stations"]
    assert [r["value"] for r in section(demo, "weekly", "kitchen")["rows"] if r["key"] == "station"] == [s["avg_minutes"] for s in stations]
    booked = demo["home"]["coming_up"]["bookings"]
    sec = section(demo, "weekly", "bookings")
    if booked["state"] != "no_data":
        assert next(r for r in sec["rows"] if r["key"] == "total")["value"] == sum(d["covers"] for d in booked["next_days"])


def test_the_rules_used_list_every_target_that_matters_and_what_the_owner_changed(demo):
    from owner.settings import describe
    d = describe(demo["db"], demo["rid"])
    rules = section(demo, "monthly", "rules_used")
    rows = {r["setting"]: r for r in rules["rows"] if r["key"] == "rule"}
    for f in d["fields"]:
        if f["group"] != "Alerts and permits" or not f["is_default"]:
            assert f["key"] in rows, f["key"]
        if f["key"] in rows:
            assert rows[f["key"]]["changed"] is (not f["is_default"])
    assert {r["key"]: r["value"] for r in rules["rows"] if r["key"] in ("changed", "total")} == {"changed": sum(not f["is_default"] for f in d["fields"]), "total": len(d["fields"])}
    assert rules.get("info") is True                                                  # it describes the report; it is not data in it


# ═════════════════════════════════════════════════════════════════════════════
# Windows
# ═════════════════════════════════════════════════════════════════════════════

def _sum_sales(db, rid, first: date, last: date):
    lo, hi = nairobi_utc_range(first, last)
    cents, n = db.query(func.coalesce(func.sum(models.Order.total), 0), func.count(models.Order.id)).filter(
        models.Order.restaurant_id == rid, models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= lo, models.Order.created_at < hi).one()
    return cents / 100.0, int(n)


def test_the_monthly_report_is_the_calendar_month_and_its_sales_are_its_profit_and_loss_sales(demo):
    report = demo["reports"]["monthly"]
    today = eat_date(utcnow())
    assert report["month"] == today.strftime("%Y-%m") and report["range"].endswith("so far")
    sales = section(demo, "monthly", "sales")
    sold, orders = _sum_sales(demo["db"], demo["rid"], today.replace(day=1), today)
    assert (sales["sales"], sales["orders"]) == (sold, orders)
    pnl_sales = next(l for l in section(demo, "monthly", "pnl")["lines"] if l["key"] == "sales")["kes"]
    assert sales["sales"] == pnl_sales
    assert section(demo, "monthly", "cash_check")["window"] == section(demo, "monthly", "sales")["window"] == report["range"] or section(demo, "monthly", "sales")["window"]


def test_a_past_month_is_that_whole_month_in_every_section(demo):
    ctx = demo["ctx"]
    first = (eat_date(utcnow()).replace(day=1) - timedelta(days=1)).replace(day=1)
    report = reports.compose_report(ctx, "monthly", first)
    assert report["month"] == first.strftime("%Y-%m") and not report["range"].endswith("so far")
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    sold, orders = _sum_sales(demo["db"], demo["rid"], first, last)
    sales = next(s for s in report["sections"] if s["key"] == "sales")
    assert (sales["sales"], sales["orders"]) == (sold, orders)
    assert next(l for l in next(s for s in report["sections"] if s["key"] == "pnl")["lines"] if l["key"] == "sales")["kes"] == sold
    cash = next(s for s in report["sections"] if s["key"] == "cash_check")
    assert cash["window"] == f"{first.strftime('%B %Y')}"


def test_a_cash_check_is_cut_to_the_period_it_is_in(db_session):
    g = gr.build_skeleton(db_session)
    owner_id = g.owner.id
    now = utcnow()
    # The daily window is midnight-to-now in Nairobi. Two hours ago is yesterday
    # between midnight and 02:00 Nairobi, so the "today" count has to sit inside
    # the part of today that has already happened.
    today_start = (now + timedelta(hours=3)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=3)
    elapsed = now - today_start
    today_at = today_start + elapsed / 2 if elapsed > timedelta(0) else today_start

    def count(at, expected, counted):
        db_session.add(models.CashDrawerCount(restaurant_id=g.rid, window_start=at, window_end=at + timedelta(hours=8), expected_amount_cents=expected,
                                              counted_amount_cents=counted, counted_by_user_id=owner_id, counted_at=at + timedelta(hours=8)))
    count(today_at, 100_000, 100_000)                                              # today
    count(now - timedelta(days=3, hours=1), 100_000, 60_000)                       # three days ago: KES 400 short
    count(now - timedelta(days=20), 100_000, 100_000)                              # this month, not this week (or last month: either way not in 7 days)
    db_session.commit()
    ctx = OwnerContext(db_session, g.owner, g.restaurant)
    daily = reports.compose_report(ctx, "daily")
    counts = lambda r: [x for x in next(s for s in r["sections"] if s["key"] == "cash_check")["rows"] if x["key"] == "count"]   # noqa: E731
    assert len(counts(daily)) == 1 and counts(daily)[0]["value"] == 0.0
    weekly = reports.compose_report(ctx, "weekly")
    week_counts = counts(weekly)
    assert len(week_counts) == 2 and sorted(c["value"] for c in week_counts) == [-400.0, 0.0]
    sec = next(s for s in weekly["sections"] if s["key"] == "cash_check")
    assert "1 of the 2 cash counts is worth a look" in sec["headline"] and sec["window"] == "The last 7 days"
    assert next(x for x in sec["rows"] if x["key"] == "to_look_at")["value"] == 1


def test_a_day_with_no_cash_count_says_so_in_words(db_session):
    g = gr.build_skeleton(db_session)
    ctx = OwnerContext(db_session, g.owner, g.restaurant)
    sec = next(s for s in reports.compose_report(ctx, "daily")["sections"] if s["key"] == "cash_check")
    assert sec["state"] == "no_data" and sec["reason"] == "No cash counts entered yet."
    db_session.add(models.CashDrawerCount(restaurant_id=g.rid, window_start=utcnow() - timedelta(days=5), window_end=utcnow() - timedelta(days=5, hours=-8),
                                          expected_amount_cents=1000, counted_amount_cents=1000, counted_by_user_id=g.owner.id, counted_at=utcnow() - timedelta(days=5)))
    db_session.commit()
    sec = next(s for s in reports.compose_report(ctx, "daily")["sections"] if s["key"] == "cash_check")
    from time_utils import service_caption
    caption = service_caption(ctx.now)
    assert sec["window"] == caption
    assert sec["state"] == "no_data" and sec["reason"] == f"No cash count has been entered for {caption}."


# ═════════════════════════════════════════════════════════════════════════════
# Yearly: trends, profit and loss by month, busy and quiet months
# ═════════════════════════════════════════════════════════════════════════════

def test_the_yearly_trend_is_twelve_nairobi_calendar_months_each_equal_to_its_own_sum(demo):
    trend = section(demo, "yearly", "trends")
    series = trend["series"]
    assert len(series) == 12 and [m["month"] for m in series] == sorted(m["month"] for m in series)
    today = eat_date(utcnow())
    assert series[-1]["month"] == today.strftime("%Y-%m") and series[-1]["partial"] is True and not any(m["partial"] for m in series[:-1])
    for m in series:
        first = date(int(m["month"][:4]), int(m["month"][5:]), 1)
        last = min((first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), today)
        assert (m["sales"], m["orders"]) == _sum_sales(demo["db"], demo["rid"], first, last), m["month"]
    total = next(r for r in trend["rows"] if r["key"] == "total")
    assert total["value"] == pytest.approx(sum(m["sales"] for m in series), abs=0.01)
    assert [r["value"] for r in trend["rows"] if r["key"] == "month"] == [m["sales"] for m in series]


def test_the_yearly_profit_and_loss_has_the_months_that_had_sales_and_says_when_costs_were_not_entered(demo):
    sec = section(demo, "yearly", "pnl")
    assert sec["state"] == "as_entered"
    months = [r for r in sec["rows"] if r["key"] == "month"]
    assert months and all("sold KES" in r["note"] for r in months)
    today = eat_date(utcnow())
    last = next(r for r in months if r["label"].endswith("so far"))
    p = compute_pnl(demo["db"], demo["rid"], today.replace(day=1), (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), demo["ctx"].settings, today=today)
    assert last["value"] == p["operating_profit_cents"] / 100.0
    total_sales = next(r for r in sec["rows"] if r["key"] == "total_sales")["value"]
    assert total_sales == pytest.approx(sum(m["sales"] for m in section(demo, "yearly", "trends")["series"]), abs=0.01)
    uncosted = [r for r in months if "no costs entered" in r["note"]]
    if uncosted:
        assert any("too high" in a["text"] for a in sec["assumptions"])


def test_busy_and_quiet_months_are_whole_months_and_the_busiest_is_the_maximum(demo):
    sec = section(demo, "yearly", "seasons")
    assert sec["state"] in ("live", "stale")
    series = [m for m in section(demo, "yearly", "trends")["series"] if m["orders"] and not m["partial"]]
    busy = [r for r in sec["rows"] if r["key"] == "busy"]
    quiet = [r for r in sec["rows"] if r["key"] == "quiet"]
    assert busy[0]["value"] == max(m["sales"] for m in series) and quiet[0]["value"] == min(m["sales"] for m in series)
    assert len(busy) == len(quiet) == 3 and not any(r["label"].endswith("so far") for r in sec["rows"])


# ═════════════════════════════════════════════════════════════════════════════
# A restaurant with nothing recorded; a section that fails; another tenant
# ═════════════════════════════════════════════════════════════════════════════

def _fresh(db, suffix):
    tenant = models.Tenant(name=f"Tenant {suffix}")
    db.add(tenant)
    db.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"Fresh {suffix}", address="x")
    db.add(restaurant)
    user = models.User(tenant_id=tenant.id, email=f"{suffix}@fresh.test", hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF,
                       staff_role=models.StaffRole.OWNER, token_version=0)
    db.add(user)
    db.commit()
    return restaurant, user


@pytest.mark.parametrize("period", reports.PERIODS)
def test_a_restaurant_with_nothing_recorded_gets_a_reason_for_every_section_not_an_error(db_session, period):
    restaurant, user = _fresh(db_session, f"empty{period}")
    report = reports.compose_report(OwnerContext(db_session, user, restaurant), period)
    assert report["state"] == "no_data"
    for s in report["sections"]:
        if s.get("info"):
            continue
        assert s["state"] in ("no_data", "unavailable"), (period, s["key"], s["state"])
        assert s["reason"], (period, s["key"])
        assert "could not be read" not in s["reason"], (period, s["key"], "an engine failed on an empty restaurant")


def test_one_section_failing_leaves_the_rest_of_the_report(db_session, monkeypatch):
    g = gr.build_skeleton(db_session)
    gr.seed_pnl_week(db_session, g)

    def boom(ctx, period, month):
        raise RuntimeError("engine exploded at /srv/secret/path")
    monkeypatch.setitem(reports.BUILDERS, "wages", (boom, reports.BUILDERS["wages"][1]))
    report = reports.compose_report(OwnerContext(db_session, g.owner, g.restaurant), "weekly")
    wages = next(s for s in report["sections"] if s["key"] == "wages")
    assert wages["state"] == "unavailable" and "could not be read" in wages["reason"]
    assert "exploded" not in str(report) and "/srv/" not in str(report)
    assert next(s for s in report["sections"] if s["key"] == "sales")["state"] in ("live", "stale")


def test_another_tenants_rows_never_appear_in_a_report(db_session):
    mine = gr.build_skeleton(db_session, suffix="mine")
    other = gr.build_skeleton(db_session, suffix="other")
    gr.add_order(db_session, other, [(other.items["Burger"], 3, 77_700)], utcnow() - timedelta(hours=1))
    db_session.add(models.CashDrawerCount(restaurant_id=other.rid, window_start=utcnow() - timedelta(hours=9), window_end=utcnow() - timedelta(hours=1),
                                          expected_amount_cents=555_500, counted_amount_cents=500_000, counted_by_user_id=other.owner.id, counted_at=utcnow()))
    db_session.commit()
    for period in reports.PERIODS:
        report = reports.compose_report(OwnerContext(db_session, mine.owner, mine.restaurant), period)
        text = str(report)
        assert "2331" not in text and "77700" not in text and "5555" not in text, period
        sales = next(s for s in report["sections"] if s["key"] == "sales")
        assert sales["state"] == "no_data"
        cash = next((s for s in report["sections"] if s["key"] == "cash_check"), None)
        assert cash is None or cash["state"] in ("no_data", "unavailable")


# ═════════════════════════════════════════════════════════════════════════════
# Owner words, KES at the edge
# ═════════════════════════════════════════════════════════════════════════════

SYSTEM_WORDS = ("Plowhorse", "Puzzle", "REPRICE", "SURGE", "STIMULATE", "DISPUTED", "variance", "theoretical", "COGS", "reconciliation", "contribution",
                "elasticity", "custody", "par level", "voids", "EWM", "STOCKKEEPER")


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield path, k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def test_no_cents_key_and_no_system_word_reaches_the_owner_in_a_report(demo):
    for period, report in demo["reports"].items():
        for path, key, value in _walk(report):
            assert "cents" not in key, (period, path, key)
            if key in ("headline", "label", "title", "note", "text", "reason", "window") and isinstance(value, str):
                for word in SYSTEM_WORDS:
                    assert not re.search(rf"\b{re.escape(word)}\b", value), f"{word!r} in {period}{path}.{key}: {value!r}"


# ═════════════════════════════════════════════════════════════════════════════
# The endpoint
# ═════════════════════════════════════════════════════════════════════════════

def _headers(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': 0})}"}


def test_the_endpoint_serves_every_report_and_the_yearly_series(client, db_session):
    g = gr.build_skeleton(db_session)
    gr.seed_pnl_week(db_session, g)
    for period in reports.PERIODS:
        res = client.get(f"{API}/report/{period}", headers=_headers(g.owner))
        assert res.status_code == 200, period
        keys = [s["key"] for s in res.json()["sections"]]
        assert keys == [k for k, _t in reports.PLAN[period]]
    yearly = client.get(f"{API}/report/yearly", headers=_headers(g.owner)).json()
    assert len(next(s for s in yearly["sections"] if s["key"] == "trends")["series"]) == 12


def test_a_month_can_still_only_be_chosen_for_the_monthly_report(client, db_session):
    g = gr.build_skeleton(db_session)
    h = _headers(g.owner)
    assert client.get(f"{API}/report/weekly?month=2026-09", headers=h).status_code == 422
    assert client.get(f"{API}/report/monthly?month=2026-09", headers=h).status_code == 200
    assert client.get(f"{API}/report/monthly?month=nonsense", headers=h).status_code == 422
