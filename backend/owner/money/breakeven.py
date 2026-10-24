"""
backend/owner/money/breakeven.py — "Costs covered" (docs/v2/SPEC.md S3.3, §7 #9, figure R3).

    break-even sales for a day  =  fixed costs per day  ÷  (1 − food cost %)          8,000 ÷ 0.68 = KES 11,765

Fixed costs are the lines the owner marked fixed (rent, KPLC, security, licences, salaries …) plus the shifts' wages when no
payroll was entered; the food cost share is the ingredients' share of sales. Both come from one reference month: the last
complete calendar month that has costs and sales, else the month so far — said plainly on the screen. It does not need recipes
for the unit economics (it uses the month's own ingredient share), and it knows nothing about other variable costs
(gas, packaging, commissions): they make the true break-even a little higher, which the note says.

`todays_progress` walks today's paid orders in time order: the moment the running total reaches the break-even is "Costs covered
3:40 pm"; before that, "KES x to go". Integer cents; read-only.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

import models
from owner.money.pnl import compute_pnl, nairobi_utc_range, period_range
from owner.money.view import MONTHS
from owner.settings import Settings, resolve


def break_even_sales_cents(fixed_per_day_cents: int, food_cost_pct: float | None) -> int | None:
    """Sales needed in a day for the contribution after ingredients to cover that day's fixed costs, in cents, half-up.
    None when ingredients eat the whole sale (a food cost of 100% or more) or the share is unknown."""
    if fixed_per_day_cents < 0:
        raise ValueError("fixed costs cannot be negative")
    if food_cost_pct is None or food_cost_pct >= 100:
        return None
    keep = (Decimal(100) - Decimal(str(food_cost_pct))) / 100
    return int((Decimal(fixed_per_day_cents) / keep).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _half_up(numerator: int, denominator: int) -> int:
    return int((Decimal(numerator) / Decimal(denominator)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def reference_pnl(db: Session, restaurant_id: int, today: date, settings: Settings) -> tuple[dict, str, str] | None:
    """(P&L, 'last_month' | 'month_so_far', label) the break-even is built from, or None if there is nothing to build it from."""
    first_of_month = today.replace(day=1)
    prev_start, prev_end = period_range("month", first_of_month - timedelta(days=1))
    prev = compute_pnl(db, restaurant_id, prev_start, prev_end, settings, today=today)
    if prev["sales_cents"] and (prev["costs_entered"] or prev["labour_cents"]):
        return prev, "last_month", f"{MONTHS[prev_start.month - 1]} {prev_start.year}"
    start, end = period_range("month", today)
    cur = compute_pnl(db, restaurant_id, start, end, settings, today=today)
    if cur["sales_cents"] and (cur["costs_entered"] or cur["labour_cents"]):
        return cur, "month_so_far", f"{MONTHS[start.month - 1]} {start.year} so far"
    return None


def break_even(db: Session, restaurant_id: int, today: date, settings: Settings | None = None) -> dict | None:
    """The day's break-even and what it is built from; None when there are no costs (or no sales) to build it from."""
    settings = resolve(db, restaurant_id, settings)
    ref = reference_pnl(db, restaurant_id, today, settings)
    if ref is None:
        return None
    p, kind, label = ref
    days = p["period"]["days"] if kind == "last_month" else max(p["period"]["days_elapsed"], 1)
    if not p["fixed_costs_cents"]:
        return None
    per_day = _half_up(p["fixed_costs_cents"], days)
    target = break_even_sales_cents(per_day, p["food_cost_pct"])
    if target is None:
        return None
    return {"break_even_cents": target, "fixed_per_day_cents": per_day, "food_cost_pct": p["food_cost_pct"],
            "basis": {"kind": kind, "label": label, "days": days, "fixed_costs_cents": p["fixed_costs_cents"], "labour_basis": p["labour_basis"],
                      "fixed_lines": [{"key": l["key"], "name": l["name"], "amount_cents": l["amount_cents"]}
                                      for sec in p["sections"] for l in sec["lines"] if l["is_fixed"]],
                      "labour_fixed_cents": p["labour_fixed_cents"]}}


def todays_progress(db: Session, restaurant_id: int, break_even_cents: int, today: date, moment: datetime | None = None) -> dict:
    """Today's paid sales against the break-even: the running total, when it crossed (a naive-UTC datetime) or what is still to go.

    When `moment` is the open trading day, the window is that service through the moment (rolls at 06:00).
    A completed day, or a call with no moment, stays the full Nairobi calendar day.
    """
    if moment is not None:
        from time_utils import trading_day, trading_window
        if trading_day(moment) == today:
            lo, hi, _day = trading_window("today", moment)
        else:
            lo, hi = nairobi_utc_range(today, today)
    else:
        lo, hi = nairobi_utc_range(today, today)
    rows = db.query(models.Order.created_at, models.Order.total).filter(
        models.Order.restaurant_id == restaurant_id, models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= lo, models.Order.created_at < hi).order_by(models.Order.created_at, models.Order.id).all()
    running, crossed_at = 0, None
    points = [{"at": lo, "sales_cents": 0}]
    for created_at, total in rows:
        running += int(total or 0)
        if crossed_at is None and running >= break_even_cents:
            crossed_at = created_at
        points.append({"at": created_at, "sales_cents": running})
    if len(points) > 24:
        step = max(1, len(points) // 24)
        sampled = points[::step]
        if sampled[-1] is not points[-1]:
            sampled.append(points[-1])
        if crossed_at is not None and not any(p["at"] == crossed_at for p in sampled):
            sampled.append(next(p for p in points if p["at"] == crossed_at))
            sampled.sort(key=lambda p: (p["at"], p["sales_cents"]))
        points = sampled
    return {"sales_so_far_cents": running, "crossed_at": crossed_at, "to_go_cents": max(break_even_cents - running, 0), "points": points}
