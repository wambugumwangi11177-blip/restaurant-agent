"""
backend/owner/areas.py — the six areas of Home (docs/v2/SPEC.md §3.1), each composed from existing engines.

  money · sales_dishes · store · cash · staff · permits

`compose_area(ctx, key)` is the ONE place an area is built: Home embeds the result as a collapsed one-line
panel (`summary`), and `/owner/area/{key}` returns exactly the same block, so Home and the deep link can
never disagree. Composition, not rewriting: every figure is an engine's output reshaped — cents become KES
here, system words become owner words (§3.4) — and every block says what state it is in (owner/states.py).

Sections whose engine does not exist yet (P&L, bills, licences, break-even, M-Pesa match) are honest
`unavailable` blocks with a plain reason, never a made-up number.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Callable

from sqlalchemy import func

import models
from owner import states
from time_utils import EAT_OFFSET, eat_date
from owner.states import OwnerContext, assume, block, kes, no_data, unavailable

AREAS = ("money", "sales_dishes", "store", "cash", "staff", "permits")

AREA_TITLES = {
    "money": "My Money", "sales_dishes": "Sales & Dishes", "store": "Store & Suppliers",
    "cash": "Cash Check", "staff": "Staff", "permits": "Permits & Settings",
}

# §3.4 owner vocabulary
QUADRANT_WORDS = {"Star": "Best dish", "Plowhorse": "Popular, earns little", "Puzzle": "Earns well, few order it",
                  "Dog": "Consider removing"}
CHANNEL_WORDS = {"walk_in": "Dine-in & takeaway", "app": "LEVIII app", "glovo": "Glovo", "uber_eats": "Uber Eats",
                 "bolt_food": "Bolt Food"}

_STATUS_WORD = {"good": "Fine", "watch": "Watch", "bad": "High", "unknown": "Not set up"}


def summary(number, word: str, status: str, *, unit: str = "", label: str = "") -> dict:
    """The collapsed one-liner of an area: one number, one word, one colour (status)."""
    return {"number": number, "unit": unit, "word": word, "status": status, "label": label}


# ── shared engine runs (memoised per request) ────────────────────────────────

def _profit(ctx: OwnerContext) -> dict:
    from ai.profit.intelligence import get_profit_intelligence
    return ctx.cached("profit", lambda: get_profit_intelligence(ctx.db, ctx.rid, ctx.settings))


def _pricing(ctx: OwnerContext) -> dict:
    from ai.pricing.recommendations import get_pricing_intelligence
    return ctx.cached("pricing", lambda: get_pricing_intelligence(ctx.db, ctx.rid, ctx.settings))


def _labor(ctx: OwnerContext) -> dict:
    from ai.labor.intelligence import get_labor_intelligence
    return ctx.cached("labor", lambda: get_labor_intelligence(ctx.db, ctx.rid, ctx.settings))


def _menu(ctx: OwnerContext) -> dict:
    from ai.menu_engineer import get_menu_engineering
    return ctx.cached("menu", lambda: get_menu_engineering(ctx.db, ctx.rid, ctx.settings))


def _supply(ctx: OwnerContext) -> dict:
    from ai.supply_chain.intelligence import get_supply_chain_intelligence
    return ctx.cached("supply", lambda: get_supply_chain_intelligence(ctx.db, ctx.rid))


def _overview_core(ctx: OwnerContext):
    from routers import overview
    return overview


# ═════════════════════════════════════════════════════════════════════════════
# My Money
# ═════════════════════════════════════════════════════════════════════════════

def _money_cost_dials(ctx: OwnerContext) -> dict:
    s = ctx.settings
    base = ctx.order_state(needs_days=14)
    if base["state"] == "no_data":
        return base
    profit, labor = _profit(ctx)["summary"], _labor(ctx)["summary"]
    food = profit.get("food_cost_pct") or 0.0
    wages = labor.get("labor_pct") if labor.get("labor_status") != "NO_DATA" else None
    return {**base,
            "food_cost_pct": food, "food_cost_target_pct": s.food_cost_target_pct,
            "food_cost_word": {"HEALTHY": "Fine", "WARNING": "Watch", "CRITICAL": "High"}.get(profit.get("food_cost_status"), "Not set up"),
            "wages_pct": wages, "wages_target_pct": s.labour_target_pct,
            "wages_word": None if wages is None else ("Fine" if wages <= s.labour_target_pct else "High"),
            "assumptions": [assume("food_cost_target_pct", s.food_cost_target_pct, label="Ingredient cost target"),
                            assume("labour_target_pct", s.labour_target_pct, label="Wages target")],
            "assumption": assume("food_cost_target_pct", s.food_cost_target_pct, label="Ingredient cost target")}


def month_pnl(ctx: OwnerContext, month_start=None) -> dict:
    """The Profit & Loss for the calendar month so far — Home's money.pnl block and the monthly report's P&L section — or, with
    `month_start` (the first day of a month), for that whole month (the monthly report's `month` and the accountant export)."""
    from owner.money.pnl import compute_pnl, period_range
    from owner.money.view import owner_pnl
    from time_utils import eat_date
    today = eat_date(ctx.now)
    start, end = period_range("month", month_start or today)
    p = compute_pnl(ctx.db, ctx.rid, start, end, ctx.settings, today=today)
    return owner_pnl(p, "month", ctx.settings, as_of=ctx.now, sales_state=ctx.order_state()["state"])


def _hhmm(utc_naive) -> str:
    """A naive-UTC timestamp as Nairobi wall-clock "3:40 pm"."""
    local = utc_naive + EAT_OFFSET
    return f"{local.hour % 12 or 12}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"


def breakeven_summary(ctx: OwnerContext) -> dict:
    """"Costs covered": today's break-even sales and where today's sales are against it (Home's pulse chip and money.breakeven)."""
    from owner.money.breakeven import break_even, todays_progress
    today = eat_date(ctx.now)
    be = ctx.cached("break_even", lambda: break_even(ctx.db, ctx.rid, today, ctx.settings))
    if be is None:
        return no_data("Costs covered needs your costs and some sales: enter your costs to see when today's sales cover them.")
    progress = todays_progress(ctx.db, ctx.rid, be["break_even_cents"], today)
    base = ctx.order_state()
    basis = be["basis"]
    return {**(base if base["state"] != "no_data" else block("live", as_of=ctx.now)),
            "break_even_kes": kes(be["break_even_cents"]), "sales_today_kes": kes(progress["sales_so_far_cents"]),
            "to_go_kes": kes(progress["to_go_cents"]), "covered": progress["crossed_at"] is not None,
            "crossed_at": _hhmm(progress["crossed_at"]) if progress["crossed_at"] else None,
            "fixed_per_day_kes": kes(be["fixed_per_day_cents"]), "food_cost_pct": be["food_cost_pct"],
            "built_from": {"label": basis["label"], "period": basis["kind"], "days": basis["days"], "fixed_costs_kes": kes(basis["fixed_costs_cents"]),
                           "wages_kes": kes(basis["labour_fixed_cents"]), "lines": [{"name": l["name"], "kes": kes(l["amount_cents"])} for l in basis["fixed_lines"]]},
            "note": "Gas, packaging and other costs that move with sales are not counted, so the real figure is a little higher.",
            "assumption": assume("food_cost_target_pct", ctx.settings.food_cost_target_pct, label="Ingredient cost target")}


def _bill_radar(ctx: OwnerContext) -> dict:
    from owner.money.radar import bill_radar
    return ctx.cached("bill_radar", lambda: bill_radar(ctx.db, ctx.rid, eat_date(ctx.now), ctx.settings))


def bills_block(ctx: OwnerContext) -> dict:
    """The bill radar: forecast sales left after ingredients and wages, minus bills falling due, for 30 days (figure R4)."""
    r = _bill_radar(ctx)
    if not r["available"]:
        if r["reason"] == "no_bills":
            return no_data("No bills entered yet.")
        return no_data("Needs about two weeks of sales before we can forecast whether they will cover your bills.")
    s = ctx.settings
    return block("as_entered", as_of=ctx.now,
                 upcoming=[{"name": u["name"], "due_on": u["due_on"], "days_away": u["days_away"], "amount_kes": kes(u["amount_cents"]),
                            "short": u["balance_after_cents"] < 0} for u in r["upcoming"]],
                 shortfalls=[{"date": x["date"], "short_by_kes": kes(x["short_by_cents"]), "bills": x["bills"], "bills_kes": kes(x["bills_cents"])} for x in r["shortfalls"]],
                 lowest={"date": r["lowest"]["date"], "balance_kes": kes(r["lowest"]["balance_cents"])},
                 days=[{"date": d["date"], "expected_sales_kes": kes(d["expected_sales_cents"]), "left_kes": kes(d["left_after_costs_cents"]),
                        "bills_kes": kes(d["bills_cents"]), "balance_kes": kes(d["balance_cents"])} for d in r["days"]],
                 opening_kes=kes(r["opening_cents"]),
                 notes=["Sales are counted after ingredients and wages, starting from the cash you keep aside for bills."]
                       + (["Ingredient cost is your target, because there is no month of sales to measure it from yet."] if r["food_cost_assumed"] else []),
                 assumption=assume("bill_reserve_kes", s.bill_reserve_cents // 100, label="Cash you keep aside for bills"))


def spikes_block(ctx: OwnerContext) -> dict:
    """Costs going up: a cost line already this far above its three-month usual (owner/money/spikes.py)."""
    from owner.money.spikes import LEARNING_DAYS, expense_spikes
    out = expense_spikes(ctx.db, ctx.rid, eat_date(ctx.now), ctx.settings)
    s = ctx.settings
    rule = assume("expense_spike_pct", s.expense_spike_pct, label="Cost increase we flag")
    if out["history_days"] is None:
        return no_data("Needs three months of entered costs.")
    if out["history_days"] < LEARNING_DAYS and not out["spikes"]:
        return block("learning", as_of=ctx.now, day=out["history_days"], of=LEARNING_DAYS, reason="Needs three months of entered costs to know what is usual.", assumption=rule)
    return block("as_entered", as_of=ctx.now,
                 spikes=[{"name": x["name"], "this_month_kes": kes(x["this_month_cents"]), "usual_kes": kes(x["usual_cents"]), "up_pct": x["pct"],
                          "extra_kes": kes(x["extra_cents"])} for x in out["spikes"]],
                 reason=None if out["spikes"] else "Nothing is costing more than usual.", assumption=rule)


def _licences(ctx: OwnerContext) -> list[dict]:
    from owner.money.licences import licence_status
    today, warn = eat_date(ctx.now), ctx.settings.licence_warning_days
    rows = ctx.db.query(models.Licence).filter(models.Licence.restaurant_id == ctx.rid, models.Licence.is_active.is_(True)).order_by(models.Licence.expires_on).all()
    out = []
    for l in rows:
        days_left, status = licence_status(l.expires_on, today, warn)
        out.append({"name": l.name, "issuer": l.issuer, "expires_on": l.expires_on.isoformat(), "days_left": days_left, "status": status,
                    "word": {"expired": "Expired", "expiring": "Expires soon", "ok": "Fine"}[status]})
    return out


def licences_block(ctx: OwnerContext) -> dict:
    items = _licences(ctx)
    if not items:
        return no_data("No licences entered yet.")
    return block("as_entered", as_of=ctx.now, items=items, assumption=assume("licence_warning_days", ctx.settings.licence_warning_days, label="Licence warning (days)"))


def licences_due_block(ctx: OwnerContext) -> dict:
    """Licences to renew soon (Home's coming-up list): expired or inside the owner's warning window."""
    items = [i for i in _licences(ctx) if i["status"] != "ok"]
    entered = ctx.db.query(models.Licence.id).filter(models.Licence.restaurant_id == ctx.rid, models.Licence.is_active.is_(True)).first()
    if entered is None:
        return no_data("No licences entered yet.")
    return block("as_entered", as_of=ctx.now, items=items, reason=None if items else f"Nothing expires in the next {ctx.settings.licence_warning_days} days.",
                 assumption=assume("licence_warning_days", ctx.settings.licence_warning_days, label="Licence warning (days)"))


def bills_due_block(ctx: OwnerContext, days: int = 14) -> dict:
    """Bills falling due in the next two weeks (Home's coming-up list)."""
    r = _bill_radar(ctx)
    if not r["available"]:
        return no_data("No bills entered yet." if r["reason"] == "no_bills" else "Bills are entered; the forecast needs about two weeks of sales.")
    items = [u for u in r["upcoming"] if u["days_away"] < days]
    return block("as_entered", as_of=ctx.now, reason=None if items else f"No bills fall due in the next {days} days.",
                 items=[{"name": u["name"], "due_on": u["due_on"], "days_away": u["days_away"], "amount_kes": kes(u["amount_cents"]), "short": u["balance_after_cents"] < 0}
                        for u in items])


def _money_savings(ctx: OwnerContext) -> dict:
    from ai.roi.savings import get_roi_savings
    roi = ctx.cached("roi", lambda: get_roi_savings(ctx.db, ctx.rid))
    captured = roi.get("money_captured", {}).get("monthly_impact_cents", 0)
    saved = roi.get("time_saved", {})
    return block("live" if (captured or saved.get("hours_saved_30d")) else "no_data",
                 as_of=ctx.now, captured_kes_month=kes(captured), hours_saved_30d=saved.get("hours_saved_30d", 0.0),
                 approved_ideas=roi.get("money_captured", {}).get("recommendations_approved", 0),
                 reason=None if (captured or saved.get("hours_saved_30d")) else "Nothing approved yet.")


def money_area(ctx: OwnerContext) -> tuple[dict, dict]:
    dials = ctx.safe("money.cost_dials", lambda: _money_cost_dials(ctx))
    blocks = {
        "pnl": ctx.safe("money.pnl", lambda: month_pnl(ctx)),
        "cost_dials": dials,
        "breakeven": ctx.safe("money.breakeven", lambda: breakeven_summary(ctx)),
        "bills": ctx.safe("money.bills", lambda: bills_block(ctx)),
        "spikes": ctx.safe("money.spikes", lambda: spikes_block(ctx)),
        "savings": ctx.safe("money.savings", lambda: _money_savings(ctx)),
    }
    if dials["state"] in ("live", "stale", "learning"):
        word = dials["food_cost_word"]
        status = {"Fine": "good", "Watch": "watch", "High": "bad"}.get(word, "unknown")
        head = summary(dials["food_cost_pct"], word, status, unit="%", label="Out of every KES 100, ingredients")
    else:
        head = summary(None, _STATUS_WORD["unknown"], "unknown", label="Out of every KES 100, ingredients")
    return head, blocks


# ═════════════════════════════════════════════════════════════════════════════
# Sales & Dishes
# ═════════════════════════════════════════════════════════════════════════════

def _seven_day(ctx: OwnerContext) -> dict:
    overview = _overview_core(ctx)
    trend = overview._performance(ctx.db, ctx.rid)["revenue_trend"]
    total = sum(d["revenue"] for d in trend)
    return {**ctx.order_state(), "days": [{"date": d["date"], "sales": d["revenue"], "orders": d["orders"]} for d in trend],
            "total": round(total, 2)}


def _forecast(ctx: OwnerContext) -> dict:
    from ai.revenue_forecaster import get_revenue_forecast
    data = ctx.cached("forecast", lambda: get_revenue_forecast(ctx.db, ctx.rid))
    base = ctx.order_state(needs_days=14)
    if base["state"] in ("no_data", "learning") or not data.get("forecast"):
        return base if base["state"] != "live" else no_data("Not enough sales to forecast yet.")
    actual = data.get("daily_revenue", [])[-14:]
    return {**base,
            "actual": [{"date": d["date"], "sales": kes(d["revenue"])} for d in actual],
            "next_7_days": [{"date": f["date"], "day": f["day"], "usual": kes(f["predicted_revenue"]),
                             "low": kes(f["confidence_low"]), "high": kes(f["confidence_high"])} for f in data["forecast"][:7]],
            "unusual_days": [{"date": a["date"], "sales": kes(a["revenue"]), "expected": kes(a["expected"]),
                              "off_by_pct": a["deviation_pct"]} for a in data.get("anomalies", [])[-3:]],
            "note": "A range, not a promise."}


def _matrix(ctx: OwnerContext) -> dict:
    menu = _menu(ctx)
    base = ctx.order_state(needs_days=14)
    rows = menu.get("matrix", [])
    if not rows:
        return no_data("No dishes sold yet.")
    summary = menu.get("summary", {})
    return {**base,
            # The engine's own two lines: popular from this many orders, earns well from this much a plate (KES).
            "popular_line_units": summary.get("popularity_cutoff_units"),
            "earns_line": kes(summary["avg_margin_cents"]) if summary.get("avg_margin_cents") is not None else None,
            "dishes": [{"name": m["name"], "kind": QUADRANT_WORDS.get(m["classification"], m["classification"]),
                        "sold": m["qty_sold"], "keeps_pct": m["margin_pct"], "earns_per_plate": kes(m["margin"]),
                        "profit": kes(m["contribution"]), "trend": m["trend"]} for m in rows[:40]],
            "assumption": assume("popular_cutoff", ctx.settings.popular_cutoff, label="Counts as popular")}


def _dishes_by_kes(ctx: OwnerContext) -> dict:
    cms = _profit(ctx).get("contribution_margins", [])
    if not cms:
        return no_data("No dishes sold yet.")
    top = sorted(cms, key=lambda c: c["total_profit_30d"], reverse=True)[:8]
    return {**ctx.order_state(),
            "dishes": [{"name": c["item_name"], "profit": kes(c["total_profit_30d"]), "sold": c["qty_30d"],
                        "keeps_pct": c["margin_pct"]} for c in top]}


def _price_ideas(ctx: OwnerContext) -> dict:
    s = ctx.settings
    recs = _pricing(ctx).get("recommendations", [])
    leaks = _profit(ctx).get("profit_leaks", [])
    base = ctx.order_state(needs_days=14)
    if base["state"] == "no_data":
        return base
    return {**base,
            "ideas": [{"id": r.get("item_id"), "dish": r["item_name"], "kind": {"REPRICE": "Priced too low", "SURGE": "Selling hot", "STIMULATE": "Selling slowly"}.get(r["type"], r["type"]),
                       "from": kes(r["current_price"]), "to": kes(r["suggested_price"]), "month_gain": kes(r["monthly_impact_cents"]),
                       "why": r["reason"]} for r in recs[:5]],
            "priced_too_low": [{"dish": l["item_name"], "keeps_pct": l["current_margin_pct"], "month_gain": kes(l["monthly_leak_cents"])}
                               for l in leaks[:5]],
            "assumptions": [assume("margin_floor_pct", s.margin_floor_pct, label="Lowest share you keep"),
                            assume("price_step_kes", s.price_step_cents // 100, label="Price rounding step")],
            "assumption": assume("margin_floor_pct", s.margin_floor_pct, label="Lowest share you keep")}


def _delivery_and_dayparts(ctx: OwnerContext) -> dict:
    s = ctx.settings
    profit, pricing = _profit(ctx), _pricing(ctx)
    channels = profit.get("channel_analysis", [])
    if not channels:
        return no_data("No sales recorded yet.")
    return {**ctx.order_state(),
            "channels": [{"channel": CHANNEL_WORDS.get(c["channel"], c["channel"]), "orders": c["orders"],
                          "keeps": kes(c["profit"]), "keeps_pct": c["margin_pct"], "pays_commission": c["commission_included"]}
                         for c in channels],
            "delivery_gaps": [{"channel": CHANNEL_WORDS.get(g["channel"], g["channel"]), "dish": g["item_name"],
                               "commission_pct": g["commission_pct"], "keeps_pct": g["effective_delivery_margin"],
                               "keeps": kes(g["delivery_keeps_cents"]), "keeps_dine_in": kes(g["dine_in_keeps_cents"]),
                               "price_to_keep_floor": kes(g["recommended_delivery_price"])} for g in pricing.get("delivery_gaps", [])[:10]],
            "best_and_weakest_hours": [{"hours": d["daypart"].replace("_", " "), "keeps_pct": d["margin_pct"], "orders": d["orders"]}
                                       for d in profit.get("daypart_analysis", [])],
            "assumption": assume("commission_glovo_pct", s.commission_glovo_pct, label="Delivery commission"),
            "assumptions": [assume("commission_uber_eats_pct", s.commission_uber_eats_pct, label="Uber Eats commission"),
                            assume("commission_glovo_pct", s.commission_glovo_pct, label="Glovo commission"),
                            assume("commission_bolt_food_pct", s.commission_bolt_food_pct, label="Bolt Food commission")]}


def _outlook(ctx: OwnerContext) -> dict:
    from ai.simulation.twin import forecast_twin
    twin = ctx.cached("twin", lambda: forecast_twin(ctx.db, ctx.rid, 30))
    base = ctx.order_state(needs_days=14)
    if not twin.get("available") or base["state"] in ("no_data", "learning"):
        return base if base["state"] != "live" else no_data("Not enough history for a 30-day outlook.")
    t = twin["summary"]
    return {**base, "next_30_days": kes(t["projected_revenue_cents"]), "low": kes(t["low_cents"]), "high": kes(t["high_cents"]),
            "confidence_pct": t["confidence_pct"], "note": "A range based on your own sales history and the calendar, not a promise."}


def _win_back(ctx: OwnerContext) -> dict:
    from ai.marketing import get_marketing_insights
    m = ctx.cached("marketing", lambda: get_marketing_insights(ctx.db, ctx.rid))
    w = m.get("winback", {})
    return block("live" if w.get("count") else "no_data", as_of=ctx.now, lapsed_guests=w.get("count", 0), reachable=w.get("reachable", 0),
                 offers=len(m.get("suggested_offers", [])), reason=None if w.get("count") else "No lapsed regulars to win back.")


def sales_dishes_area(ctx: OwnerContext) -> tuple[dict, dict]:
    seven = ctx.safe("sales.seven_day", lambda: _seven_day(ctx))
    blocks = {
        "seven_day": seven,
        "forecast": ctx.safe("sales.forecast", lambda: _forecast(ctx)),
        "matrix": ctx.safe("sales.matrix", lambda: _matrix(ctx)),
        "dishes_by_kes": ctx.safe("sales.dishes_by_kes", lambda: _dishes_by_kes(ctx)),
        "price_ideas": ctx.safe("sales.price_ideas", lambda: _price_ideas(ctx)),
        "delivery": ctx.safe("sales.delivery", lambda: _delivery_and_dayparts(ctx)),
        "outlook": ctx.safe("sales.outlook", lambda: _outlook(ctx)),
        "win_back": ctx.safe("sales.win_back", lambda: _win_back(ctx)),
        "simulator": block("live", as_of=ctx.now, info=True, how="Ask “what if I raise the price of <dish>?” in Ask LEVIII."),
    }
    if seven["state"] in ("live", "stale", "learning"):
        days = seven["days"]
        last, prev = sum(d["sales"] for d in days[-3:]), sum(d["sales"] for d in days[:3])
        word, status = ("Steady", "good") if not prev else (("Up", "good") if last > prev * 1.05 else ("Down", "watch") if last < prev * 0.95 else ("Steady", "good"))
        head = summary(seven["total"], word, status, unit="KES", label="Sales, last 7 days")
    else:
        head = summary(None, _STATUS_WORD["unknown"], "unknown", label="Sales, last 7 days")
    return head, blocks


# ═════════════════════════════════════════════════════════════════════════════
# Store & Suppliers
# ═════════════════════════════════════════════════════════════════════════════

def _missing_stock(ctx: OwnerContext) -> dict:
    from ai.stock_custody import compute_variance_report
    rows = compute_variance_report(ctx.db, ctx.rid, hours=24 * 7, settings=ctx.settings)
    latest = ctx.db.query(models.StockMovement.created_at).join(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == ctx.rid).order_by(models.StockMovement.created_at.desc()).first()
    base = ctx.entered_state(latest[0] if latest else None, empty="No stock movements recorded yet.")
    if base["state"] == "no_data":
        return base
    costs = {i.id: i.cost_per_unit_cents or 0 for i in ctx.db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == ctx.rid)}
    items = []
    for r in rows:
        if r.variance_pct is None:
            continue
        gap = r.actual_usage - r.theoretical_usage
        items.append({"item": r.item_name, "unit": r.unit, "expected": round(r.theoretical_usage, 2), "used": round(r.actual_usage, 2),
                      "missing": round(max(gap, 0), 2), "missing_value": kes(max(gap, 0) * costs.get(r.inventory_item_id, 0)),
                      "off_by_pct": round(r.variance_pct * 100, 1), "check": bool(r.flagged)})
    items.sort(key=lambda i: (i["check"], i["missing_value"] or 0), reverse=True)
    return {**base, "window_days": 7, "items": items,
            "assumption": assume("missing_stock_flag_pct", ctx.settings.missing_stock_flag_pct, label="Missing stock we flag")}


def _handovers(ctx: OwnerContext) -> dict:
    rows = ctx.db.query(models.StockTransfer).filter(
        models.StockTransfer.restaurant_id == ctx.rid, models.StockTransfer.status == models.StockTransferStatus.DISPUTED,
        models.StockTransfer.confirmed_at >= ctx.now - timedelta(days=30)).order_by(models.StockTransfer.confirmed_at.desc()).limit(10).all()
    latest = ctx.db.query(models.StockTransfer.initiated_at).filter(models.StockTransfer.restaurant_id == ctx.rid).order_by(
        models.StockTransfer.initiated_at.desc()).first()
    base = ctx.entered_state(latest[0] if latest else None, empty="No store-to-kitchen handovers recorded yet.")
    if base["state"] == "no_data":
        return base
    return {**base, "doesnt_match": [{"item": r.inventory_item.item_name if r.inventory_item else "", "unit": r.unit, "store_said": r.quantity,
                                      "kitchen_counted": r.confirmed_quantity, "gap": round((r.quantity or 0) - (r.confirmed_quantity or 0), 2)} for r in rows]}


def _reorder(ctx: OwnerContext) -> dict:
    from ai.inventory_predictor import get_inventory_predictions
    from ai.reorder import find_reorder_candidates
    preds = ctx.cached("inventory", lambda: get_inventory_predictions(ctx.db, ctx.rid))
    items = [p for p in preds.get("predictions", []) if p.get("status") in ("critical", "low", "reorder")]
    if not preds.get("predictions"):
        return no_data("No stock items recorded yet.")
    drafts = find_reorder_candidates(ctx.db, ctx.rid)
    latest = ctx.db.query(models.StockMovement.created_at).join(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == ctx.rid).order_by(models.StockMovement.created_at.desc()).first()
    return {**ctx.entered_state(latest[0] if latest else None, empty="Stock levels recorded, no movements yet."),
            "tracked": len(preds["predictions"]),
            "least_cover": [{"item": p["name"], "unit": p["unit"], "left": p["current_stock"], "days_left": p.get("days_until_depletion")}
                            for p in sorted((p for p in preds["predictions"] if p.get("days_until_depletion") is not None),
                                            key=lambda p: p["days_until_depletion"])[:5]],
            "time_to_reorder": [{"item": p["name"], "unit": p["unit"], "left": p["current_stock"], "status": p["status"],
                                 "days_left": p.get("days_until_depletion")} for p in items[:10]],
            "drafts": [{"item": c.item_name, "unit": c.unit, "order": c.adjusted_quantity, "supplier": c.supplier_name} for c in drafts[:10]]}


def _suppliers(ctx: OwnerContext) -> dict:
    data = _supply(ctx)
    if not data.get("suppliers"):
        return no_data("No suppliers added yet.")
    latest = ctx.db.query(models.PurchaseOrder.ordered_at).filter(models.PurchaseOrder.restaurant_id == ctx.rid).order_by(
        models.PurchaseOrder.ordered_at.desc()).first()
    return {**ctx.entered_state(latest[0] if latest else None, empty="Suppliers added, no orders yet."),
            "suppliers": [{"name": s["name"], "on_time_pct": s["reliability_score"], "closed_orders": s["closed_orders"],
                           "word": {"LEARNING": "Learning", "EXCELLENT": "Reliable", "GOOD": "Good", "POOR": "Late too often"}.get(s["reliability_label"], "")}
                          for s in data["suppliers"]],
            "overdue_orders": data["summary"]["overdue_orders"],
            "short_deliveries": [{"supplier": d["supplier"], "item": d["item"], "unit": d["unit"], "ordered": d["ordered"], "received": d["received"],
                                  "short_by": d["short_by"], "short_value": kes(d["short_value_cents"]), "on": d["delivered_at"][:10]}
                                 for d in data.get("short_deliveries", [])]}


def store_area(ctx: OwnerContext) -> tuple[dict, dict]:
    missing = ctx.safe("store.missing", lambda: _missing_stock(ctx))
    reorder = ctx.safe("store.reorder", lambda: _reorder(ctx))
    blocks = {"missing": missing, "handover": ctx.safe("store.handover", lambda: _handovers(ctx)), "reorder": reorder,
              "suppliers": ctx.safe("store.suppliers", lambda: _suppliers(ctx))}
    checks = sum(1 for i in missing.get("items", []) if i["check"]) if missing["state"] in ("as_entered", "stale", "live") else None
    due = len(reorder.get("time_to_reorder", [])) if reorder["state"] not in ("no_data", "unavailable") else None
    if checks:
        head = summary(checks, "Missing stock to check", "bad", label="Items to check")
    elif due:
        head = summary(due, "Time to reorder", "watch", label="Items to reorder")
    elif checks is None and due is None:
        head = summary(None, _STATUS_WORD["unknown"], "unknown", label="Items to check")
    else:
        head = summary(0, "All fine", "good", label="Items to check")
    return head, blocks


# ═════════════════════════════════════════════════════════════════════════════
# Cash Check
# ═════════════════════════════════════════════════════════════════════════════

def _shifts(ctx: OwnerContext) -> dict:
    from ai.cash_reconciliation.intelligence import drawer_tolerance_cents
    rows = ctx.db.query(models.CashDrawerCount).filter(
        models.CashDrawerCount.restaurant_id == ctx.rid,
        models.CashDrawerCount.window_start >= ctx.now - timedelta(days=14)).order_by(models.CashDrawerCount.window_start.desc()).all()
    latest = ctx.db.query(models.CashDrawerCount.counted_at).filter(models.CashDrawerCount.restaurant_id == ctx.rid).order_by(
        models.CashDrawerCount.counted_at.desc()).first()
    base = ctx.entered_state(latest[0] if latest else None, empty="No cash counts entered yet.")
    if base["state"] == "no_data":
        return base
    s = ctx.settings
    return {**base, "shifts": [{"from": r.window_start.isoformat(), "expected": kes(r.expected_amount_cents), "counted": kes(r.counted_amount_cents),
                                "gap": kes(r.counted_amount_cents - r.expected_amount_cents),
                                "check": abs(r.counted_amount_cents - r.expected_amount_cents) > drawer_tolerance_cents(r.expected_amount_cents, s)}
                               for r in rows],
            "assumptions": [assume("cash_tolerance_kes", s.cash_tolerance_cents // 100, label="Cash count difference we accept"),
                            assume("cash_tolerance_pct", s.cash_tolerance_pct, label="…or this share of takings")],
            "assumption": assume("cash_tolerance_kes", s.cash_tolerance_cents // 100, label="Cash count difference we accept")}


def _cancelled_sales(ctx: OwnerContext) -> dict:
    from ai.fraud.detection import compute_fraud_report
    base = ctx.order_state()
    if base["state"] == "no_data":
        return base
    report = ctx.cached("fraud", lambda: compute_fraud_report(ctx.db, ctx.rid))
    cancelled = ctx.db.query(models.Order.id).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.status == models.OrderStatus.CANCELLED,
        models.Order.created_at >= ctx.now - timedelta(days=7)).count()
    return {**base, "cancelled_last_7_days": cancelled, "unusual_cancelling": len(report.void_spikes), "unusual_refunds": len(report.refund_velocity),
            "late_night_activity": len(report.off_hours), "to_check": len(report.void_spikes) + len(report.refund_velocity) + len(report.off_hours),
            "note": "These are things to check, not conclusions about anyone."}


def _below_menu_price(ctx: OwnerContext) -> dict:
    gaps = _profit(ctx).get("till_price_gap", [])
    base = ctx.order_state(needs_days=14)
    if base["state"] == "no_data":
        return base
    return {**base, "dishes": [{"dish": g["item_name"], "menu_price": kes(g["menu_price"]), "charged": kes(g["avg_captured_price"]),
                                "below_pct": g["drift_pct"], "month_loss": kes(g["estimated_monthly_leak"])} for g in gaps[:5]]}


PATTERN_DAYS = 28


def _patterns(ctx: OwnerContext) -> dict:
    """The same weekday and shift short, again and again (ai.cash_reconciliation.recurring_drawer_gaps). It needs four
    weeks of counts before it can say anything, so until then it says how far along it is."""
    from ai.cash_reconciliation.intelligence import recurring_drawer_gaps
    first = ctx.db.query(func.min(models.CashDrawerCount.counted_at)).filter(models.CashDrawerCount.restaurant_id == ctx.rid).scalar()
    if first is None:
        return no_data("Needs four weeks of cash counts to spot a repeating pattern.")
    day = (ctx.now - first).days + 1
    if day < PATTERN_DAYS:
        return block("learning", as_of=ctx.now, day=day, of=PATTERN_DAYS, reason="Needs four weeks of cash counts to spot a repeating pattern.")
    found = recurring_drawer_gaps(ctx.db, ctx.rid, ctx.settings)
    s = ctx.settings
    return block("live", as_of=ctx.now,
                 patterns=[{"when": p.when, "weekday": p.weekday, "shift": p.shift, "times_short": p.times_short, "of_last": p.of_last, "short_each": kes(p.average_short_cents),
                            "total": kes(p.total_short_cents)} for p in found],
                 reason=None if found else "No shift has come up short again and again in the last four weeks.",
                 note="A pattern is a reason to look at that shift, not a conclusion about anyone.",
                 assumption=assume("cash_tolerance_kes", s.cash_tolerance_cents // 100, label="Cash count difference we accept"))


def _mpesa(ctx: OwnerContext) -> dict:
    """The M-Pesa check (owner/mpesa_match.py): memoised, because Home shows it twice (Zone 1 and the cash panel)."""
    from owner import mpesa_match
    return ctx.cached("mpesa", lambda: ctx.safe("cash.mpesa", lambda: mpesa_match.block(ctx)))


def cash_area(ctx: OwnerContext) -> tuple[dict, dict]:
    shifts = ctx.safe("cash.shifts", lambda: _shifts(ctx))
    cancelled = ctx.safe("cash.cancelled", lambda: _cancelled_sales(ctx))
    below = ctx.safe("cash.below_menu_price", lambda: _below_menu_price(ctx))
    mpesa = _mpesa(ctx)
    blocks = {"shifts": shifts, "cancelled_sales": cancelled, "below_menu_price": below, "mpesa": mpesa,
              "patterns": ctx.safe("cash.patterns", lambda: _patterns(ctx))}
    # a gap between the till and the statement is one more thing to look at (one, however many sales or payments it spans)
    gap = 1 if mpesa.get("state") in ("not_from_pos", "stale") and (mpesa["sales_without_payment"]["count"] or mpesa["payments_without_sale"]["count"]
                                                                   or mpesa["different_amounts"]) else 0
    flagged = sum(1 for s in shifts.get("shifts", []) if s["check"]) + (cancelled.get("to_check", 0) if cancelled["state"] == "live" else 0) + gap
    if shifts["state"] in ("no_data", "unavailable") and cancelled["state"] in ("no_data", "unavailable"):
        head = summary(None, _STATUS_WORD["unknown"], "unknown", label="Counts and sales to look at")
    elif flagged:
        head = summary(flagged, "Things to check", "bad", label="Counts and sales to look at")
    else:
        head = summary(0, "Balanced", "good", label="Counts and sales to look at")
    return head, blocks


# ═════════════════════════════════════════════════════════════════════════════
# Staff
# ═════════════════════════════════════════════════════════════════════════════

def _wages(ctx: OwnerContext) -> dict:
    labor = _labor(ctx)
    summ = labor["summary"]
    if summ.get("labor_status") == "NO_DATA":
        return no_data("No staff shifts recorded yet.")
    latest = ctx.db.query(models.LaborShift.created_at).filter(models.LaborShift.restaurant_id == ctx.rid).order_by(
        models.LaborShift.created_at.desc()).first()
    s = ctx.settings
    return {**ctx.entered_state(latest[0] if latest else None),
            "wages_pct": summ["labor_pct"], "wages_30d": kes(summ["total_labor_cost_30d"]), "sales_per_staff_hour": kes(summ["sales_per_hour"]),
            "overtime_hours": summ["overtime_hours_30d"], "overtime_cost": kes(summ["overtime_cost_30d"]),
            "word": "Fine" if summ["labor_status"] == "HEALTHY" else "High",
            "by_person": [{"name": p["staff_name"], "hours": p["hours_worked"], "wages": kes(p["labor_cost"])} for p in labor.get("staff_productivity", [])[:10]],
            "assumptions": [assume("labour_target_pct", s.labour_target_pct, label="Wages target"),
                            assume("overtime_after_hours", s.overtime_after_hours, label="Overtime starts after (hours)")],
            "assumption": assume("labour_target_pct", s.labour_target_pct, label="Wages target")}


def _on_shift(ctx: OwnerContext) -> dict:
    overview = _overview_core(ctx)
    start, end = overview._eat_range("today")
    card = overview._staff_card(ctx.db, ctx.rid, start, end)
    if not card["scheduled"]:
        return no_data("No shifts scheduled today.")
    return block("live", as_of=ctx.now, scheduled=card["scheduled"], on_shift=card["on_shift"])


def _kitchen(ctx: OwnerContext) -> dict:
    from ai.kds_intelligence import get_kds_intelligence
    kds = ctx.cached("kds", lambda: get_kds_intelligence(ctx.db, ctx.rid))
    if not kds.get("station_performance"):
        return no_data("No kitchen preparation times recorded yet.")
    return {**ctx.order_state(needs_days=14),
            "stations": [{"station": s["station"], "avg_minutes": s["avg_minutes"]} for s in kds["station_performance"]],
            "slowest": [{"station": b["station"], "minutes_over_average": b["above_avg_by"]} for b in kds.get("bottlenecks", [])[:3]]}


def staff_area(ctx: OwnerContext) -> tuple[dict, dict]:
    wages = ctx.safe("staff.wages", lambda: _wages(ctx))
    blocks = {"wages": wages, "on_shift": ctx.safe("staff.on_shift", lambda: _on_shift(ctx)), "kitchen": ctx.safe("staff.kitchen", lambda: _kitchen(ctx))}
    if wages["state"] in ("no_data", "unavailable"):
        head = summary(None, _STATUS_WORD["unknown"], "unknown", label="Out of every KES 100, wages")
    else:
        head = summary(wages["wages_pct"], wages["word"], "good" if wages["word"] == "Fine" else "bad", unit="%", label="Out of every KES 100, wages")
    return head, blocks


# ═════════════════════════════════════════════════════════════════════════════
# Permits & Settings
# ═════════════════════════════════════════════════════════════════════════════

def _settings_summary(ctx: OwnerContext) -> dict:
    from owner.settings import describe
    d = describe(ctx.db, ctx.rid)
    changed = [f for f in d["fields"] if not f["is_default"]]
    return block("as_entered" if d["chosen"] else "no_data", as_of=d["updated_at"], chosen=d["chosen"], changed=len(changed),
                 total=len(d["fields"]), updated_at=d["updated_at"], reason=None if d["chosen"] else "You have not set your own targets yet — defaults are in use.")


def _till_connection(ctx: OwnerContext) -> dict:
    conn = _overview_core(ctx)._source_connection(ctx.db, ctx.tenant_id)
    word = {"direct": "Recorded here", "receiving": "Receiving", "awaiting_first_delivery": "Waiting for first sale", "unavailable": "Can't be read"}.get(conn["state"], conn["state"])
    return block("live", as_of=conn.get("last_received_at") or ctx.now, info=True, source=conn["source"], word=word,
                 reconciled=bool(conn.get("reconciled")), records=conn.get("records"))


def _data_trust(ctx: OwnerContext) -> dict:
    from ai.data_quality import get_cost_price_quality
    q = ctx.cached("data_quality", lambda: get_cost_price_quality(ctx.db, ctx.rid))
    s = q["summary"]
    if not s["total_items"]:
        return no_data("No dishes on the menu yet.")
    return block("live", as_of=ctx.now, dishes=s["total_items"], costs_known_pct=s["coverage_pct"], missing_costs=s["missing_cost_count"],
                 to_fix=s["items_with_issues"])


def permits_area(ctx: OwnerContext) -> tuple[dict, dict]:
    settings_block = ctx.safe("permits.settings", lambda: _settings_summary(ctx))
    trust = ctx.safe("permits.data_trust", lambda: _data_trust(ctx))
    blocks = {"licences": ctx.safe("permits.licences", lambda: licences_block(ctx)), "settings": settings_block,
              "till_connection": ctx.safe("permits.till", lambda: _till_connection(ctx)), "data_trust": trust}
    if trust["state"] == "live":
        pct = trust["costs_known_pct"]
        head = summary(pct, "Costs known" if pct >= 90 else "Costs missing", "good" if pct >= 90 else "watch", unit="%", label="Dishes with a cost")
    else:
        head = summary(None, _STATUS_WORD["unknown"], "unknown", label="Dishes with a cost")
    return head, blocks


# ═════════════════════════════════════════════════════════════════════════════

_BUILDERS: dict[str, Callable[[OwnerContext], tuple[dict, dict]]] = {
    "money": money_area, "sales_dishes": sales_dishes_area, "store": store_area, "cash": cash_area,
    "staff": staff_area, "permits": permits_area,
}


def compose_area(ctx: OwnerContext, key: str) -> dict:
    """One area, exactly as Home embeds it and `/owner/area/{key}` returns it."""
    if key not in _BUILDERS:
        raise KeyError(key)
    try:
        with ctx.db.begin_nested():
            head, blocks = _BUILDERS[key](ctx)
    except Exception:  # noqa: BLE001 — an area must always render
        states.logger.exception("owner area %s failed for restaurant %s", key, ctx.rid)
        head, blocks = summary(None, _STATUS_WORD["unknown"], "unknown"), {}
    # `info` blocks (a pointer to the simulator, the till connection status) are not measurements: they never make
    # an area look live on their own, so a fresh tenant's areas say no_data.
    measured = [b for b in blocks.values() if isinstance(b, dict) and "state" in b and not b.get("info")]
    worst = [b["state"] for b in measured]
    area_state = ("live" if "live" in worst else "as_entered" if "as_entered" in worst else "learning" if "learning" in worst
                  else "stale" if "stale" in worst else "no_data" if "no_data" in worst else "unavailable")
    as_of = next((b.get("as_of") for b in measured if b.get("as_of")), None)
    return {"key": key, "title": AREA_TITLES[key], "state": area_state, "as_of": as_of, "summary": head, "blocks": blocks}
