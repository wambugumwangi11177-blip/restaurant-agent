"""
backend/owner/report_sections.py — the sections of the owner's reports (docs/v2/SPEC.md §4 P5.2).

Every section reads the very block Home shows for the same thing (owner/areas.py), so a report and Home cannot disagree; the ones that
can be cut to the report's period (cash counts, cancelled sales, the monthly and yearly series) are cut to it. Each section says which
window it covers (`window`), gives one sentence made from its own rows (`headline`, checked by owner/answers.py::ungrounded) and the rows
themselves (`rows`, the same shape an Ask LEVIII answer has), and — like every owner block — its state; a section with nothing to say
says why.

A builder is `(ctx, period, month) -> dict`; `owner/reports.py` lists which sections each report has and wraps a builder that fails
in an honest "could not be read".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import models
from owner import areas
from owner.answers import assumption, day_text, from_setting, kes_text, pct_text, row, setting_text
from owner.states import OwnerContext, block, kes, no_data
from time_utils import EAT_OFFSET, eat_date

MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


# ── the shape of a section ───────────────────────────────────────────────────

def _done(base: dict, window: str, headline: str, rows: list[dict], assumptions: list[dict] | None = None, **extra) -> dict:
    """A section with something to say: `base` is the block it was read from (its state, its as_of, what it was entered up to)."""
    keep = {k: base[k] for k in ("state", "as_of", "entered_up_to", "day", "of", "age_days") if k in base}
    return {**keep, "window": window, "headline": headline, "rows": rows, "assumptions": assumptions or [], **extra}


def _nothing(base: dict, window: str, fallback: str) -> dict:
    """A section whose source has nothing: its state (no data, or could not be read) and the reason."""
    return {**{k: base[k] for k in ("state", "as_of") if k in base}, "window": window, "reason": base.get("reason") or fallback, "rows": [], "assumptions": []}


def _empty(base: dict) -> bool:
    return base.get("state") in ("no_data", "unavailable")


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _local(utc_naive):
    return utc_naive + EAT_OFFSET


def _month_end(first: date) -> date:
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _check_phrase(key: str, n: int) -> str:
    """Count plus the thing, with a real plural. '2 handover that doesn't matchs' was the old bug."""
    if key == "handover":
        return f"{n} handover that doesn't match" if n == 1 else f"{n} handovers that don't match"
    if key == "missing_stock":
        return f"{n} item used more than your sales explain" if n == 1 else f"{n} items used more than your sales explain"
    words = {"unusual_cancelling": "unusual cancelling", "unusual_refunds": "unusual refunds", "late_night": "late-night activity"}
    return f"{n} {words.get(key, key)}"


def _window_text(period: str, month: date | None, today: date, now: datetime | None = None) -> str:
    if period == "daily":
        from time_utils import service_caption
        return service_caption(now)
    if period == "weekly":
        return "The last 7 days"
    if period == "monthly" and month is not None:
        partial = month.replace(day=1) == today.replace(day=1)
        return f"{MONTH_NAMES[month.month - 1]} {month.year}" + (" so far" if partial else "")
    return "The last 12 months"


# ── cash count check ─────────────────────────────────────────────────────────

