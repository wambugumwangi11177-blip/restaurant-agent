"""
backend/owner/answer_what.py — the "what" form: what is the position in one area (docs/v2/SPEC.md §4 P5.1).

Nine topics are answered by the deterministic handlers in routers/ai_ask.py, unchanged (stock, revenue, bookings, kitchen, staff, menu,
pricing, profit, ops). The other areas are answered from the very blocks Home shows — `owner/areas.py` — so Ask LEVIII and Home cannot
disagree: cash, things_to_check, suppliers, win_back, savings, data_trust, money.

Every headline is built from the values in the rows beside it (see owner/answers.py::ungrounded).
"""
from __future__ import annotations

from datetime import date
from typing import Callable

from owner import areas
from owner.answers import assumption, day_text, from_setting, kes_text, make, nothing, pct_text, row
from owner.states import OwnerContext, block

LEGACY_TOPICS = ("stock", "revenue", "bookings", "kitchen", "staff", "menu", "pricing", "profit", "ops")


def legacy_topics() -> tuple[str, ...]:
    from routers import ai_ask
    return tuple(t for t in LEGACY_TOPICS if t in ai_ask._HANDLERS)


def _state_of(*blocks: dict) -> tuple[str, str | None]:
    """The honest state of an answer built from several blocks: the first one that has something to say sets it."""
    for b in blocks:
        if b.get("state") not in ("no_data", "unavailable"):
            return b["state"], b.get("as_of")
    return blocks[0]["state"], blocks[0].get("as_of")


def _empty(blocks: list[dict]) -> bool:
    return all(b.get("state") in ("no_data", "unavailable") for b in blocks)


def _reason(blocks: list[dict], fallback: str) -> str:
    return next((b["reason"] for b in blocks if b.get("reason")), fallback)


# ── the nine old topics: the handlers in routers/ai_ask.py ───────────────────

def legacy(ctx: OwnerContext, question: str, topic: str) -> dict:
    from routers import ai_ask
    try:
        with ctx.db.begin_nested():
            card = ai_ask._HANDLERS[topic](ctx.db, ctx.rid, question)
    except Exception:  # noqa: BLE001 — never substitute unrelated facts or expose internals
        card = ai_ask._unavailable_card(topic)
    card = ai_ask._with_provenance(card, ctx.db, ctx.rid)
    answered = card.get("data", {}).get("available") is not False
    state = ctx.order_state() if answered else block("unavailable", reason="The data needed to answer this was not available.")
    steps = [row(f"step{i}", s.get("action", ""), None, "text", s.get("why") or None) for i, s in enumerate(card.get("steps") or [], 1)]
    return make("what", topic, question, state=state["state"], as_of=state.get("as_of"), headline=card.get("finding") or "",
                reason=None if answered else state.get("reason"), rows=steps,
                answer={k: card.get(k) for k in ("finding", "why", "impact", "recommendation", "steps", "data")})


# ── cash count check ─────────────────────────────────────────────────────────

def _cash(ctx: OwnerContext, q: str) -> dict:
    shifts = ctx.safe("ask.cash.shifts", lambda: areas._shifts(ctx))
    patterns = ctx.safe("ask.cash.patterns", lambda: areas._patterns(ctx))
    if shifts.get("state") in ("no_data", "unavailable"):
        return nothing("what", "cash", q, shifts.get("reason") or "No cash counts recorded yet.", state=shifts["state"],
                       next=["Anything to check at the till?"])
    counts = shifts["shifts"]
    to_look = [s for s in counts if s["check"]]
    rows = [row("counts", "Counts checked", len(counts), "count"), row("to_look_at", "Counts to look at", len(to_look), "count")]
    for s in to_look[:5]:
        rows.append(row("shift", s["from"][:10], s["gap"], "kes", f"counted {kes_text(s['counted'])}, expected {kes_text(s['expected'])}"))
    pats = patterns.get("patterns") or []
    for p in pats[:3]:
        rows.append(row("pattern", p["when"], p["total"], "kes", f"short {p['times_short']} of the last {p['of_last']} times, about {kes_text(p['short_each'])} each time"))
    head = (f"{len(to_look)} of the last {len(counts)} cash counts are worth a look." if to_look
            else f"All {len(counts)} recent cash counts match.")
    if pats:
        p = pats[0]
        head += f" {p['when']} was short {p['times_short']} of the last {p['of_last']} times, about {kes_text(p['short_each'])} each time."
    return make("what", "cash", q, state=shifts["state"], as_of=shifts.get("as_of"), headline=head, rows=rows,
                assumptions=from_setting(shifts.get("assumption")) + [assumption(patterns.get("note") or "A pattern is a reason to look, not a conclusion about anyone.")],
                next=["Anything to check at the till?"])


