"""
backend/owner/answer_compare.py — the "compare" form: my branches side by side, or a period against the one before it
(docs/v2/SPEC.md §4 P5.1, scenario P14: "Branch B food cost 37% vs A 29%").

BRANCHES: every restaurant of the owner's own tenant (never another tenant's), each worked out by the same engines Home uses for it —
the food-cost figure is the very number on that branch's Home. The gap is also put in KES a month: what the higher branch would keep if
it spent what the lower one spends on ingredients, at the higher branch's last 30 days of sales. That is an estimate and says so.

PERIODS: this week against last week, or this month against last month, LIKE FOR LIKE: only days that are over, and the same number
of days from each. On the first day of a week or month nothing of it is over, so the answer says so and compares the two before it.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import models
from owner import areas
from owner.answers import assumption, kes_text, make, nothing, pct_text, row
from owner.money.pnl import compute_pnl, nairobi_utc_range, period_range
from owner.states import OwnerContext
from routers.deps import list_restaurants_for_tenant
from time_utils import eat_date

_GENERIC = {"restaurant", "branch", "demo", "cafe", "hotel", "grill", "bar", "kitchen", "the", "and"}


def wants_branches(question: str, names: list[str]) -> bool:
    q = question.lower()
    if re.search(r"\b(branch|branches|outlet|outlets|location|locations|site|sites)\b", q):
        return True
    for name in names:
        for token in re.findall(r"[a-z]{4,}", name.lower()):
            if token not in _GENERIC and token in q:
                return True
    return False


# ── branches ─────────────────────────────────────────────────────────────────

def _branch(ctx: OwnerContext, restaurant: models.Restaurant) -> dict:
    c = ctx if restaurant.id == ctx.rid else OwnerContext(ctx.db, ctx.user, restaurant)
    c.now = ctx.now
    dials = c.safe("compare.dials", lambda: areas._money_cost_dials(c))
    overview = areas._overview_core(c)
    core = overview._summarize(c.db, c.rid, ctx.now - timedelta(days=30), ctx.now)
    has = dials.get("state") in ("live", "stale", "learning")
    return {"name": restaurant.name, "sales": dials.get("sales_kes", core["revenue"]), "orders": dials.get("orders",core["orders"]),
            "food_cost_pct": dials["food_cost_pct"] if has else None, "wages_pct": dials.get("wages_pct") if has else None,
            "food_cost_word": dials.get("food_cost_word") if has else None, "state": dials.get("state")}


def _branches(ctx: OwnerContext, question: str) -> dict:
    restaurants = list_restaurants_for_tenant(ctx.db, ctx.user)
    follow = ["This week vs last week", "This month vs last month"]
    if len(restaurants) < 2:
        return nothing("compare", "compare", question, "You have one branch, so there is nothing to compare it with. I can compare this week with last week instead.",
                       next=follow, kind="branches", columns=[])
    cols = [_branch(ctx, r) for r in restaurants]
    known = [c for c in cols if c["food_cost_pct"] is not None]
    state = ctx.order_state()
    if len(known) < 2:
        return nothing("compare", "compare", question, "Not enough sales and dish costs are recorded at two branches yet to compare them.",
                       next=follow, kind="branches", columns=cols)
    hi, lo = max(known, key=lambda c: c["food_cost_pct"]), min(known, key=lambda c: c["food_cost_pct"])
    gap = round(hi["food_cost_pct"] - lo["food_cost_pct"], 1)
    gap_kes = round(gap / 100.0 * hi["sales"], 2)
    rows = [row("food_cost_pct", "Out of every KES 100, ingredients", hi["food_cost_pct"], "pct", f"{hi['name']} (the higher); {lo['name']} {pct_text(lo['food_cost_pct'])}"),
            row("food_cost_gap", "Difference", gap, "pct_points", f"{hi['name']} spends more of each sale on ingredients"),
            row("gap_kes_month", f"What {hi['name']} would keep a month at {lo['name']}'s ingredient cost", gap_kes, "kes",
                f"{pct_text(gap)} of its last 30 days of sales ({kes_text(hi['sales'])})")]
    head = (f"{hi['name']} spends {pct_text(hi['food_cost_pct'])} of every sale on ingredients; {lo['name']} spends {pct_text(lo['food_cost_pct'])}. "
            f"That is {gap:g} points more, about {kes_text(gap_kes)} a month at {hi['name']}'s sales.")
    assumptions = [assumption("Both are the last 30 days, worked out the same way as on each branch's Home."),
                   assumption(f"The monthly figure is an estimate: it assumes {hi['name']} could spend what {lo['name']} spends and sell the same.")]
    return make("compare", "compare", question, state=state["state"], as_of=state.get("as_of"), headline=head, rows=rows, assumptions=assumptions,
                next=follow, kind="branches", columns=cols)


# ── periods ──────────────────────────────────────────────────────────────────

def _window(ctx: OwnerContext, start: date, days: int) -> dict:
    end = start + timedelta(days=days - 1)
    p = compute_pnl(ctx.db, ctx.rid, start, end, ctx.settings, today=eat_date(ctx.now))
    sales, orders = p["sales_cents"] / 100.0, p["orders"]
    return {"from": start.isoformat(), "to": end.isoformat(), "days": days, "sales": sales, "orders": orders,
            "average_order": round(sales / orders, 2) if orders else None, "food_cost_pct": p["food_cost_pct"]}


def _periods(ctx: OwnerContext, question: str) -> dict:
    q = question.lower()
    today = eat_date(ctx.now)
    month = bool(re.search(r"\bmonth", q)) and not re.search(r"\bweek", q)
    follow = ["Compare my branches", "What should I do to make more money?"]
    if month:
        first, unit = today.replace(day=1), "month"
        prev_last = first - timedelta(days=1)
        prev_first = prev_last.replace(day=1)
        finished = today.day - 1
        if finished >= 1:
            days = min(finished, prev_last.day)
            this_start, last_start, this_label, last_label = first, prev_first, "This month so far", "Last month"
        else:
            before_first = (prev_first - timedelta(days=1)).replace(day=1)
            days = min(prev_last.day, (prev_first - timedelta(days=1)).day)
            this_start, last_start, this_label, last_label = prev_first, before_first, "Last month", "The month before"
    else:
        monday, unit = period_range("week", today)[0], "week"
        finished = (today - monday).days
        if finished >= 1:
            days, this_start, last_start, this_label, last_label = finished, monday, monday - timedelta(days=7), "This week so far", "Last week"
        else:
            days, this_start, last_start, this_label, last_label = 7, monday - timedelta(days=7), monday - timedelta(days=14), "Last week", "The week before"
    this, last = _window(ctx, this_start, days), _window(ctx, last_start, days)
    this.update(key="this", label=this_label)
    last.update(key="last", label=last_label)
    state = ctx.order_state()
    if not this["orders"] and not last["orders"]:
        return nothing("compare", "compare", question, f"No sales are recorded in either {unit} to compare.", next=follow, kind="periods", columns=[this, last])
    change = ((this["sales"] - last["sales"]) / last["sales"] * 100.0) if last["sales"] else None
    rows = [row("sales", "Sales", this["sales"], "kes", f"{last_label}: {kes_text(last['sales'])}"),
            row("orders", "Orders", this["orders"], "count", f"{last_label}: {last['orders']}")]
    if change is not None:
        rows.append(row("sales_change_pct", "Sales compared with " + last_label.lower(), abs(change), "pct", "up" if change >= 0 else "down"))
    if this["food_cost_pct"] is not None and last["food_cost_pct"] is not None:
        rows.append(row("food_cost_pct", "Out of every KES 100, ingredients", this["food_cost_pct"], "pct", f"{last_label}: {pct_text(last['food_cost_pct'])}"))
    span = f"the first {days} day{'s' if days != 1 else ''}"
    if change is None:
        head = f"{this_label} you sold {kes_text(this['sales'])} in {span}; nothing was sold in the same days of {last_label.lower()}."
    else:
        head = (f"{this_label} you sold {kes_text(this['sales'])} in {span}, {pct_text(abs(change))} {'up' if change >= 0 else 'down'} on the same days of "
                f"{last_label.lower()} ({kes_text(last['sales'])}).")
    assumptions = [assumption(f"Only finished days are compared: {span} of {this_label.lower().replace(' so far', '')} and of {last_label.lower()}.")]
    if finished < 1:
        assumptions.append(assumption(f"This {unit} has no finished day yet, so this compares {this_label.lower()} with {last_label.lower()}."))
        head = "This " + unit + " has no finished day yet. " + head
    return make("compare", "compare", question, state=state["state"], as_of=state.get("as_of"), headline=head, rows=rows, assumptions=assumptions,
                next=follow, kind="periods", columns=[this, last])


def build(ctx: OwnerContext, question: str) -> dict:
    names = [r.name for r in list_restaurants_for_tenant(ctx.db, ctx.user)]
    if wants_branches(question, names):
        return _branches(ctx, question)
    return _periods(ctx, question)
