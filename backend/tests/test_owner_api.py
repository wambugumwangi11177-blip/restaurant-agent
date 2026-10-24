"""
S1.4 — the owner API: GET /owner/home · /owner/area/{key} · /owner/report/{period} · POST /owner/ask
(docs/v2/SPEC.md §3.1, §2).

What this pins:
  * a fresh tenant gets every block with an honest `state` (no_data / unavailable), never an error and never a number;
  * the golden restaurant gets the engines' real numbers, reshaped (KES at the edge, owner words, one state each);
  * `learning` carries "day n of N", `stale` carries its age, `as_entered` carries the Nairobi date of the last entry;
  * one engine failing never takes Home down — only its own block says "could not be read";
  * /owner/area/{key} is exactly the block Home embeds; costing_you_money is exactly /overview/today's attention list;
    report content equals /reports; ask delegates to the ai_ask handlers;
  * owner-only, tenant-isolated on every endpoint, observer-mode blocked;
  * no `*_cents` key and no system word reaches an owner screen.
"""
import json
import re
from datetime import timedelta

import pytest

import auth
import models
from owner.states import STATES
from tests.fixtures import golden_restaurant as gr
from time_utils import utcnow

API = "/api/v1/owner"
AREA_KEYS = ("money", "sales_dishes", "store", "cash", "staff", "permits")
REPORT_PERIODS = ("daily", "weekly", "monthly", "yearly")


# ── helpers ───────────────────────────────────────────────────────────────────

def _headers(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': 0})}"}


def _fresh(db, suffix="fresh", staff_role=models.StaffRole.OWNER):
    tenant = models.Tenant(name=f"Tenant {suffix}")
    db.add(tenant)
    db.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"Fresh {suffix}", address="x")
    db.add(restaurant)
    user = models.User(tenant_id=tenant.id, email=f"{suffix}@fresh.test", hashed_password=auth.get_password_hash("x"),
                       role=models.Role.STAFF, staff_role=staff_role, token_version=0)
    db.add(user)
    db.commit()
    return restaurant, user


