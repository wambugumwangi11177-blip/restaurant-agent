"""
backend/owner/money/radar.py — the bill radar (docs/v2/SPEC.md S3.3, figure R4 "CashRunway", P10).

"Daily projected cash = forecast sales − bills due, 30 days." Each day adds what the forecast says will be sold, after the
ingredients and wages it takes to sell it, and takes off the bills that fall due that day. It starts from the cash the owner
says they keep aside for bills (a setting; KES 0 until they say) — the system does not know the bank balance and does not
pretend to. A dip below zero is a shortfall: "you'll be KES 22,000 short on the 4th".

  forecast       ai.simulation.twin (the calendar-aware revenue projection the whole product already uses); today is the
                 larger of what has been sold so far and this weekday's usual
  left per day   forecast × (1 − ingredients share) − wages per day, from the reference month (owner/money/breakeven.py)
  bills          active recurring bills by their due rule, minus occurrences already paid (an expense linked to the bill
                 within half a period of the due date)

Honest limits: costs that are neither ingredients, wages nor a recurring bill (gas, repairs …) are not in the radar. If a
salaries bill exists it IS the wages, so wages per day is not also subtracted. Read-only; integer cents.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

import models
from owner.money import bills as bill_rules
from owner.money.breakeven import reference_pnl
from owner.money.pnl import nairobi_utc_range
from owner.settings import Settings, resolve

HORIZON_DAYS = 30


def _share(cents: int, keep_pct: Decimal) -> int:
    return int((Decimal(cents) * keep_pct / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def forecast_sales(db: Session, restaurant_id: int, today: date, horizon: int = HORIZON_DAYS) -> dict[date, int] | None:
    """Expected paid sales per day, in cents, for today and the days after it; None when there is not enough history to forecast."""
    from ai.revenue_forecaster import get_revenue_forecast
    from ai.simulation.twin import forecast_twin
    twin = forecast_twin(db, restaurant_id, horizon)
    if not twin.get("available"):
        return None
    out = {date.fromisoformat(row["date"]): int(row["projected_cents"]) for row in twin["daily"]}
    base = get_revenue_forecast(db, restaurant_id)
    usual = {p["day"]: int(p["avg_revenue"]) for p in base.get("weekly_pattern", [])} if isinstance(base, dict) else {}
    lo, hi = nairobi_utc_range(today, today)
    sold = sum(int(t or 0) for (t,) in db.query(models.Order.total).filter(
        models.Order.restaurant_id == restaurant_id, models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= lo, models.Order.created_at < hi))
    out[today] = max(sold, usual.get(today.strftime("%A"), 0))
    return out


def bill_radar(db: Session, restaurant_id: int, today: date, settings: Settings | None = None, *, forecast: Optional[dict[date, int]] = None,
               opening_cents: Optional[int] = None, horizon: int = HORIZON_DAYS) -> dict:
    """The next `horizon` days: sales left after ingredients and wages, bills falling due, and the running cash. Integer cents."""
    settings = resolve(db, restaurant_id, settings)
    opening = settings.bill_reserve_cents if opening_cents is None else opening_cents
    end = today + timedelta(days=horizon - 1)
    bills = db.query(models.RecurringBill).filter(models.RecurringBill.restaurant_id == restaurant_id, models.RecurringBill.is_active.is_(True)).all()
    if not bills:
        return {"available": False, "reason": "no_bills"}
    if forecast is None:
        forecast = forecast_sales(db, restaurant_id, today, horizon)
    if forecast is None:
        return {"available": False, "reason": "no_forecast"}

    ref = reference_pnl(db, restaurant_id, today, settings)
    assumed_food_cost = ref is None or ref[0]["food_cost_pct"] is None
    food_cost_pct = settings.food_cost_target_pct if assumed_food_cost else ref[0]["food_cost_pct"]
    keep_pct = Decimal(100) - Decimal(str(food_cost_pct))
    salaries_are_a_bill = any(b.category.pnl_line == "staff" for b in bills)
    wages_per_day = 0
    if ref is not None and not salaries_are_a_bill:
        p, kind, _label = ref
        wages_per_day = int((Decimal(p["labour_cents"]) / (p["period"]["days"] if kind == "last_month" else max(p["period"]["days_elapsed"], 1))
                             ).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    # which occurrences are already paid
    paid_rows = db.query(models.Expense.bill_id, models.Expense.paid_on).filter(
        models.Expense.restaurant_id == restaurant_id, models.Expense.voided_at.is_(None), models.Expense.bill_id.isnot(None),
        models.Expense.paid_on >= today - timedelta(days=120)).all()
    paid_on: dict[int, list[date]] = {}
    for bill_id, d in paid_rows:
        paid_on.setdefault(bill_id, []).append(d)
    due_by_day: dict[date, list[dict]] = {}
    for b in bills:
        window = bill_rules.PAID_WINDOW_DAYS[b.frequency]
        for due in bill_rules.due_dates(b, today, end):
            if any(due - timedelta(days=window) <= d <= due + timedelta(days=3) for d in paid_on.get(b.id, [])):
                continue
            due_by_day.setdefault(due, []).append({"bill_id": b.id, "name": b.name, "amount_cents": b.amount_cents, "category": b.category.name})

    days, balance, lowest = [], opening, None
    shortfalls: list[dict] = []
    upcoming: list[dict] = []
    for i in range(horizon):
        d = today + timedelta(days=i)
        sales = forecast.get(d, 0)
        left = _share(sales, keep_pct) - wages_per_day
        due = due_by_day.get(d, [])
        due_total = sum(x["amount_cents"] for x in due)
        balance += left - due_total
        days.append({"date": d.isoformat(), "expected_sales_cents": sales, "left_after_costs_cents": left, "bills": due,
                     "bills_cents": due_total, "balance_cents": balance})
        if lowest is None or balance < lowest["balance_cents"]:
            lowest = {"date": d.isoformat(), "balance_cents": balance}
        for x in due:
            upcoming.append({**x, "due_on": d.isoformat(), "days_away": i, "balance_after_cents": balance})
        if due and balance < 0:
            shortfalls.append({"date": d.isoformat(), "short_by_cents": -balance, "bills": [x["name"] for x in due], "bills_cents": due_total})
    return {"available": True, "opening_cents": opening, "horizon_days": horizon, "days": days, "upcoming": upcoming, "shortfalls": shortfalls,
            "lowest": lowest, "wages_per_day_cents": wages_per_day, "food_cost_pct": food_cost_pct, "food_cost_assumed": assumed_food_cost,
            "salaries_are_a_bill": salaries_are_a_bill}
