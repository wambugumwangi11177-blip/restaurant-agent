"""
S1.2 — every business threshold comes from the settings service (docs/v2/SPEC.md §3.2, D11).

For each engine there is a test that CHANGING A SETTING CHANGES THE ENGINE'S OUTPUT, in both ways an engine
can receive it:
  * explicitly:  engine(db, rid, settings=Settings(...))   — what the owner API and previews will use;
  * saved:       the owner saves a value, the engine is called with no settings and reads the saved row —
                 so every existing caller (Home, OS, reports, WhatsApp, the old dashboard) honours the
                 owner's choice without being touched.
Defaults reproduce today's numbers (tests/evals/test_e2_money_goldens.py stays green unchanged); the one
documented exception is the food-cost ceiling, which was 35 in profit/pricing but 40 in the menu engine and
is now one setting (default 35).
"""
from dataclasses import replace

import pytest

import models
from owner.settings import DEFAULTS, Settings, get_settings, update_settings
from tests.fixtures import golden_restaurant as gr


def S(**changes) -> Settings:
    return replace(DEFAULTS, **changes)


def _chicken(db):
    g = gr.build_skeleton(db)
    gr.seed_chicken_reprice(db, g)
    return g


# ═════════════════════════════════════════════════════════════════════════════
# profit
# ═════════════════════════════════════════════════════════════════════════════

def test_profit_margin_floor_moves_the_leak_line(db_session):
    from ai.profit.intelligence import get_profit_intelligence
    g = _chicken(db_session)
    leaks = lambda data: [l["item_name"] for l in data["profit_leaks"]]
    status = lambda data: next(c["status"] for c in data["contribution_margins"] if c["item_name"] == "Quarter chicken")

    default = get_profit_intelligence(db_session, g.rid)
    assert "Quarter chicken" in leaks(default) and status(default) == "LEAK"          # 35% < 40% floor

    relaxed = get_profit_intelligence(db_session, g.rid, settings=S(margin_floor_pct=30))
    assert "Quarter chicken" not in leaks(relaxed) and status(relaxed) == "ACCEPTABLE"

    strict = get_profit_intelligence(db_session, g.rid, settings=S(margin_floor_pct=36, margin_target_pct=50))
    assert status(strict) == "LEAK"                                                    # 35% < 36%


def test_profit_margin_target_sets_the_star_line_and_the_leak_price(db_session):
    from ai.profit.intelligence import get_profit_intelligence
    g = _chicken(db_session)
    price_at = lambda data: next(l["suggested_price"] for l in data["profit_leaks"] if l["item_name"] == "Quarter chicken")
    assert price_at(get_profit_intelligence(db_session, g.rid)) == int(26_000 / (1 - 0.55))
    assert price_at(get_profit_intelligence(db_session, g.rid, settings=S(margin_target_pct=45))) == int(26_000 / (1 - 0.45))


def test_profit_food_cost_target_sets_status_and_recommendation(db_session):
    from ai.profit.intelligence import get_profit_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_pnl_week(db_session, g)                                                   # food cost 32.0%
    default = get_profit_intelligence(db_session, g.rid)
    assert default["summary"]["food_cost_status"] == "HEALTHY"
    assert not [r for r in default["recommendations"] if r["type"] == "food_cost"]

    stricter = get_profit_intelligence(db_session, g.rid, settings=S(food_cost_target_pct=30))
    assert stricter["summary"]["food_cost_status"] == "WARNING"                       # over 30%, within 5 points of it
    rec = next(r for r in stricter["recommendations"] if r["type"] == "food_cost")
    assert "30" in rec["message"] and "32.0" in rec["message"]