def _walk(node, path=""):
    """Yield (path, key, value) for every dict entry in a JSON-like tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield path, k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def _blocks(payload):
    """Every dict that is an owner block (has a `state`)."""
    return [(f"{p}.{k}", v) for p, k, v in _walk(payload) if isinstance(v, dict) and "state" in v]


def _strip_clock(node):
    """Drop timestamps that legitimately differ between two calls (`as_of` = request time on some blocks)."""
    if isinstance(node, dict):
        return {k: _strip_clock(v) for k, v in node.items() if k not in ("as_of", "generated_at", "updated_at", "latest_sale_at")}
    if isinstance(node, list):
        return [_strip_clock(v) for v in node]
    return node


@pytest.fixture
def golden(db_session):
    g = gr.build_skeleton(db_session)
    return g


def _get(client, g, path):
    return client.get(f"{API}{path}", headers=_headers(g.owner))


# ═════════════════════════════════════════════════════════════════════════════
# A fresh tenant: honest, never an error, never a made-up number
# ═════════════════════════════════════════════════════════════════════════════

def test_fresh_tenant_home_is_all_honest_states(client, db_session):
    _r, user = _fresh(db_session)
    res = client.get(f"{API}/home", headers=_headers(user))
    assert res.status_code == 200
    body = res.json()
    assert body["timezone"] == "Africa/Nairobi" and body["period"] == "today"
    assert set(body["areas"]) == set(AREA_KEYS)
    assert {"pulse", "costing_you_money", "health", "areas", "coming_up", "read"} <= set(body)

    blocks = _blocks(body)
    assert blocks, "no blocks found"
    for path, b in blocks:
        assert b["state"] in STATES, path
        assert "as_of" in b, path
    # a fresh tenant has nothing live: only blocks flagged `info` (the simulator pointer, the till connection
    # status) may say anything else, and an area made only of those is no_data
    for path, b in blocks:
        if b["state"] in ("live", "stale", "as_entered", "learning") and not b.get("info"):
            pytest.fail(f"fresh tenant has a '{b['state']}' block at {path}")
    for key, area in body["areas"].items():
        assert area["state"] in ("no_data", "unavailable"), key

    assert body["pulse"]["state"] == "no_data"
    assert body["pulse"]["sales_today"] == 0.0
    tiles = {t["area"]: t for t in body["health"]["tiles"]}
    assert set(tiles) == set(AREA_KEYS)
    for key in ("money", "sales_dishes", "store", "staff"):
        assert tiles[key]["number"] is None and tiles[key]["status"] == "unknown", key
    assert body["health"]["state"] == "no_data"
    assert body["costing_you_money"]["cards"] == []


def test_fresh_tenant_every_area_and_report_answers(client, db_session):
    _r, user = _fresh(db_session)
    h = _headers(user)
    for key in AREA_KEYS:
        res = client.get(f"{API}/area/{key}", headers=h)
        assert res.status_code == 200 and res.json()["key"] == key, key
    for period in REPORT_PERIODS:
        res = client.get(f"{API}/report/{period}", headers=h)
        assert res.status_code == 200, period
        assert res.json()["state"] == "no_data" and res.json()["period"] == period
    assert client.get(f"{API}/home?period=7d", headers=h).status_code == 200
    assert client.get(f"{API}/home?period=30d", headers=h).status_code == 200


def test_not_yet_built_parts_say_so_instead_of_inventing_a_number(client, db_session):
    _r, user = _fresh(db_session)
    body = client.get(f"{API}/home", headers=_headers(user)).json()
    money = body["areas"]["money"]["blocks"]
    for name in ("pnl", "breakeven", "bills", "spikes"):                              # S3.2/S3.3: built, and honest when nothing is recorded
        assert money[name]["state"] == "no_data" and money[name]["reason"], name
    assert money["pnl"]["lines"][0]["key"] == "sales" and money["pnl"]["lines"][-1]["key"] == "kept"
    mpesa = body["areas"]["cash"]["blocks"]["mpesa"]                                   # S6.2: built, and honest when no statement has been uploaded
    assert mpesa["state"] == "no_data" and "Upload your M-Pesa statement" in mpesa["reason"]
    assert body["pulse"]["money_match"]["mpesa"]["state"] == "no_data"
    assert body["pulse"]["breakeven_at"]["state"] == "no_data"
    assert body["read"]["state"] == "unavailable" and body["read"]["text"] is None
    for bill in ("bills", "licences"):
        assert body["coming_up"][bill]["state"] == "no_data" and body["coming_up"][bill]["reason"]
    assert body["areas"]["permits"]["blocks"]["licences"]["state"] == "no_data"


# ═════════════════════════════════════════════════════════════════════════════
# The golden restaurant: the engines' real numbers, in owner shape
# ═════════════════════════════════════════════════════════════════════════════

def test_golden_week_gives_the_worked_example_percentages(client, db_session, golden):
    """§7 #1: ingredients 32% of KES 100,000, wages 25%. The same numbers the engines give (E2), now on Home."""
    gr.seed_pnl_week(db_session, golden)
    body = _get(client, golden, "/home").json()
    dials = body["areas"]["money"]["blocks"]["cost_dials"]
    assert dials["food_cost_pct"] == 32.0 and dials["wages_pct"] == 25.0
    assert dials["food_cost_target_pct"] == 35.0 and dials["food_cost_word"] == "Fine"
    assert dials["wages_target_pct"] == 30.0 and dials["wages_word"] == "Fine"
    assert dials["prime_cost_pct"] == 57.0 and dials["prime_cost_target_pct"] == 62.0 and dials["prime_cost_word"] == "Fine"
    assert {a["setting"] for a in dials["assumptions"]} == {"food_cost_target_pct", "labour_target_pct", "prime_cost_target_pct"}
    assert dials["assumption"] == dials["assumptions"][0]
    head = body["areas"]["money"]["summary"]
    assert (head["number"], head["unit"], head["word"], head["status"]) == (32.0, "%", "Fine", "good")
    wages = body["areas"]["staff"]["blocks"]["wages"]
    assert wages["wages_30d"] == 25_000.0 and wages["wages_pct"] == 25.0 and wages["state"] == "as_entered"
    assert body["pulse"]["sales_in_period"] >= 0