def cash_check(ctx: OwnerContext, period: str, month: date | None) -> dict:
    from owner import reports
    from ai.cash_reconciliation.intelligence import drawer_tolerance_cents
    lo, hi = reports._window(period, month)
    window = _window_text(period, month, eat_date(ctx.now), ctx.now)
    counts = ctx.db.query(models.CashDrawerCount).filter(
        models.CashDrawerCount.restaurant_id == ctx.rid, models.CashDrawerCount.window_start >= lo, models.CashDrawerCount.window_start < hi
    ).order_by(models.CashDrawerCount.window_start.desc()).all()
    latest = ctx.db.query(models.CashDrawerCount.counted_at).filter(models.CashDrawerCount.restaurant_id == ctx.rid).order_by(
        models.CashDrawerCount.counted_at.desc()).first()
    base = ctx.entered_state(latest[0] if latest else None, empty="No cash counts entered yet.")
    if base["state"] == "no_data":
        return _nothing(base, window, "No cash counts entered yet.")
    if not counts:
        said = f"No cash count has been entered for {window}." if period == "daily" else "No cash count has been entered in this period."
        return _nothing(no_data(said), window, said)
    s = ctx.settings
    rows, looked = [], 0
    for c in counts:
        gap = c.counted_amount_cents - c.expected_amount_cents
        check = abs(gap) > drawer_tolerance_cents(c.expected_amount_cents, s)
        looked += check
        rows.append(row("count", day_text(_local(c.window_start).date()) + (" · to look at" if check else ""), kes(gap), "kes",
                        f"counted {kes_text(kes(c.counted_amount_cents))}, expected {kes_text(kes(c.expected_amount_cents))}", check=check))
    rows = [row("counts", "Counts checked", len(counts), "count"), row("to_look_at", "Counts to look at", looked, "count")] + rows
    patterns = [] if period == "daily" else (areas._patterns(ctx).get("patterns") or [])
    for p in patterns[:3]:
        rows.append(row("pattern", p["when"], p["total"], "kes", f"short {p['times_short']} of the last {p['of_last']} times, about {kes_text(p['short_each'])} each time"))
    head = (f"{looked} of the {_plural(len(counts), 'cash count')} {'is' if looked == 1 else 'are'} worth a look." if looked
            else f"{'The' if len(counts) == 1 else 'All'} {_plural(len(counts), 'cash count')} match.")
    if patterns:
        p = patterns[0]
        head += f" {p['when']} was short {p['times_short']} of the last {p['of_last']} times."
    return _done(base, window, head, rows, from_setting(areas._shifts(ctx).get("assumption")) + [assumption("A pattern is a reason to look at that shift, not a conclusion about anyone.")])


# ── things to check ──────────────────────────────────────────────────────────

def things_to_check(ctx: OwnerContext, period: str, month: date | None) -> dict:
    fraud = areas._cancelled_sales(ctx)
    missing = areas._missing_stock(ctx)
    handovers = areas._handovers(ctx)
    rows: list[dict] = []
    if not _empty(fraud):
        for key, label, field in (("unusual_cancelling", "Unusual cancelling", "unusual_cancelling"), ("unusual_refunds", "Unusual refunds", "unusual_refunds"),
                                  ("late_night", "Late-night activity", "late_night_activity")):
            if fraud[field]:
                rows.append(row(key, label, fraud[field], "count", "at the till, last 7 days"))
    for i in (missing.get("items") or []) if not _empty(missing) else []:
        if i["check"]:
            rows.append(row("missing_stock", f"{i['item']}: {i['missing']:g} {i['unit']} more used than your sales explain", i["missing_value"], "kes", f"{pct_text(i['off_by_pct'])} more than expected, last 7 days"))
    for h in (handovers.get("doesnt_match") or []) if not _empty(handovers) else []:
        rows.append(row("handover", f"{h['item']}: the store said {h['store_said']:g} {h['unit']}, the kitchen counted {h['kitchen_counted']:g}", None, "text", "a handover that doesn't match, last 30 days"))
    window = "The last 7 days"
    anchor = fraud if not _empty(fraud) else missing if not _empty(missing) else handovers
    if _empty(anchor) and not rows:
        return _nothing(anchor, window, "Nothing is recorded yet to check.")
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["key"]] = kinds.get(r["key"], 0) + 1
    head = (f"{_plural(len(rows), 'thing')} to check: " + "; ".join(_check_phrase(k, n) for k, n in kinds.items()) + "."
            if rows else "Nothing to check: no unusual cancelling, no missing stock, no handover that doesn't match.")
    return _done(anchor, window, head, rows, [assumption("These are things to check, not conclusions about anyone.")])


# ── stock today ──────────────────────────────────────────────────────────────