def test_profit_delivery_commission_is_the_owners_rate(db_session):
    from ai.profit.intelligence import get_profit_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_burger_delivery(db_session, g)
    per_plate = lambda data: next(c["profit"] // c["orders"] for c in data["channel_analysis"] if c["channel"] == "glovo")
    assert per_plate(get_profit_intelligence(db_session, g.rid)) == 17_000                       # 600 − 150 − 280
    assert per_plate(get_profit_intelligence(db_session, g.rid, settings=S(commission_glovo_pct=30))) == 14_000
    assert per_plate(get_profit_intelligence(db_session, g.rid, settings=S(commission_glovo_pct=0))) == 32_000


def test_profit_reads_the_saved_settings_when_none_are_passed(db_session):
    from ai.profit.intelligence import get_profit_intelligence
    g = _chicken(db_session)
    assert get_profit_intelligence(db_session, g.rid)["profit_leaks"]
    update_settings(db_session, g.rid, g.owner.id, {"margin_floor_pct": 30})
    assert get_profit_intelligence(db_session, g.rid)["profit_leaks"] == []


# ═════════════════════════════════════════════════════════════════════════════
# pricing
# ═════════════════════════════════════════════════════════════════════════════

def _rec(data, name):
    return next((r for r in data["recommendations"] if r["item_name"] == name), None)


def test_pricing_margin_floor_sets_the_reprice_target(db_session):
    from ai.pricing.recommendations import get_pricing_intelligence
    g = _chicken(db_session)
    default = _rec(get_pricing_intelligence(db_session, g.rid), "Quarter chicken")
    stricter = _rec(get_pricing_intelligence(db_session, g.rid, settings=S(margin_floor_pct=45)), "Quarter chicken")
    assert default["type"] == stricter["type"] == "REPRICE"
    assert default["new_margin_pct"] >= 40.0 and stricter["new_margin_pct"] >= 45.0
    assert stricter["suggested_price"] > default["suggested_price"] >= 26_000 / 0.6
    assert stricter["suggested_price"] >= 26_000 / 0.55
    assert "45" in stricter["reason"]
    # A dish at 35% is fine for an owner whose floor is 30%: no recommendation at all.
    assert _rec(get_pricing_intelligence(db_session, g.rid, settings=S(margin_floor_pct=30)), "Quarter chicken") is None


def test_pricing_max_raise_caps_a_surge(db_session):
    from ai.pricing.recommendations import get_pricing_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_chips_surge(db_session, g)
    default = _rec(get_pricing_intelligence(db_session, g.rid), "Chips")
    capped = _rec(get_pricing_intelligence(db_session, g.rid, settings=S(max_raise_pct=10)), "Chips")
    assert default["type"] == capped["type"] == "SURGE"
    assert default["price_change_pct"] == 15.0 and capped["price_change_pct"] == 10.0
    assert capped["suggested_price"] < default["suggested_price"]


def test_pricing_offer_size_lift_and_the_food_cost_ceiling_shape_a_stimulate_offer(db_session):
    from ai.pricing.recommendations import get_pricing_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_slow_pilau(db_session, g)
    default = _rec(get_pricing_intelligence(db_session, g.rid), "Pilau")
    assert default["type"] == "STIMULATE" and default["price_change_pct"] == -10.0

    smaller = _rec(get_pricing_intelligence(db_session, g.rid, settings=S(offer_size_pct=5)), "Pilau")
    assert smaller["price_change_pct"] == -5.0 and smaller["suggested_price"] > default["suggested_price"]

    bigger_lift = _rec(get_pricing_intelligence(db_session, g.rid, settings=S(offer_lift_pct=50)), "Pilau")
    assert bigger_lift["monthly_impact_cents"] > default["monthly_impact_cents"]

    # A 15% offer pushes ingredients above the 35% ceiling (11,000 / 29,750 = 37%) so it is not offered ...
    assert _rec(get_pricing_intelligence(db_session, g.rid, settings=S(offer_size_pct=15)), "Pilau") is None
    # ... unless the owner's own ceiling allows it.
    allowed = _rec(get_pricing_intelligence(db_session, g.rid, settings=S(offer_size_pct=15, food_cost_target_pct=45)), "Pilau")
    assert allowed["price_change_pct"] == -15.0


def test_pricing_delivery_gap_uses_the_owners_commission(db_session):
    from ai.pricing.recommendations import get_pricing_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_burger_delivery(db_session, g)
    gaps = lambda data, channel: [d for d in data["delivery_gaps"] if d["channel"] == channel and d["item_name"] == "Burger"]

    default = get_pricing_intelligence(db_session, g.rid)
    assert gaps(default, "glovo")[0]["recommended_delivery_price"] == 80_000
    higher = get_pricing_intelligence(db_session, g.rid, settings=S(commission_glovo_pct=30))
    gap = gaps(higher, "glovo")[0]
    assert gap["commission_pct"] == 30 and gap["effective_delivery_margin"] == 23.3
    assert gap["recommended_delivery_price"] >= 28_000 / 0.30
    assert gaps(default, "bolt_food") and not gaps(get_pricing_intelligence(db_session, g.rid, settings=S(commission_bolt_food_pct=0)), "bolt_food")


def test_pricing_reads_the_saved_settings_when_none_are_passed(db_session):
    from ai.pricing.recommendations import get_pricing_intelligence
    g = _chicken(db_session)
    assert _rec(get_pricing_intelligence(db_session, g.rid), "Quarter chicken")
    update_settings(db_session, g.rid, g.owner.id, {"margin_floor_pct": 30})
    assert _rec(get_pricing_intelligence(db_session, g.rid), "Quarter chicken") is None


# ═════════════════════════════════════════════════════════════════════════════
# menu engineering
# ═════════════════════════════════════════════════════════════════════════════

def test_menu_popular_cutoff_changes_which_dishes_are_popular(db_session):
    from ai.menu_engineer import get_menu_engineering
    g = gr.build_skeleton(db_session)
    gr.seed_menu_mix(db_session, g)
    kind = lambda data, name: next(m["classification"] for m in data["matrix"] if m["name"] == name)

    default = get_menu_engineering(db_session, g.rid)                                  # cut-off 0.7 × 50 = 35 units
    assert kind(default, "Burger") in ("Star", "Plowhorse")                             # 40 units: popular
    strict = get_menu_engineering(db_session, g.rid, settings=S(popular_cutoff=1.0))   # cut-off 50 units
    assert kind(strict, "Burger") in ("Puzzle", "Dog")
    assert sum(strict["summary"][k] for k in ("stars", "plowhorses")) < sum(default["summary"][k] for k in ("stars", "plowhorses"))


def test_menu_score_uses_the_one_food_cost_ceiling_which_is_35_not_40(db_session):
    """D11: profit and pricing used 35, the menu engine used 40. One setting now, default 35."""
    from ai.menu_engineer import get_menu_engineering
    g = gr.build_skeleton(db_session)
    gr.seed_menu_mix(db_session, g)
    for item in g.items.values():                       # a menu averaging 32% food cost: inside the scoring band
        item.cost_price = round(item.price * 0.32)
    db_session.commit()
    score = lambda **kw: get_menu_engineering(db_session, g.rid, **kw)["summary"]["menu_optimization_score"]

    assert score() == score(settings=S(food_cost_target_pct=35))                       # default is 35
    # The old menu-only ceiling of 40 would have scored this very menu higher — that is the conflict D11 recorded.
    assert score(settings=S(food_cost_target_pct=40)) > score(settings=S(food_cost_target_pct=35))
    assert score(settings=S(food_cost_target_pct=30)) < score(settings=S(food_cost_target_pct=35))


# ═════════════════════════════════════════════════════════════════════════════
# cash, stock custody
# ═════════════════════════════════════════════════════════════════════════════

def _drawer(db_session, monkeypatch, settings=None):
    from ai.cash_reconciliation.intelligence import record_drawer_count, compute_reconciliation_report
    emitted = []
    monkeypatch.setattr("events.bus.emit_async", lambda event_type, payload: emitted.append(payload))
    g = gr.build_skeleton(db_session)
    (a_start, a_end, _ae, a_counted), _b = gr.seed_cash_drawers(db_session, g)
    a = record_drawer_count(db_session, g.rid, g.manager.id, a_counted, a_start, a_end, settings=settings)
    report = compute_reconciliation_report(db_session, g.rid, settings=settings)
    flagged = {v.count_id: v.flagged for v in report.drawer_variances}[a.id]
    return g, flagged, emitted


def test_cash_tolerance_amount_changes_the_verdict(db_session, monkeypatch):
    _g, flagged, emitted = _drawer(db_session, monkeypatch)                              # KES 520 short vs KES 350 tolerance
    assert flagged is True and len(emitted) == 1


def test_cash_tolerance_in_shillings_can_forgive_520(db_session, monkeypatch):
    _g, flagged, emitted = _drawer(db_session, monkeypatch, S(cash_tolerance_cents=60_000))   # KES 600
    assert flagged is False and emitted == []


def test_cash_tolerance_percentage_can_forgive_520(db_session, monkeypatch):
    _g, flagged, emitted = _drawer(db_session, monkeypatch, S(cash_tolerance_pct=2.0))        # 2% of 35,000 = KES 700
    assert flagged is False and emitted == []


def test_cash_reads_the_saved_tolerance_when_none_is_passed(db_session, monkeypatch):
    from ai.cash_reconciliation.intelligence import record_drawer_count, compute_reconciliation_report
    emitted = []
    monkeypatch.setattr("events.bus.emit_async", lambda event_type, payload: emitted.append(payload))
    g = gr.build_skeleton(db_session)
    (a_start, a_end, _ae, a_counted), _b = gr.seed_cash_drawers(db_session, g)
    update_settings(db_session, g.rid, g.owner.id, {"cash_tolerance_kes": 600})
    a = record_drawer_count(db_session, g.rid, g.manager.id, a_counted, a_start, a_end)
    assert emitted == []
    assert [v.flagged for v in compute_reconciliation_report(db_session, g.rid).drawer_variances if v.count_id == a.id] == [False]


def test_custody_missing_stock_flag_changes_which_items_are_flagged(db_session):
    from ai.stock_custody import compute_variance_report, flagged_items
    g = gr.build_skeleton(db_session)
    gr.seed_beef_variance(db_session, g)
    window = 24 * 8
    only = lambda **kw: compute_variance_report(db_session, g.rid, hours=window, **kw)[0]
    assert only().flagged is True                                                        # 33.3% > 3%
    assert only(settings=S(missing_stock_flag_pct=10)).flagged is True
    assert only(settings=S(missing_stock_flag_pct=40)).flagged is False                  # 33.3% < 40%
    assert [i.item_name for i in flagged_items(db_session, g.rid, hours=window)] == ["Beef"]
    # Saved row, no argument: a smaller gap (31.5 kg used against 30 expected = 5%) is flagged at the default
    # 3% and forgiven once the owner saves a 10% line. (The settings API caps the line at 10%.)
    for movement in db_session.query(models.StockMovement).filter_by(movement_type=models.StockMovementType.OUT):
        movement.quantity = 7.875
    db_session.commit()
    assert only().flagged is True and only().variance_pct == pytest.approx(0.05)
    update_settings(db_session, g.rid, g.owner.id, {"missing_stock_flag_pct": 10})
    assert only().flagged is False and flagged_items(db_session, g.rid, hours=window) == []


def test_the_variance_report_endpoint_shows_the_owners_threshold(client, db_session):
    import auth
    g = gr.build_skeleton(db_session)
    headers = {"Authorization": f"Bearer {auth.create_access_token({'sub': g.owner.email, 'ver': 0})}"}
    assert client.get("/api/v1/stock/variance-report", headers=headers).json()["threshold"] == 0.03
    client.put("/api/v1/owner/settings", headers=headers, json={"missing_stock_flag_pct": 5})
    assert client.get("/api/v1/stock/variance-report", headers=headers).json()["threshold"] == pytest.approx(0.05)


# ═════════════════════════════════════════════════════════════════════════════
# simulation, labour, decisions
# ═════════════════════════════════════════════════════════════════════════════

def test_simulator_price_sensitivity_and_margin_floor(db_session):
    from ai.simulation.engine import simulate_price_change
    from ai.pricing.analysis import fetch_item_velocities
    g = _chicken(db_session)
    chicken = g.items["Quarter chicken"]
    ratio = fetch_item_velocities(db_session, g.rid)[chicken.id].velocity_ratio

    base = simulate_price_change(db_session, g.rid, chicken.id, 44_000)
    sensitive = simulate_price_change(db_session, g.rid, chicken.id, 44_000, settings=S(price_sensitivity=-1.0))
    assert base["elasticity_used"] == round(-0.7 * (2.0 - max(0.3, min(1.7, ratio))), 2)
    assert sensitive["elasticity_used"] == round(-1.0 * (2.0 - max(0.3, min(1.7, ratio))), 2)
    assert sensitive["deltas"]["sales_pct"] < base["deltas"]["sales_pct"] < 0            # guests who react more, buy less

    cut = simulate_price_change(db_session, g.rid, chicken.id, 34_000)                  # margin 23.5% — under the 40% floor, and falling
    assert cut["verdict"] == "NO" and "40%" in cut["verdict_reason"]
    lenient = simulate_price_change(db_session, g.rid, chicken.id, 34_000, settings=S(margin_floor_pct=20))
    assert "healthy floor" not in lenient["verdict_reason"]


def test_overtime_starts_when_the_owner_says(db_session):
    from ai.labor.intelligence import get_labor_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_overtime_shift(db_session, g, hours=8.5)
    default = get_labor_intelligence(db_session, g.rid)["summary"]
    assert default["shifts_logged"] == 1 and default["overtime_hours_30d"] == 0.5          # 8.5 h against 8 h
    nine = get_labor_intelligence(db_session, g.rid, settings=S(overtime_after_hours=9))["summary"]
    assert nine["overtime_hours_30d"] == 0.0
    seven = get_labor_intelligence(db_session, g.rid, settings=S(overtime_after_hours=7))["summary"]
    assert seven["overtime_hours_30d"] == 1.5
    update_settings(db_session, g.rid, g.owner.id, {"overtime_after_hours": 9})
    assert get_labor_intelligence(db_session, g.rid)["summary"]["overtime_hours_30d"] == 0.0


def test_labour_status_flips_when_the_wage_target_drops_below_actual(db_session):
    from ai.labor.intelligence import get_labor_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_pnl_week(db_session, g)                                                      # wages are 25% of sales
    assert get_labor_intelligence(db_session, g.rid)["summary"]["labor_status"] == "HEALTHY"
    assert get_labor_intelligence(db_session, g.rid, settings=S(labour_target_pct=20))["summary"]["labor_status"] == "HIGH"
    update_settings(db_session, g.rid, g.owner.id, {"labour_target_pct": 20})
    assert get_labor_intelligence(db_session, g.rid)["summary"]["labor_status"] == "HIGH"


def test_decisions_are_built_from_the_owners_settings(db_session):
    from ai.decisions import get_ranked_decisions
    g = _chicken(db_session)
    actions = lambda data: [d["action"] for d in data["decisions"]]
    assert any("Quarter chicken" in a for a in actions(get_ranked_decisions(db_session, g.rid)))
    relaxed = get_ranked_decisions(db_session, g.rid, settings=S(margin_floor_pct=30))
    assert not any("Quarter chicken" in a and a.startswith("Reprice") for a in actions(relaxed))
    update_settings(db_session, g.rid, g.owner.id, {"margin_floor_pct": 30})
    assert not any(a.startswith("Reprice") for a in actions(get_ranked_decisions(db_session, g.rid)))


# ═════════════════════════════════════════════════════════════════════════════
# the service itself
# ═════════════════════════════════════════════════════════════════════════════

def test_get_settings_fails_safe_to_defaults_when_the_table_is_missing(db_session):
    """Deploy-order safety: code can run before migration 051. A missing table must never take every engine down."""
    g = gr.build_skeleton(db_session)
    db_session.commit()                                                                  # release the write lock first
    models.RestaurantSettings.__table__.drop(db_session.get_bind())
    assert get_settings(db_session, g.rid) == DEFAULTS
    assert db_session.query(models.MenuItem).count() == 8                                # the session is still usable afterwards


def test_no_module_level_business_constants_remain_for_settings_owned_rules():
    """D11: the numbers live in owner/settings.py only. Importing the old names must now fail loudly."""
    import importlib
    gone = {
        "ai.profit.intelligence": ["HEALTHY_FOOD_COST_MAX", "HEALTHY_MARGIN_MIN", "CRITICAL_MARGIN_FLOOR", "DELIVERY_COMMISSIONS"],
        "ai.pricing.analysis": ["MIN_MARGIN_PCT", "MAX_FOOD_COST_PCT", "DELIVERY_COMMISSIONS"],
        "ai.menu_engineer": ["POPULARITY_INDEX", "FOOD_COST_CEILING_PCT"],
        "ai.cash_reconciliation.intelligence": ["DRAWER_TOLERANCE_CENTS", "DRAWER_TOLERANCE_PCT"],
        "ai.stock_custody": ["VARIANCE_THRESHOLD"],
        "ai.simulation.engine": ["BASE_ELASTICITY"],
        "ai.labor.intelligence": ["HEALTHY_LABOR_PCT_MAX", "OVERTIME_HOURS_DAILY"],
    }
    for module, names in gone.items():
        mod = importlib.import_module(module)
        for name in names:
            assert not hasattr(mod, name), f"{module}.{name} should now come from owner.settings"