def test_golden_price_idea_is_the_rounded_up_435(client, db_session, golden):
    """§7 #3 after D16: Quarter chicken KES 400 → 435, worth KES 10,500 a month — on Home as an idea and as a card."""
    gr.seed_chicken_reprice(db_session, golden)
    body = _get(client, golden, "/home").json()
    ideas = body["areas"]["sales_dishes"]["blocks"]["price_ideas"]
    idea = next(i for i in ideas["ideas"] if i["dish"] == "Quarter chicken")
    assert (idea["from"], idea["to"], idea["month_gain"]) == (400.0, 435.0, 10_500.0)
    assert idea["kind"] == "Priced too low"
    assert {a["setting"] for a in ideas["assumptions"]} == {"margin_floor_pct", "price_step_kes"}
    card = next(c for c in body["costing_you_money"]["cards"] if "435" in c["sentence"])
    assert card["kes_month"] == 10_500.0 and card["action"] and card["why"]


def test_golden_sold_below_menu_price(client, db_session, golden):
    """§7 #5: chips charged KES 270 against a KES 300 menu price."""
    gr.seed_chips_below_menu(db_session, golden)
    below = _get(client, golden, "/area/cash").json()["blocks"]["below_menu_price"]
    chips = next(d for d in below["dishes"] if d["dish"] == "Chips")
    assert (chips["menu_price"], chips["charged"], chips["below_pct"]) == (300.0, 270.0, 10.0)


def test_golden_cash_shifts_are_as_entered_with_the_nairobi_date(client, db_session, golden):
    from ai.cash_reconciliation.intelligence import record_drawer_count
    for start, end, expected, counted in gr.seed_cash_drawers(db_session, golden):
        record_drawer_count(db_session, golden.rid, golden.manager.id, counted, start, end)
    cash = _get(client, golden, "/area/cash").json()
    shifts = cash["blocks"]["shifts"]
    assert shifts["state"] == "as_entered"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", shifts["entered_up_to"])
    assert len(shifts["shifts"]) == 2
    by_gap = sorted(shifts["shifts"], key=lambda s: s["gap"])
    assert by_gap[0]["gap"] == -520.0 and by_gap[0]["check"] is True       # KES 520 short is over the KES 200 tolerance
    assert by_gap[1]["gap"] == -150.0 and by_gap[1]["check"] is False      # KES 150 short is inside it
    assert shifts["assumption"]["setting"] == "cash_tolerance_kes" and shifts["assumption"]["value"] == 200
    assert cash["summary"]["number"] >= 1 and cash["summary"]["status"] == "bad"


def test_golden_missing_stock_is_in_kes_and_flagged(client, db_session, golden):
    gr.seed_beef_variance(db_session, golden)
    missing = _get(client, golden, "/area/store").json()["blocks"]["missing"]
    assert missing["state"] == "as_entered"
    beef = next(i for i in missing["items"] if i["item"] == "Beef")
    assert beef["check"] is True and beef["missing"] == pytest.approx(10.0) and beef["missing_value"] == pytest.approx(10.0 * 800.0)
    assert missing["assumption"] == {"setting": "missing_stock_flag_pct", "value": 3.0, "label": "Missing stock we flag"}


def test_golden_handover_that_does_not_match_is_listed(client, db_session, golden):
    t = gr.seed_handover(db_session, golden)
    from ai.stock_custody import confirm_transfer
    confirm_transfer(db_session, t.id, golden.rid, golden.kitchen.id, 38.0)
    handover = _get(client, golden, "/area/store").json()["blocks"]["handover"]
    assert handover["state"] == "as_entered"
    row = handover["doesnt_match"][0]
    assert (row["item"], row["store_said"], row["kitchen_counted"], row["gap"]) == ("Beef", 40.0, 38.0, 2.0)


def test_period_changes_the_window_but_not_the_shape(client, db_session, golden):
    gr.seed_pnl_week(db_session, golden)
    today = _get(client, golden, "/home?period=today").json()
    week = _get(client, golden, "/home?period=7d").json()
    assert week["period"] == "7d"
    assert week["pulse"]["sales_in_period"] >= today["pulse"]["sales_in_period"]
    assert set(week) == set(today)


# ── states ───────────────────────────────────────────────────────────────────

def test_old_data_is_stale_with_its_age(client, db_session, golden):
    gr.seed_pnl_week(db_session, golden)
    for order in db_session.query(models.Order).all():
        order.created_at = order.created_at - timedelta(days=10)
    db_session.commit()
    body = _get(client, golden, "/home").json()
    assert body["pulse"]["state"] == "stale" and body["pulse"]["age_days"] >= 9
    assert body["areas"]["money"]["blocks"]["cost_dials"]["state"] == "stale"
    assert body["freshness"]["is_stale"] if "freshness" in body else body["pulse"]["freshness"]["is_stale"]


