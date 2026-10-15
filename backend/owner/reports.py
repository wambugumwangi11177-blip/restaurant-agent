"""
backend/owner/reports.py — GET /owner/report/{period} (docs/v2/SPEC.md §4 P5.2): daily (control), weekly
(performance), monthly (full P&L + export), yearly (trends).

S1.4 carries today's report content (sales, orders, average order, top dishes) in the new shape; every other
section the plan names is listed with `state: unavailable` and `planned: true` until its sprint lands, so the
shape the owner shell binds to is final and E5 can see exactly which sections exist.
"""
from __future__ import annotations

from owner.states import OwnerContext, block, kes, no_data, unavailable

PERIODS = ("daily", "weekly", "monthly", "yearly")

# What each report is meant to contain. A key listed here but without a builder is `planned`.
PLAN: dict[str, list[tuple[str, str]]] = {
    "daily": [("sales", "Sales"), ("top_dishes", "Best sellers"), ("cash_check", "Cash count check"),
              ("things_to_check", "Things to check"), ("stock_today", "Stock today")],
    "weekly": [("sales", "Sales"), ("top_dishes", "Best sellers"), ("dishes", "Best and weakest dishes"), ("price_ideas", "Price ideas"),
               ("missing_stock", "Missing stock"), ("wages", "Wages"), ("cash_check", "Cash count check"),
               ("outlook", "Next week"), ("kitchen", "Kitchen speed"), ("bookings", "Bookings"), ("suppliers", "Suppliers")],
    "monthly": [("pnl", "Profit & Loss"), ("sales", "Sales"), ("top_dishes", "Best sellers"), ("costs", "Costs"), ("dishes", "Dishes"),
                ("channels", "Delivery apps and dine-in"), ("store", "Store & suppliers"), ("wages", "Wages"), ("cash_check", "Cash count check"),
                ("decisions", "What cost you money"), ("savings", "What LEVIII saved you"), ("marketing", "Winning guests back"),
                ("outlook", "Next 30 days"), ("data_trust", "How complete your costs are"),
                ("rules_used", "Targets used in this report"), ("read", "LEVIII's read")],
    "yearly": [("sales", "Sales"), ("trends", "Trends"), ("pnl", "Profit & Loss by month"), ("seasons", "Busy and quiet months")],
}


def _routers():
    from routers import overview, reports
    return overview, reports


def _sales(ctx: OwnerContext, period: str) -> dict:
    overview, reports = _routers()
    start, end = reports._range(period)
    core = overview._summarize(ctx.db, ctx.rid, start, end)
    base = ctx.order_state()
    if not core["orders"]:
        return no_data("No sales recorded in this period.", sales=0.0, orders=0)
    return {**base, "sales": core["revenue"], "orders": core["orders"], "average_order": round(core["revenue"] / core["orders"], 2),
            "basis": "Paid orders that were not cancelled, by the time they were taken. Not a payment cash-flow report."}


def _top_dishes(ctx: OwnerContext, period: str) -> dict:
    _overview, reports = _routers()
    start, end = reports._range(period)
    top = reports._top_items(ctx.db, ctx.rid, start, end)
    if not top:
        return no_data("No dishes sold in this period.", dishes=[])
    return {**ctx.order_state(), "dishes": [{"name": t["name"], "sold": t["qty"], "sales": t["sales_kes"]} for t in top]}


BUILDERS = {"sales": _sales, "top_dishes": _top_dishes}


def built_sections() -> set[str]:
    """`period.section` keys that exist today (used by E5 and the registry); the rest of PLAN is `planned`."""
    return {f"{period}.{key}" for period, plan in PLAN.items() for key, _title in plan if key in BUILDERS}


def planned_sections() -> set[str]:
    return {f"{period}.{key}" for period, plan in PLAN.items() for key, _title in plan} - built_sections()


def compose_report(ctx: OwnerContext, period: str) -> dict:
    if period not in PERIODS:
        raise ValueError(f"period must be one of {PERIODS}")
    _overview, reports = _routers()
    sections = []
    for key, title in PLAN[period]:
        if key in BUILDERS:
            body = ctx.safe(f"report.{key}", lambda k=key: BUILDERS[k](ctx, period))
        else:
            body = unavailable("This section is not available yet.", planned=True)
        sections.append({"key": key, "title": title, **body})
    live = [s for s in sections if s["state"] in ("live", "stale", "learning", "as_entered")]
    return {"period": period, "range": reports._label(period), "state": live[0]["state"] if live else "no_data",
            "as_of": next((s.get("as_of") for s in live if s.get("as_of")), None), "sections": sections,
            "read": unavailable("LEVIII's read is optional and is left out unless every number in it is backed.", text=None)}