# ── the M-Pesa check ─────────────────────────────────────────────────────────

def _mpesa(ctx: OwnerContext, q: str) -> dict:
    b = areas._mpesa(ctx)
    if b.get("state") in ("no_data", "unavailable"):
        return nothing("what", "mpesa", q, b.get("reason") or "Upload your M-Pesa statement to check it against your sales.", state=b["state"],
                       next=["Anything to check at the till?"])
    gap_s, gap_p = b["sales_without_payment"], b["payments_without_sale"]
    rows = [row("checked_sales", "M-Pesa sales checked", b["checked"]["sales"], "count"), row("checked_payments", "Payments on the statement", b["checked"]["payments"], "count"),
            row("matched", "Sales with a payment", b["matched"]["sales"], "count", f"worth {kes_text(b['matched']['kes'])}"),
            row("sales_without_payment", "Sales with no payment on the statement", gap_s["count"], "count"),
            row("sales_without_payment_kes", "Value of sales with no payment", gap_s["kes"], "kes"),
            row("payments_without_sale", "Payments with no sale recorded", gap_p["count"], "count"),
            row("payments_without_sale_kes", "Value of payments with no sale", gap_p["kes"], "kes")]
    if b["different_amounts"]:
        rows.append(row("different_amounts", "Sales paid a different amount from the one recorded", len(b["different_amounts"]), "count"))
    return make("what", "mpesa", q, state=b["state"], as_of=b.get("as_of"), headline=b["headline"], rows=rows,
                assumptions=from_setting(b.get("assumption")) + [assumption(b["note"])], next=["Anything to check at the till?"])


# ── things to check at the till ──────────────────────────────────────────────

def _things_to_check(ctx: OwnerContext, q: str) -> dict:
    b = ctx.safe("ask.fraud", lambda: areas._cancelled_sales(ctx))
    if b.get("state") in ("no_data", "unavailable"):
        return nothing("what", "things_to_check", q, b.get("reason") or "No sales recorded yet.", state=b["state"])
    rows = [row("cancelled", "Cancelled sales, last 7 days", b["cancelled_last_7_days"], "count"),
            row("unusual_cancelling", "Unusual cancelling", b["unusual_cancelling"], "count"),
            row("unusual_refunds", "Unusual refunds", b["unusual_refunds"], "count"),
            row("late_night", "Late-night activity", b["late_night_activity"], "count")]
    n = b["to_check"]
    head = (f"{n} thing{'s' if n != 1 else ''} to check at the till; {b['cancelled_last_7_days']} sales were cancelled in the last 7 days."
            if n else f"Nothing unusual at the till; {b['cancelled_last_7_days']} sales were cancelled in the last 7 days.")
    return make("what", "things_to_check", q, state=b["state"], as_of=b.get("as_of"), headline=head, rows=rows,
                assumptions=[assumption(b.get("note") or "These are things to check, not conclusions about anyone.")],
                next=["How is my cash count looking?"])


# ── suppliers ────────────────────────────────────────────────────────────────