def test_home_says_whether_the_source_can_be_trusted(client, db_session, golden):
    """The shell withholds a Macsoft-fed restaurant's figures until the delivery is reconciled; Home carries what it needs."""
    fresh = _get(client, golden, "/home").json()["pulse"]["freshness"]
    assert fresh["source"] == "macsoft" and fresh["source_state"] in ("awaiting_first_delivery", "unavailable")      # no mirror in the test database
    assert fresh["source_trusted"] is False and fresh["source_reconciled"] is False and fresh["source_notice"].startswith("Recorded data only")
    tenant = db_session.get(models.Tenant, golden.owner.tenant_id)
    tenant.name = "Demo Restaurant"                                                # a restaurant that records its data here
    db_session.commit()
    direct = _get(client, golden, "/home").json()["pulse"]["freshness"]
    assert direct["source"] == "direct" and direct["source_trusted"] is True and direct["source_reconciled"] is True


def test_a_young_restaurant_is_learning_with_day_n_of_n(client, db_session, golden):
    chicken = golden.items["Quarter chicken"]
    for days_ago in range(5):
        gr.add_order(db_session, golden, [(chicken, 1, chicken.price)], golden.now - timedelta(days=days_ago, minutes=3))
    db_session.commit()
    dials = _get(client, golden, "/area/money").json()["blocks"]["cost_dials"]
    assert dials["state"] == "learning" and dials["day"] == 5 and dials["of"] == 14


# ── one engine failing never takes Home down ─────────────────────────────────

def test_one_failing_engine_only_blanks_its_own_blocks(client, db_session, golden, monkeypatch):
    gr.seed_pnl_week(db_session, golden)
    import ai.profit.intelligence as profit

    def boom(*a, **k):
        raise RuntimeError("engine exploded")
    monkeypatch.setattr(profit, "get_profit_intelligence", boom)

    res = _get(client, golden, "/home")
    assert res.status_code == 200
    body = res.json()
    dials = body["areas"]["money"]["blocks"]["cost_dials"]
    assert dials["state"] == "unavailable" and "could not be read" in dials["reason"]
    assert "engine exploded" not in json.dumps(body)                           # internals never leak
    assert body["areas"]["staff"]["blocks"]["wages"]["state"] == "as_entered"   # an unrelated engine is untouched
    assert body["pulse"]["state"] == "live"
    assert body["areas"]["money"]["summary"]["number"] is None


# ═════════════════════════════════════════════════════════════════════════════
# One path per number
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("key", AREA_KEYS)
def test_area_endpoint_is_exactly_the_block_home_embeds(client, db_session, golden, key):
    gr.seed_pnl_week(db_session, golden)
    gr.seed_cash_drawers(db_session, golden)
    home = _get(client, golden, "/home").json()
    area = _get(client, golden, f"/area/{key}").json()
    assert _strip_clock(area) == _strip_clock(home["areas"][key])


def test_costing_you_money_is_the_overview_attention_list(client, db_session, golden):
    gr.seed_chicken_reprice(db_session, golden)
    gr.seed_chips_below_menu(db_session, golden)
    costing = _get(client, golden, "/home").json()["costing_you_money"]
    legacy = client.get("/api/v1/overview/today", headers=_headers(golden.owner)).json()["attention"]
    # Same cards, same ids (so a decision made on one screen holds on the other); since S4.2 the order is Home's own: what is happening
    # now, money going out, money to make, what cannot be priced — not the legacy decision-score order.
    ranked = {c["id"] for c in costing["ranked"]}
    assert {c["id"] for c in legacy} <= ranked
    assert [c["id"] for c in costing["cards"]] == [c["id"] for c in costing["ranked"]][:5]
    decisions = [c for c in legacy if "priority_score" in c]            # cards from the decision-ranking layer
    assert decisions and all("impact_cents_month" in c for c in decisions)       # S1.4 exposes the KES behind the ranking


