"""
backend/owner/reports.py — GET /owner/report/{period} (docs/v2/SPEC.md §4 P5.2): daily (control), weekly
(performance), monthly (full P&L + export), yearly (trends).

S1.4 carries today's report content (sales, orders, average order, top dishes) in the new shape; every other
section the plan names is listed with `state: unavailable` and `planned: true` until its sprint lands, so the
shape the owner shell binds to is final and E5 can see exactly which sections exist.
"""
from __future__ import annotations

from datetime import date

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


def _window(period: str, month: date | None):
    """The report's window as naive UTC: the period as it is today, or — for a monthly report of a chosen `month` — that calendar
    month in Nairobi days (up to now, if it is the current one)."""
    _overview, reports = _routers()
    if month is None:
        return reports._range(period)
    from owner.money.pnl import nairobi_utc_range, period_range
    from time_utils import utcnow
    lo, hi = nairobi_utc_range(*period_range("month", month))
    return lo, min(hi, utcnow())


def _sales(ctx: OwnerContext, period: str, month: date | None = None) -> dict:
    overview, _reports = _routers()
    start, end = _window(period, month)
    core = overview._summarize(ctx.db, ctx.rid, start, end)
    base = ctx.order_state()
    if not core["orders"]:
        return no_data("No sales recorded in this period.", sales=0.0, orders=0)
    return {**base, "sales": core["revenue"], "orders": core["orders"], "average_order": round(core["revenue"] / core["orders"], 2),
            "basis": "Paid orders that were not cancelled, by the time they were taken. Not a payment cash-flow report."}


def _top_dishes(ctx: OwnerContext, period: str, month: date | None = None) -> dict:
    _overview, reports = _routers()
    start, end = _window(period, month)
    top = reports._top_items(ctx.db, ctx.rid, start, end)
    if not top:
        return no_data("No dishes sold in this period.", dishes=[])
    return {**ctx.order_state(), "dishes": [{"name": t["name"], "sold": t["qty"], "sales": t["sales_kes"]} for t in top]}


def _pnl(ctx: OwnerContext, period: str, month: date | None = None) -> dict:
    """The Profit & Loss for the calendar month so far, or for the chosen `month` (S3.2, S3.4). The yearly report's
    "Profit & Loss by month" is S5.2."""
    from owner.areas import month_pnl
    return month_pnl(ctx, month)


# section key -> (builder, the report periods it exists for; None = every period). The rest of PLAN is `planned`.
BUILDERS = {"sales": (_sales, None), "top_dishes": (_top_dishes, None), "pnl": (_pnl, ("monthly",))}


def _exists(key: str, period: str) -> bool:
    return key in BUILDERS and (BUILDERS[key][1] is None or period in BUILDERS[key][1])


def built_sections() -> set[str]:
    """`period.section` keys that exist today (used by E5 and the registry); the rest of PLAN is `planned`."""
    return {f"{period}.{key}" for period, plan in PLAN.items() for key, _title in plan if _exists(key, period)}


def planned_sections() -> set[str]:
    return {f"{period}.{key}" for period, plan in PLAN.items() for key, _title in plan} - built_sections()


def compose_report(ctx: OwnerContext, period: str, month: date | None = None) -> dict:
    """`month` (the first day of a month) turns the monthly report into that month's: its P&L, sales and best sellers all cover
    the same calendar month, so the accountant's export and the report show the same figures."""
    if period not in PERIODS:
        raise ValueError(f"period must be one of {PERIODS}")
    if month is not None and period != "monthly":
        raise ValueError("a month can only be chosen for the monthly report")
    _overview, reports = _routers()
    sections = []
    for key, title in PLAN[period]:
        if _exists(key, period):
            body = ctx.safe(f"report.{key}", lambda k=key: BUILDERS[k][0](ctx, period, month))
        else:
            body = unavailable("This section is not available yet.", planned=True)
        sections.append({"key": key, "title": title, **body})
    live = [s for s in sections if s["state"] in ("live", "stale", "learning", "as_entered")]
    from owner.money.view import period_label
    label = reports._label(period) if month is None else period_label("month", month, month, False)
    return {"period": period, "range": label, **({"month": month.strftime("%Y-%m")} if month else {}), "state": live[0]["state"] if live else "no_data",
            "as_of": next((s.get("as_of") for s in live if s.get("as_of")), None), "sections": sections,
            "read": unavailable("LEVIII's read is optional and is left out unless every number in it is backed.", text=None)}