def _suppliers(ctx: OwnerContext, q: str) -> dict:
    b = ctx.safe("ask.suppliers", lambda: areas._suppliers(ctx))
    if b.get("state") in ("no_data", "unavailable"):
        return nothing("what", "suppliers", q, b.get("reason") or "No supplier deliveries recorded yet.", state=b["state"])
    sup, short = b["suppliers"], b.get("short_deliveries") or []
    rows = [row("supplier", s["name"], s["on_time_pct"], "pct", f"{s['word']}; {s['closed_orders']} orders delivered") for s in sup]
    rows += [row("short", f"{s['supplier']} · {s['item']}", s["short_value"], "kes",
                 f"{s['received']:g} of {s['ordered']:g} {s['unit']} on {s['on']}") for s in short]
    if short:
        s = short[0]
        head = f"{s['supplier']} delivered {s['received']:g} of the {s['ordered']:g} {s['unit']} of {s['item']} you ordered: {kes_text(s['short_value'])} short."
    elif b.get("overdue_orders"):
        head = f"{b['overdue_orders']} order{'s are' if b['overdue_orders'] != 1 else ' is'} overdue."
    else:
        head = f"{len(sup)} supplier{'s' if len(sup) != 1 else ''} on record; no short or overdue deliveries."
    return make("what", "suppliers", q, state=b["state"], as_of=b.get("as_of"), headline=head, rows=rows,
                assumptions=[assumption("A supplier with fewer than 3 delivered orders shows as Learning, not a score.")],
                next=["What will run out soon?"])


# ── winning guests back ──────────────────────────────────────────────────────

def _win_back(ctx: OwnerContext, q: str) -> dict:
    b = ctx.safe("ask.win_back", lambda: areas._win_back(ctx))
    if b.get("state") in ("no_data", "unavailable") or not b.get("lapsed_guests"):
        return nothing("what", "win_back", q, b.get("reason") or "Nobody has gone quiet yet, or there are no guest contacts recorded.",
                       state=b["state"] if b.get("state") in ("no_data", "unavailable") else "no_data")
    rows = [row("lapsed", "Guests who haven't been back", b["lapsed_guests"], "count"), row("reachable", "Of them, with a phone number", b["reachable"], "count"),
            row("offers", "Offers ready", b["offers"], "count")]
    head = f"{b['lapsed_guests']} guests haven't been back for a while; {b['reachable']} of them have a phone number, and {b['offers']} offers are ready."
    return make("what", "win_back", q, state=b["state"], as_of=b.get("as_of"), headline=head, rows=rows,
                assumptions=[assumption("An offer is a draft for you to send; nothing is sent for you.")])


# ── what LEVIII saved you ────────────────────────────────────────────────────

def _savings(ctx: OwnerContext, q: str) -> dict:
    b = ctx.safe("ask.savings", lambda: areas._money_savings(ctx))
    if b.get("state") in ("no_data", "unavailable"):
        return nothing("what", "savings", q, b.get("reason") or "Nothing approved yet.", state=b["state"])
    rows = [row("captured", "Brought in by ideas you approved, a month", b["captured_kes_month"], "kes"),
            row("hours", "Hours saved, last 30 days", b["hours_saved_30d"], "hours"), row("approved", "Ideas you approved", b["approved_ideas"], "count")]
    head = (f"The {b['approved_ideas']} idea{'s' if b['approved_ideas'] != 1 else ''} you approved bring in about {kes_text(b['captured_kes_month'])} a month "
            f"and saved about {b['hours_saved_30d']:g} hours in the last 30 days.")
    return make("what", "savings", q, state=b["state"], as_of=b.get("as_of"), headline=head, rows=rows,
                assumptions=[assumption("These are estimates from the ideas you approved, not money counted in the till.")])


# ── how complete your costs are ──────────────────────────────────────────────

def _data_trust(ctx: OwnerContext, q: str) -> dict:
    b = ctx.safe("ask.data_trust", lambda: areas._data_trust(ctx))
    if b.get("state") in ("no_data", "unavailable"):
        return nothing("what", "data_trust", q, b.get("reason") or "No dishes recorded yet.", state=b["state"])
    rows = [row("dishes", "Dishes", b["dishes"], "count"), row("known", "Dishes whose cost is known", b["costs_known_pct"], "pct"),
            row("missing", "Dishes with no cost yet", b["missing_costs"], "count")]
    head = (f"The cost is known for {pct_text(b['costs_known_pct'])} of your {b['dishes']} dishes."
            + (f" {b['to_fix']} still need a cost before their profit can be trusted." if b.get("to_fix") else ""))
    return make("what", "data_trust", q, state=b["state"], as_of=b.get("as_of"), headline=head, rows=rows,
                assumptions=[assumption("A dish with no recipe cost is left out of food cost, so the real figure is higher.")])