@pytest.mark.parametrize("period", REPORT_PERIODS)
def test_report_content_equals_the_legacy_report(client, db_session, golden, period):
    """Daily, weekly and yearly are the legacy windows, so their sales equal `/reports/{period}`. The monthly report is the calendar month
    so far (so it agrees with its Profit & Loss), not the legacy rolling 30 days: its sales are checked against that month directly."""
    gr.seed_pnl_week(db_session, golden)
    new = _get(client, golden, f"/report/{period}").json()
    sales = next(s for s in new["sections"] if s["key"] == "sales")
    if period == "monthly":
        from owner.money.pnl import nairobi_utc_range
        from routers import overview
        from time_utils import eat_date
        today = eat_date(utcnow())
        lo, hi = nairobi_utc_range(today.replace(day=1), today)
        core = overview._summarize(db_session, golden.rid, lo, hi)
        assert new["month"] == today.strftime("%Y-%m") and new["range"].endswith("so far")
        assert (sales["sales"], sales["orders"]) == ((core["revenue"], core["orders"]) if core["orders"] else (0.0, 0))
        return
    old = client.get(f"/api/v1/reports/{period}?narrate=false", headers=_headers(golden.owner)).json()
    assert new["range"] == old["range"]
    if period == "yearly" or old["orders"]:
        assert sales["state"] in ("live", "stale", "no_data")
    if old["orders"]:
        assert sales["sales"] == old["revenue"] and sales["orders"] == old["orders"]
        top = next((s for s in new["sections"] if s["key"] == "top_dishes"), None)
        if top is not None:                                                     # the yearly report is trends, not a dish list
            assert [d["name"] for d in top["dishes"]] == [t["name"] for t in old["top_items"]]
            assert [d["sold"] for d in top["dishes"]] == [t["qty"] for t in old["top_items"]]
    else:
        assert sales["state"] == "no_data"


def test_every_report_section_is_built_and_none_is_planned(client, db_session, golden):
    from owner import reports
    assert reports.planned_sections() == set()
    for period in REPORT_PERIODS:
        body = _get(client, golden, f"/report/{period}").json()
        assert body["sections"], period
        for s in body["sections"]:
            assert "planned" not in s and s["title"], (period, s["key"])
        assert "read" not in {s["key"] for s in body["sections"]}               # LEVIII's read is its own, optional, key
        assert body["read"]["text"] is None


def test_ask_delegates_to_the_deterministic_handlers(client, db_session, golden):
    gr.seed_pnl_week(db_session, golden)
    question = "how are sales going?"
    new = client.post(f"{API}/ask", headers=_headers(golden.owner), json={"question": question}).json()
    old = client.get("/api/v1/ai/ask", params={"question": question}, headers=_headers(golden.owner)).json()
    assert new["topic"] == "revenue" and new["form"] == "what"
    assert new["answer"]["finding"] == old["finding"] and new["answer"]["impact"] == old["impact"]
    assert new["state"] in ("live", "stale")
    assert new["as_of"]


def test_ask_validates_and_degrades(client, db_session, golden, monkeypatch):
    h = _headers(golden.owner)
    assert client.post(f"{API}/ask", headers=h, json={"question": "hi"}).status_code == 422
    assert client.post(f"{API}/ask", headers=h, json={"question": "x" * 501}).status_code == 422
    assert client.post(f"{API}/ask", headers=h, json={"question": "how are sales", "restaurant_id": 2}).status_code == 422
    from routers import ai_ask

    def boom(db, rid, q):
        raise RuntimeError("handler exploded")
    monkeypatch.setitem(ai_ask._HANDLERS, "revenue", boom)
    res = client.post(f"{API}/ask", headers=h, json={"question": "how are sales going?"})
    assert res.status_code == 200 and res.json()["state"] == "unavailable"
    assert "handler exploded" not in res.text


def test_unknown_area_report_and_period_are_refused(client, db_session, golden):
    assert _get(client, golden, "/area/bogus").status_code == 404
    assert _get(client, golden, "/report/hourly").status_code == 404
    assert _get(client, golden, "/home?period=1y").status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# Who may ask, and whose data they get
# ═════════════════════════════════════════════════════════════════════════════

ENDPOINTS = [("GET", "/home", None), ("GET", "/area/money", None), ("GET", "/report/daily", None),
             ("POST", "/ask", {"question": "how are sales going?"})]