def stock_today(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._reorder(ctx)
    if _empty(b):
        return _nothing(b, "Right now", "No stock items recorded yet.")
    due = b["time_to_reorder"]
    rows = [row("reorder", f"{i['item']}", i["days_left"], "days" if i["days_left"] is not None else "text",
                f"{i['left']:g} {i['unit']} left" + (f"; {i['status']}" if i.get("status") else "")) for i in due]
    rows.insert(0, row("tracked", "Items tracked", b["tracked"], "count"))
    rows += [row("draft", f"Order {d['order']:g} {d['unit']} of {d['item']}", None, "text", f"from {d['supplier']}" if d.get("supplier") else None) for d in b["drafts"][:5]]
    head = (f"{_plural(len(due), 'item')} {'is' if len(due) == 1 else 'are'} due to reorder out of {b['tracked']} tracked." if due
            else f"Nothing is due to reorder; {b['tracked']} items tracked.")
    return _done(b, "Right now", head, rows)


# ── dishes ───────────────────────────────────────────────────────────────────

def dishes(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._matrix(ctx)
    if _empty(b):
        return _nothing(b, "The last 30 days", "No dishes sold yet.")
    ds = sorted(b["dishes"], key=lambda d: d["profit"], reverse=True)
    best, weakest = ds[0], ds[-1]
    shown = ds[:7] + ([weakest] if len(ds) > 7 else ds[7:8])
    rows = [row("dish", d["name"], d["profit"], "kes", f"{d['kind']} · {d['sold']} sold · keeps {pct_text(d['keeps_pct'])}") for d in shown]
    head = f"{best['name']} earned the most ({kes_text(best['profit'])}) and {weakest['name']} the least ({kes_text(weakest['profit'])})." if len(ds) > 1 else f"{best['name']} earned {kes_text(best['profit'])}."
    return _done(b, "The last 30 days", head, rows, from_setting(b.get("assumption")))


def price_ideas(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._price_ideas(ctx)
    if _empty(b):
        return _nothing(b, "The last 30 days", "No sales recorded yet.")
    ideas, low = b["ideas"], b["priced_too_low"]
    if not ideas and not low:
        return _done(b, "The last 30 days", "No price changes are worth suggesting right now.", [], [a for x in (b.get("assumptions") or []) for a in from_setting(x)])
    rows = [row("idea", f"{i['dish']}: KES {i['from']:,.0f} to KES {i['to']:,.0f}", i["month_gain"], "kes", i["kind"], why=i["why"]) for i in ideas]
    rows += [row("too_low", f"{l['dish']} keeps only {pct_text(l['keeps_pct'])} of its price", l["month_gain"], "kes", "priced too low") for l in low if l["dish"] not in {i["dish"] for i in ideas}]
    top = max(rows, key=lambda r: r["value"] or 0)
    head = f"{_plural(len(rows), 'price idea')}; the biggest is {top['label'].split(':')[0]}, worth about {kes_text(top['value'])} a month."
    return _done(b, "The last 30 days", head, rows, [a for x in (b.get("assumptions") or []) for a in from_setting(x)] + [assumption("Each figure is an estimate of a month's gain, not a promise.")])


# ── missing stock ────────────────────────────────────────────────────────────

def missing_stock(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._missing_stock(ctx)
    if _empty(b):
        return _nothing(b, "The last 7 days", "No stock movements recorded yet.")
    items = b["items"]
    rows = [row("item", i["item"], i["missing_value"], "kes",
                f"used {i['used']:g} {i['unit']}, expected {i['expected']:g}, {pct_text(i['off_by_pct'])} off" + ("; worth a look" if i["check"] else "")) for i in items[:10]]
    flagged = [i for i in items if i["check"]]
    head = (f"{_plural(len(flagged), 'item')} used more than your sales explain; the biggest gap is {flagged[0]['item']} ({kes_text(flagged[0]['missing_value'])})."
            if flagged else "Everything used matches what your sales explain.")
    return _done(b, "The last 7 days", head, rows, from_setting(b.get("assumption")) + [assumption("A gap is a reason to check the store and the portions, not a finding about anyone.")])


# ── M-Pesa check ─────────────────────────────────────────────────────────────

def mpesa_check(ctx: OwnerContext, period: str, month: date | None) -> dict:
    """The statement against the M-Pesa sales, over the days the statement covers (not the report's days: a statement is a file)."""
    b = areas._mpesa(ctx)
    window = "The days your M-Pesa statement covers"
    if _empty(b):
        return _nothing(b, window, "Upload your M-Pesa statement to check it against your sales.")
    gap_s, gap_p = b["sales_without_payment"], b["payments_without_sale"]
    rows = [row("checked_sales", "M-Pesa sales checked", b["checked"]["sales"], "count"), row("checked_payments", "Payments on the statement", b["checked"]["payments"], "count"),
            row("matched", "Sales with a payment", b["matched"]["sales"], "count", f"worth {kes_text(b['matched']['kes'])}"),
            row("sales_without_payment", "Sales with no payment on the statement", gap_s["count"], "count", f"together {kes_text(gap_s['kes'])}"),
            row("sales_without_payment_kes", "Value of sales with no payment", gap_s["kes"], "kes"),
            row("payments_without_sale", "Payments with no sale recorded", gap_p["count"], "count", f"together {kes_text(gap_p['kes'])}"),
            row("payments_without_sale_kes", "Value of payments with no sale", gap_p["kes"], "kes")]
    if b["different_amounts"]:
        rows.append(row("different_amounts", "Sales paid a different amount from the one recorded", len(b["different_amounts"]), "count"))
    for item in gap_s["items"][:5]:
        rows.append(row("sale", f"{day_text(_local(_utc(item['at'])).date())} · {item['what']}", item["kes"], "kes", "no payment on the statement"))
    for item in gap_p["items"][:5]:
        rows.append(row("payment", f"{day_text(_local(_utc(item['at'])).date())} · {item['from'] or 'payment'}", item["kes"], "kes", "no sale recorded"))
    return _done(b, window, b["headline"], rows, from_setting(b.get("assumption")) + [assumption(b["note"])],
                 source=b.get("source"), outside_statement=b["outside_statement"])


def _utc(text: str):
    from datetime import datetime
    return datetime.fromisoformat(text).replace(tzinfo=None)


# ── wages ────────────────────────────────────────────────────────────────────

def wages(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._wages(ctx)
    if _empty(b):
        return _nothing(b, "The last 30 days", "No staff shifts recorded yet.")
    rows = [row("wages_pct", "Out of every KES 100, wages", b["wages_pct"], "pct", b["word"]), row("wages", "Wages", b["wages_30d"], "kes"),
            row("per_hour", "Sales for each staff hour", b["sales_per_staff_hour"], "kes"), row("overtime_hours", "Overtime", b["overtime_hours"], "hours", f"costing {kes_text(b['overtime_cost'])}")]
    rows += [row("person", p["name"], p["wages"], "kes", f"{p['hours']:g} hours") for p in b["by_person"][:5]]
    head = f"Wages are {pct_text(b['wages_pct'])} of sales ({b['word'].lower()}): {kes_text(b['wages_30d'])}, with {b['overtime_hours']:g} hours of overtime."
    return _done(b, "The last 30 days", head, rows, [a for x in (b.get("assumptions") or []) for a in from_setting(x)])


# ── outlook ──────────────────────────────────────────────────────────────────

def outlook(ctx: OwnerContext, period: str, month: date | None) -> dict:
    if period == "weekly":
        b = areas._forecast(ctx)
        if _empty(b) or b["state"] == "learning":
            return _nothing(b, "The next 7 days", "Not enough sales to forecast yet.")
        days = b["next_7_days"]
        rows = [row("day", f"{d['day']} {day_text(date.fromisoformat(d['date']))}", d["usual"], "kes", f"between {kes_text(d['low'])} and {kes_text(d['high'])}") for d in days]
        total, low, high = round(sum(d["usual"] for d in days), 2), round(sum(d["low"] for d in days), 2), round(sum(d["high"] for d in days), 2)
        rows.insert(0, row("total", "The next 7 days, together", total, "kes", f"between {kes_text(low)} and {kes_text(high)}"))
        return _done(b, "The next 7 days", f"The next 7 days should bring about {kes_text(total)}, somewhere between {kes_text(low)} and {kes_text(high)}.", rows,
                     [assumption(b["note"])])
    b = areas._outlook(ctx)
    if _empty(b) or b["state"] == "learning":
        return _nothing(b, "The next 30 days", "Not enough history for a 30-day outlook.")
    rows = [row("expected", "The next 30 days", b["next_30_days"], "kes"), row("low", "At the low end", b["low"], "kes"), row("high", "At the high end", b["high"], "kes"),
            row("confidence", "How sure", b["confidence_pct"], "pct")]
    return _done(b, "The next 30 days", f"The next 30 days should bring about {kes_text(b['next_30_days'])}, between {kes_text(b['low'])} and {kes_text(b['high'])}.", rows, [assumption(b["note"])])


# ── kitchen, bookings, suppliers ─────────────────────────────────────────────

def kitchen(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._kitchen(ctx)
    if _empty(b):
        return _nothing(b, "The last 30 days", "No kitchen preparation times recorded yet.")
    rows = [row("station", s["station"].capitalize(), s["avg_minutes"], "minutes", "on average") for s in b["stations"]]
    slow = b["slowest"]
    rows += [row("slowest", f"{x['station'].capitalize()} runs over the average", x["minutes_over_average"], "minutes") for x in slow]
    head = (f"{slow[0]['station'].capitalize()} is slowest, {slow[0]['minutes_over_average']:g} minutes over the kitchen's average." if slow
            else f"Preparation times are even across {_plural(len(rows), 'station')}.")
    return _done(b, "The last 30 days", head, rows)


def bookings(ctx: OwnerContext, period: str, month: date | None) -> dict:
    from owner import home
    from routers import overview
    start, end = overview._eat_range("today")
    b = home._bookings(ctx, overview._bookings_card(ctx.db, ctx.rid, start, end)["covers_today"])
    if _empty(b):
        return _nothing(b, "The next 7 days", "No bookings in the next 7 days.")
    rows = [row("day", day_text(date.fromisoformat(d["date"])), d["covers"], "count", f"{_plural(d['bookings'], 'booking')}, {_plural(d['covers'], 'guest')}") for d in b["next_days"]]
    total = sum(d["covers"] for d in b["next_days"])
    rows.insert(0, row("total", "Guests booked, next 7 days", total, "count"))
    if b["covers_today"]:
        rows.insert(1, row("tonight", "Of them, tonight", b["covers_today"], "count"))
    head = f"{_plural(total, 'guest')} booked over the next 7 days" + (f", {b['covers_today']} of them tonight." if b["covers_today"] else ".")
    return _done(b, "The next 7 days", head, rows)


def suppliers(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._suppliers(ctx)
    if _empty(b):
        return _nothing(b, "All orders so far", "No suppliers added yet.")
    rows = [row("supplier", s["name"], s["on_time_pct"], "pct", f"{s['word']}; {_plural(s['closed_orders'], 'order')} delivered") for s in b["suppliers"]]
    rows += [row("short", f"{s['supplier']} · {s['item']}", s["short_value"], "kes", f"{s['received']:g} of {s['ordered']:g} {s['unit']} on {day_text(date.fromisoformat(s['on']))}") for s in b["short_deliveries"]]
    short = b["short_deliveries"]
    head = (f"{short[0]['supplier']} delivered {short[0]['received']:g} of the {short[0]['ordered']:g} {short[0]['unit']} of {short[0]['item']} you ordered ({kes_text(short[0]['short_value'])} short)."
            if short else f"{_plural(len(b['suppliers']), 'supplier')} on record; no short deliveries.")
    return _done(b, "All orders so far", head, rows, [assumption("A supplier with fewer than 3 delivered orders shows as Learning, not a score.")])


# ── monthly: costs, channels, store, decisions, savings, marketing, data trust, rules ──

def costs(ctx: OwnerContext, period: str, month: date | None) -> dict:
    dials = areas._money_cost_dials(ctx)
    bills = areas.bills_block(ctx)
    spikes = areas.spikes_block(ctx)
    if _empty(dials):
        return _nothing(dials, "The last 30 days", "No sales recorded yet.")
    rows = [row("food_cost", "Out of every KES 100, ingredients", dials["food_cost_pct"], "pct", f"{dials['food_cost_word']} (your target {pct_text(dials['food_cost_target_pct'])})")]
    if dials.get("wages_pct") is not None:
        rows.append(row("wages", "Out of every KES 100, wages", dials["wages_pct"], "pct", f"{dials['wages_word']} (your target {pct_text(dials['wages_target_pct'])})"))
    for s in ((spikes.get("spikes") or []) if not _empty(spikes) else [])[:3]:
        rows.append(row("spike", f"{s['name']} is {pct_text(s['up_pct'])} above usual", s["extra_kes"], "kes", f"{kes_text(s['this_month_kes'])} this month against {kes_text(s['usual_kes'])}"))
    for b in ((bills.get("upcoming") or []) if not _empty(bills) else [])[:3]:
        rows.append(row("bill", b["name"], b["amount_kes"], "kes", f"due {day_text(date.fromisoformat(b['due_on']))}" + ("; your sales will not cover it" if b["short"] else "")))
    head = f"Ingredients are {pct_text(dials['food_cost_pct'])} of sales ({dials['food_cost_word'].lower()})"
    if dials.get("wages_pct") is not None:
        head += f" and wages {pct_text(dials['wages_pct'])} ({dials['wages_word'].lower()})"
    head += "."
    return _done(dials, "The last 30 days", head, rows, [a for x in (dials.get("assumptions") or []) for a in from_setting(x)])


def channels(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._delivery_and_dayparts(ctx)
    if _empty(b):
        return _nothing(b, "The last 30 days", "No sales recorded yet.")
    rows = [row("channel", c["channel"], c["keeps"], "kes", f"{_plural(c['orders'], 'order')} · keeps {pct_text(c['keeps_pct'])}" + ("" if c["pays_commission"] else "")) for c in b["channels"]]
    rows += [row("gap", f"{g['dish']} on {g['channel']} keeps {kes_text(g['keeps'])}", g["keeps_dine_in"], "kes", f"against {kes_text(g['keeps_dine_in'])} dine-in; to keep your floor, price it at {kes_text(g['price_to_keep_floor'])}") for g in b["delivery_gaps"][:3]]
    rows += [row("hours", h["hours"].capitalize(), h["keeps_pct"], "pct", f"{_plural(h['orders'], 'order')}") for h in b["best_and_weakest_hours"]]
    best = max(b["channels"], key=lambda c: c["keeps"])
    head = f"{best['channel']} keeps the most ({kes_text(best['keeps'])})" + (f"; {b['delivery_gaps'][0]['dish']} on {b['delivery_gaps'][0]['channel']} keeps {kes_text(b['delivery_gaps'][0]['keeps'])} where dine-in keeps {kes_text(b['delivery_gaps'][0]['keeps_dine_in'])}." if b["delivery_gaps"] else ".")
    return _done(b, "The last 30 days", head, rows, [a for x in (b.get("assumptions") or []) for a in from_setting(x)])


def store(ctx: OwnerContext, period: str, month: date | None) -> dict:
    reorder, missing, sup = areas._reorder(ctx), areas._missing_stock(ctx), areas._suppliers(ctx)
    if all(_empty(b) for b in (reorder, missing, sup)):
        return _nothing(reorder, "The last 7 days", "No stock or supplier records yet.")
    rows, parts = [], []
    if not _empty(reorder):
        due = reorder["time_to_reorder"]
        rows.append(row("reorder", "Items due to reorder", len(due), "count", ", ".join(i["item"] for i in due[:4]) or None))
        parts.append(f"{_plural(len(due), 'item')} due to reorder")
    if not _empty(missing):
        flagged = [i for i in missing["items"] if i["check"]]
        value = round(sum(i["missing_value"] or 0 for i in flagged), 2)
        rows.append(row("missing", "Items used more than your sales explain", len(flagged), "count", f"worth {kes_text(value)}" if flagged else None))
        rows.append(row("missing_value", "Value of that stock", value, "kes"))
        parts.append(f"{_plural(len(flagged), 'item')} used more than sales explain")
    if not _empty(sup):
        short = sup["short_deliveries"]
        rows.append(row("short", "Short deliveries", len(short), "count", f"worth {kes_text(sum(s['short_value'] for s in short))}" if short else None))
        parts.append(f"{_plural(len(short), 'short delivery', 'short deliveries')}")
    base = next(b for b in (reorder, missing, sup) if not _empty(b))
    return _done(base, "The last 7 days", "Store: " + "; ".join(parts) + ".", rows)


def decisions(ctx: OwnerContext, period: str, month: date | None) -> dict:
    from owner import home
    b = home._costing_you_money(ctx)
    cards = [home._card(c) for c in home.ranked_cards(ctx)] if not _empty(b) else []
    if not cards:
        return _nothing(b if _empty(b) else no_data("Nothing is costing you money that we can see right now."), "Right now", "Nothing is costing you money that we can see right now.")
    rows = [row("idea", c["sentence"], c["kes_month"], "kes" if c["kes_month"] else "text", id=c["id"], action=c["action"], why=c["why"] or None, tier=c["tier"], domain=c["domain"]) for c in cards[:5]]
    top = cards[0]
    head = f"Start with: {top['sentence']}" + (f" — about {kes_text(top['kes_month'])} a month." if top["kes_month"] else ".")
    return _done(b, "Right now", head, rows, [assumption("Each figure is an estimate of what the idea is worth in a month, from your own sales; it is not a promise.")] + from_setting(top.get("assumption")))


def savings(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._money_savings(ctx)
    from owner.growth import price_results
    results = [r for r in price_results(ctx.db,ctx.rid,ctx.now)
               if r['revenue_change_kes'] is not None and (month is None or r['changed_at'][:7]==month.strftime('%Y-%m'))]
    measured = [row(f"price-result-{r['id']}",f"{r['dish']}: observed revenue after {kes_text(r['old_kes'])} → {kes_text(r['new_kes'])}",
                    r['revenue_change_kes'],'kes',r['reason']) for r in results]
    if _empty(b) and measured:
        return _done({'state':'as_entered','as_of':ctx.now.isoformat()},'14 days before and after each change',
                     'Recorded revenue after approved price changes; not a causal savings claim.',measured,
                     [assumption('Equal 14-day windows; recorded paid sales, not projected savings. Other factors may explain the change.')])
    if _empty(b):
        return _nothing(b, "Since you started", "Nothing approved yet.")
    rows = [row("captured", "Brought in by ideas you approved, a month", b["captured_kes_month"], "kes"), row("hours", "Hours saved, last 30 days", b["hours_saved_30d"], "hours"),
            row("approved", "Ideas you approved", b["approved_ideas"], "count")]
    n = b["approved_ideas"]
    head = (f"The {'idea' if n == 1 else f'{n} ideas'} you approved {'brings' if n == 1 else 'bring'} in about {kes_text(b['captured_kes_month'])} a month "
            f"and saved about {b['hours_saved_30d']:g} hours.")
    return _done(b, "Since you started", head, rows+measured, [assumption("Aggregate savings are estimates; individual price-result rows are observed equal-window revenue changes, not proven causal savings.")])


def marketing(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._win_back(ctx)
    if _empty(b):
        return _nothing(b, "Right now", "No lapsed regulars to win back.")
    rows = [row("lapsed", "Guests who haven't been back", b["lapsed_guests"], "count"), row("reachable", "Of them, with a phone number", b["reachable"], "count"), row("offers", "Offers ready", b["offers"], "count")]
    return _done(b, "Right now", f"{b['lapsed_guests']} guests haven't been back for a while; {b['reachable']} have a phone number and {b['offers']} offers are ready.", rows,
                 [assumption("An offer is a draft for you to send; nothing is sent for you.")])


def data_trust(ctx: OwnerContext, period: str, month: date | None) -> dict:
    b = areas._data_trust(ctx)
    if _empty(b):
        return _nothing(b, "Right now", "No dishes on the menu yet.")
    rows = [row("dishes", "Dishes", b["dishes"], "count"), row("known", "Dishes whose cost is known", b["costs_known_pct"], "pct"), row("missing", "Dishes with no cost yet", b["missing_costs"], "count")]
    head = f"The cost is known for {pct_text(b['costs_known_pct'])} of your {b['dishes']} dishes." + (f" {b['to_fix']} still need a cost." if b["to_fix"] else "")
    return _done(b, "Right now", head, rows, [assumption("A dish with no recipe cost is left out of food cost, so the real figure is higher.")])


def rules_used(ctx: OwnerContext, period: str, month: date | None) -> dict:
    from owner.settings import describe
    d = describe(ctx.db, ctx.rid)
    rows = []
    for f in d["fields"]:
        if f["group"] == "Alerts and permits" and f["is_default"]:
            continue
        figure = f["unit"] in ("KES", "%")
        changed_from = f"you changed it from {setting_text(f['unit'], f['default'])}"
        note = (changed_from if not f["is_default"] else None) if figure else setting_text(f["unit"], f["value"]) + ("" if f["is_default"] else f" ({changed_from})")
        rows.append(row("rule", f["label"], f["value"] if figure else None, "kes" if f["unit"] == "KES" else "pct" if f["unit"] == "%" else "text", note,
                        setting=f["key"], changed=not f["is_default"]))
    changed = sum(1 for f in d["fields"] if not f["is_default"])
    rows = [row("changed", "Targets you changed", changed, "count"), row("total", "Targets in all", len(d["fields"]), "count")] + rows
    head = (f"{changed} of your {len(d['fields'])} targets are your own; the rest are the usual answers." if d["chosen"]
            else "You have not set your own targets yet, so every figure here uses the usual answers.")
    base = block("as_entered", as_of=ctx.now, entered_up_to=d["updated_at"][:10]) if d["updated_at"] else block("live", as_of=ctx.now)
    return _done(base, "Used for every figure in this report", head, rows, info=True)           # information about the report, not data in it


# ── yearly: trends, profit and loss by month, busy and quiet months ──────────

def _months(ctx: OwnerContext, n: int = 12) -> list[date]:
    today = eat_date(ctx.now).replace(day=1)
    out = []
    for _ in range(n):
        out.append(today)
        today = (today - timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def _series(ctx: OwnerContext) -> list[dict]:
    from owner.money.pnl import nairobi_utc_range
    from routers import overview
    today = eat_date(ctx.now)
    out = []
    for first in _months(ctx):
        lo, hi = nairobi_utc_range(first, min(_month_end(first), today))
        core = overview._summarize(ctx.db, ctx.rid, lo, hi)
        out.append({"month": first.strftime("%Y-%m"), "label": f"{MONTH_NAMES[first.month - 1][:3]} {first.year}", "sales": core["revenue"], "orders": core["orders"],
                    "partial": first == today.replace(day=1)})
    return out


def trends(ctx: OwnerContext, period: str, month: date | None) -> dict:
    base = ctx.order_state()
    if base["state"] == "no_data":
        return _nothing(base, "The last 12 months", "No sales recorded yet.")
    series = _series(ctx)
    live = [m for m in series if m["orders"]]
    total = round(sum(m["sales"] for m in series), 2)
    rows = [row("total", "Sold in the last 12 months", total, "kes")]
    rows += [row("month", m["label"] + (" so far" if m["partial"] else ""), m["sales"], "kes", f"{_plural(m['orders'], 'order')}") for m in series]
    best = max(live, key=lambda m: m["sales"])
    head = f"Over the last {len(series)} months you sold {kes_text(total)}; the best month was {best['label']} ({kes_text(best['sales'])})."
    return _done(base, "The last 12 months", head, rows, [assumption("Sales are paid orders that were not cancelled, by the day they were taken, in Nairobi time.")], series=series)


def yearly_pnl(ctx: OwnerContext, period: str, month: date | None) -> dict:
    from owner.money.pnl import compute_pnl
    base = ctx.order_state()
    if base["state"] == "no_data":
        return _nothing(base, "The last 12 months", "No sales recorded yet.")
    today = eat_date(ctx.now)
    rows, sales_total, kept_total, incomplete = [], 0, 0, 0
    for first in _months(ctx):
        p = compute_pnl(ctx.db, ctx.rid, first, _month_end(first), ctx.settings, today=today)
        if not p["orders"]:
            continue
        sales_total += p["sales_cents"]
        kept_total += p["operating_profit_cents"]
        note = f"sold {kes_text(kes(p['sales_cents']))}" + ("" if p["costs_entered"] else " · no costs entered")
        incomplete += 0 if p["costs_entered"] else 1
        rows.append(row("month", f"{MONTH_NAMES[first.month - 1][:3]} {first.year}" + (" so far" if first == today.replace(day=1) else ""), kes(p["operating_profit_cents"]), "kes", note))
    if not rows:
        return _nothing(no_data("No sales recorded in the last 12 months."), "The last 12 months", "No sales recorded in the last 12 months.")
    sales, kept = kes(sales_total), kes(kept_total)
    rows.insert(0, row("total_sales", "Sold, in total", sales, "kes"))
    rows.insert(1, row("total_kept", "Kept, in total", kept, "kes"))
    head = f"Over these months you sold {kes_text(sales)} and kept {kes_text(kept)}."
    assumptions = [assumption("What you kept is sales less ingredients, wages and the costs you entered; a month with no costs entered counts them as nothing.")]
    if incomplete:
        assumptions.append(assumption(f"{_plural(incomplete, 'month')} had no costs entered, so what you kept there is too high."))
    return _done({**base, "state": "as_entered"}, "The last 12 months", head, rows, assumptions)


def seasons(ctx: OwnerContext, period: str, month: date | None) -> dict:
    base = ctx.order_state(needs_days=90)
    if base["state"] in ("no_data", "learning"):
        return _nothing(base, "The last 12 months", "Not enough months recorded yet to tell the busy ones from the quiet ones.")
    done = [m for m in _series(ctx) if m["orders"] and not m["partial"]]
    if len(done) < 3:
        return _nothing(no_data("Fewer than three whole months are recorded."), "The last 12 months", "Fewer than three whole months are recorded.")
    ranked = sorted(done, key=lambda m: m["sales"], reverse=True)
    busy, quiet = ranked[:3], ranked[-3:][::-1]
    rows = [row("busy", m["label"], m["sales"], "kes", "one of your busiest months") for m in busy] + [row("quiet", m["label"], m["sales"], "kes", "one of your quietest months") for m in quiet]
    head = f"{busy[0]['label']} was your busiest whole month ({kes_text(busy[0]['sales'])}) and {quiet[0]['label']} your quietest ({kes_text(quiet[0]['sales'])})."
    return _done(base, "The last 12 months", head, rows, [assumption("Only whole months are ranked; this month is not over.")])