# ── Profit & Loss, costs covered, bills ──────────────────────────────────────

def _money(ctx: OwnerContext, q: str) -> dict:
    pnl = ctx.safe("ask.money.pnl", lambda: areas.month_pnl(ctx))
    be = ctx.safe("ask.money.breakeven", lambda: areas.breakeven_summary(ctx))
    bills = ctx.safe("ask.money.bills", lambda: areas.bills_block(ctx))
    spikes = ctx.safe("ask.money.spikes", lambda: areas.spikes_block(ctx))
    if _empty([pnl, be, bills]):
        return nothing("what", "money", q, _reason([pnl, be, bills], "No sales or costs recorded yet."), state=pnl["state"])
    rows, parts = [], []
    if pnl.get("state") not in ("no_data", "unavailable"):
        lines = {l["key"]: l for l in pnl["lines"]}
        for l in pnl["lines"]:
            rows.append(row(l["key"], l["label"], l["kes"], "kes"))
        kept, sales = lines.get("kept"), lines.get("sales")
        if kept and sales:
            rows.append(row("kept_pct", "What you kept, out of every KES 100 sold", pnl["ratios"]["kept_pct"], "pct"))
            parts.append(f"{pnl['period']['label']}: you sold {kes_text(sales['kes'])} and kept {kes_text(kept['kes'])} ({pct_text(pnl['ratios']['kept_pct'])}).")
    if be.get("state") not in ("no_data", "unavailable"):
        rows.append(row("costs_covered", "Sales needed to cover today's costs", be["break_even_kes"], "kes",
                        f"covered at {be['crossed_at']}" if be.get("covered") and be.get("crossed_at") else f"{kes_text(be['to_go_kes'])} still to go"))
        parts.append("Today's costs are covered." if be.get("covered") else f"{kes_text(be['to_go_kes'])} of sales still to go to cover today's costs.")
    upcoming = (bills.get("upcoming") or []) if bills.get("state") not in ("no_data", "unavailable") else []
    for b in upcoming[:3]:
        rows.append(row("bill", b["name"], b["amount_kes"], "kes", f"due {b['due_on']}, in {b['days_away']} days" + ("; your sales will not cover it" if b["short"] else "")))
    if upcoming:
        n = upcoming[0]
        parts.append(f"Next bill: {n['name']}, {kes_text(n['amount_kes'])} on {day_text(date.fromisoformat(n['due_on']))}"
                     + (" — your sales will not cover it." if n["short"] else "."))
    for s in ((spikes.get("spikes") or []) if spikes.get("state") not in ("no_data", "unavailable") else [])[:2]:
        rows.append(row("spike", s["name"], s["extra_kes"], "kes", f"{pct_text(s['up_pct'])} above usual"))
    state, as_of = _state_of(pnl, be, bills)
    assumptions = from_setting(pnl.get("assumption")) + from_setting(bills.get("assumption"))
    return make("what", "money", q, state=state, as_of=as_of, headline=" ".join(parts) or "Nothing recorded yet.", rows=rows, assumptions=assumptions,
                next=["Which bills are due soon?", "Compare this month with last month"])


# ── the table ────────────────────────────────────────────────────────────────

AREA_TOPICS: dict[str, Callable[[OwnerContext, str], dict]] = {
    "cash": _cash, "mpesa": _mpesa, "things_to_check": _things_to_check, "suppliers": _suppliers, "win_back": _win_back,
    "savings": _savings, "data_trust": _data_trust, "money": _money,
}


def build(ctx: OwnerContext, question: str, topic: str) -> dict:
    if topic in AREA_TOPICS:
        return AREA_TOPICS[topic](ctx, question)
    return legacy(ctx, question, topic)