@pytest.mark.parametrize("staff_role", [r for r in models.StaffRole if r != models.StaffRole.OWNER])
@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_non_owner_staff_roles_get_403(client, db_session, staff_role, method, path, body):
    _r, user = _fresh(db_session, f"s{staff_role.value}", staff_role=staff_role)
    res = client.request(method, f"{API}{path}", headers=_headers(user), json=body)
    assert res.status_code == 403, (staff_role, path)


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_unauthenticated_is_401(client, method, path, body):
    assert client.request(method, f"{API}{path}", json=body).status_code == 401


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_tenant_isolation_on_every_endpoint(client, db_session, golden, method, path, body):
    """Tenant A has the golden restaurant; tenant B's owner must see none of it — not a dish, not a figure."""
    gr.seed_pnl_week(db_session, golden)
    gr.seed_chicken_reprice(db_session, golden)
    gr.seed_beef_variance(db_session, golden)
    _rb, user_b = _fresh(db_session, "other")
    forged = {**{"Authorization": _headers(user_b)["Authorization"]}}
    res = client.request(method, f"{API}{path}", headers=forged, json=body)
    assert res.status_code == 200
    text = res.text
    for secret in ("Quarter chicken", "House set meal", "Golden Meats", "Beef", "Golden Grill"):
        assert secret not in text, f"{secret!r} leaked to another tenant via {path}"
    # and A's owner still sees their own
    mine = client.request(method, f"{API}{path}", headers=_headers(golden.owner), json=body)
    assert mine.status_code == 200 and mine.text != text


def test_forging_the_active_restaurant_does_not_cross_tenants(client, db_session, golden):
    gr.seed_chicken_reprice(db_session, golden)
    rb, user_b = _fresh(db_session, "forger")
    user_b.active_restaurant_id = golden.rid
    db_session.commit()
    body = client.get(f"{API}/home", headers=_headers(user_b)).json()
    assert body["restaurant"]["id"] == rb.id
    assert "Quarter chicken" not in json.dumps(body)


def test_owner_api_is_inside_the_observer_mode_boundary():
    from observer_mode import is_blocked_request
    for method, path in (("GET", "/api/v1/owner/home"), ("GET", "/api/v1/owner/area/money"),
                         ("GET", "/api/v1/owner/report/daily"), ("POST", "/api/v1/owner/ask")):
        assert is_blocked_request(method, path), path


# ═════════════════════════════════════════════════════════════════════════════
# Owner words on owner screens; money in KES at the edge
# ═════════════════════════════════════════════════════════════════════════════

SYSTEM_WORDS = ("Plowhorse", "Puzzle", "Dog", "Star", "REPRICE", "SURGE", "STIMULATE", "DISPUTED", "variance", "theoretical",
                "COGS", "reconciliation", "contribution", "portion_drift", "custody", "par level", "voids")


def _rich_golden(db_session, golden):
    gr.seed_pnl_week(db_session, golden)
    gr.seed_chicken_reprice(db_session, golden)
    gr.seed_chips_below_menu(db_session, golden)
    gr.seed_burger_delivery(db_session, golden)
    gr.seed_beef_variance(db_session, golden)
    gr.seed_cash_drawers(db_session, golden)
    gr.seed_menu_mix(db_session, golden)


def test_no_cents_key_reaches_the_owner(client, db_session, golden):
    _rich_golden(db_session, golden)
    payloads = [_get(client, golden, "/home").json()] + [_get(client, golden, f"/report/{p}").json() for p in REPORT_PERIODS]
    for payload in payloads:
        bad = [f"{p}.{k}" for p, k, _v in _walk(payload) if "cents" in k]
        assert bad == [], f"integer-cents keys reached the owner: {bad[:5]}"


def test_owner_vocabulary_on_labels_words_and_titles(client, db_session, golden):
    _rich_golden(db_session, golden)
    home = _get(client, golden, "/home").json()
    visible = []
    for path, key, value in _walk(home):
        if key in ("title", "word", "label", "kind", "sentence", "action", "domain") and isinstance(value, str) and not path.endswith(".period"):
            visible.append((f"{path}.{key}", value))
    assert visible
    for where, text in visible:
        for word in SYSTEM_WORDS:
            assert not re.search(rf"\b{re.escape(word)}\b", text), f"system word {word!r} on an owner screen at {where}: {text!r}"
    kinds = {v for w, v in visible if w.endswith("matrix.dishes[0].kind") or w.endswith(".kind")}
    assert kinds <= {"Best dish", "Popular, earns little", "Earns well, few order it", "Consider removing",
                     "Priced too low", "Selling hot", "Selling slowly"}


def test_money_is_kes_not_cents_at_the_edge(client, db_session, golden):
    gr.seed_pnl_week(db_session, golden)
    body = _get(client, golden, "/home").json()
    assert body["areas"]["staff"]["blocks"]["wages"]["wages_30d"] == 25_000.0            # not 2_500_000
    assert body["pulse"]["sales_in_period"] <= 100_000.0


def test_every_block_has_state_and_as_of(client, db_session, golden):
    _rich_golden(db_session, golden)
    body = _get(client, golden, "/home").json()
    for path, b in _blocks(body):
        assert b["state"] in STATES, path
        assert "as_of" in b, path
        if b["state"] == "learning":
            assert isinstance(b["day"], int) and isinstance(b["of"], int), path
        if b["state"] == "stale":
            assert "age_days" in b, path
        if b["state"] == "as_entered" and "blocks" not in b:                  # a leaf block, not an area container
            assert b.get("entered_up_to") or "settings" in path, path
        if b["state"] in ("no_data", "unavailable"):
            assert b.get("reason"), f"{path} says nothing was found but not why"


def test_home_on_the_golden_restaurant_is_fast_enough_to_use(client, db_session, golden):
    """Recorded, not tuned: SPEC §2 wants one call for Home. A very generous ceiling so a regression to N+1 queries shows."""
    import time
    _rich_golden(db_session, golden)
    t0 = time.perf_counter()
    res = _get(client, golden, "/home")
    elapsed = time.perf_counter() - t0
    assert res.status_code == 200
    print(f"\n[S1.4] GET /owner/home on the golden restaurant: {elapsed * 1000:.0f} ms, {len(res.content) / 1024:.1f} KiB")
    assert elapsed < 20


# ═════════════════════════════════════════════════════════════════════════════
# The registry and the code map stay in step
# ═════════════════════════════════════════════════════════════════════════════

def _codemap():
    import importlib.util
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = importlib.util.spec_from_file_location("codemap", os.path.join(root, "execution", "codemap.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_has_exactly_the_engines_of_figure_1_3():
    from owner.registry import BY_KEY, ENGINES
    codemap = _codemap()
    assert {e.key for e in ENGINES} == {k for k, _l, _kind, _t in codemap.ENGINES}
    assert len(BY_KEY) == len(ENGINES)


def test_registry_entries_point_at_things_that_exist():
    from owner import areas, reports
    from owner import ask as owner_ask
    from owner.registry import ENGINES
    from owner.settings import FIELDS
    setting_keys = {f.key for f in FIELDS}
    plan = {f"{p}.{k}" for p, sections in reports.PLAN.items() for k, _t in sections}
    for e in ENGINES:
        assert e.area in areas.AREAS
        assert set(e.settings) <= setting_keys, (e.key, set(e.settings) - setting_keys)
        assert set(e.os_topics) <= set(owner_ask.topics()), (e.key, e.os_topics)
        assert set(e.report_sections) <= plan, (e.key, set(e.report_sections) - plan)
        assert e.owner_name


def test_registered_planned_engines_match_the_codemap_engines_that_are_not_built():
    """An engine with no module at all is `none` in the code map and `planned` with no built blocks in the registry; a partly
    built engine (the money layer: P&L done, break-even and bills to come) has a module and is `planned` with built_blocks."""
    from owner.registry import engines
    codemap = _codemap()
    not_built = {k for k, _l, kind, _t in codemap.ENGINES if kind == "none"}
    assert {e.key for e in engines("planned") if not e.built_blocks} == not_built
    modules = {k for k, _l, kind, _t in codemap.ENGINES if kind != "none"}
    assert {e.key for e in engines("planned") if e.built_blocks} <= modules


def test_every_former_candidate_is_resolved_with_a_reason():
    from owner.registry import NOT_ENGINES
    codemap = _codemap()
    assert codemap.CANDIDATES == {}
    assert set(NOT_ENGINES) <= set(codemap.INFRASTRUCTURE)
    assert all(len(reason) > 30 for reason in NOT_ENGINES.values())


def test_every_setting_an_engine_reads_is_listed_by_at_least_one_engine_or_surface():
    """Settings that no registry entry reads are dead controls: the owner could move a slider that does nothing."""
    from owner.registry import ENGINES
    from owner.settings import FIELDS
    read = {s for e in ENGINES for s in e.settings}
    dead = {f.key for f in FIELDS} - read
    assert dead == set(), f"settings no engine reads: {sorted(dead)}"
