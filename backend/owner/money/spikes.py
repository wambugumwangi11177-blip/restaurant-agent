"""
backend/owner/money/spikes.py — "Costs going up" (docs/v2/SPEC.md S3.3, §7 #14, figure 6.1 P9).

A cost line is flagged when this month's spend so far is already `expense_spike_pct` (the owner's setting, default 25%) above
what that line averaged over the three complete months before — 18,600 against (14,600 + 14,100 + 14,300) ÷ 3 = 14,333 is +29.8%.
Month-to-date against a whole-month average is deliberately early and one-sided: a partial month that is already over the usual
can only end higher, so it is worth saying now; a partial month under the usual is simply not finished.

Needs the line to have been entered in each of the three previous months (anything less is a guess), and says how far along it
is until there are three months of costs.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from owner.money.pnl import period_range
from owner.settings import Settings, resolve

PRIOR_MONTHS = 3
LEARNING_DAYS = 90


def expense_spike_pct(this_cents: int, prior_cents: Sequence[int]) -> float | None:
    """This month's amount as a percentage above the average of the prior months', half-up to one decimal; None without a usual."""
    if not prior_cents:
        return None
    average = Decimal(sum(prior_cents)) / len(prior_cents)
    if average <= 0:
        return None
    return float(((Decimal(this_cents) / average - 1) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _month_starts(today: date) -> list[date]:
    """The first day of each of the three complete months before today's month, oldest first."""
    first = today.replace(day=1)
    out = []
    for _ in range(PRIOR_MONTHS):
        first = (first - timedelta(days=1)).replace(day=1)
        out.append(first)
    return list(reversed(out))


def expense_spikes(db: Session, restaurant_id: int, today: date, settings: Settings | None = None) -> dict:
    """{'spikes': [...worst first], 'eligible': n lines with a usual, 'history_days': days since the first cost was entered, 'months': [...]}."""
    settings = resolve(db, restaurant_id, settings)
    prior = _month_starts(today)
    this_start = today.replace(day=1)
    first_entry = db.query(func.min(models.Expense.paid_on)).filter(models.Expense.restaurant_id == restaurant_id, models.Expense.voided_at.is_(None)).scalar()
    rows = db.query(models.Expense.category_id, models.Expense.paid_on, models.Expense.amount_cents).filter(
        models.Expense.restaurant_id == restaurant_id, models.Expense.voided_at.is_(None),
        models.Expense.paid_on >= prior[0], models.Expense.paid_on <= today).all()
    per: dict[int, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    for category_id, paid_on, cents in rows:
        per[category_id][paid_on.replace(day=1)] += int(cents)
    names = {c.id: c for c in db.query(models.ExpenseCategory).filter(models.ExpenseCategory.restaurant_id == restaurant_id)}
    spikes, eligible = [], 0
    for category_id, by_month in per.items():
        history = [by_month.get(m, 0) for m in prior]
        if any(h <= 0 for h in history):
            continue                                                  # not entered in every one of the three months: no usual to compare with
        eligible += 1
        this_cents = by_month.get(this_start, 0)
        pct = expense_spike_pct(this_cents, history)
        if pct is not None and pct >= settings.expense_spike_pct:
            usual = round(sum(history) / PRIOR_MONTHS)
            cat = names.get(category_id)
            spikes.append({"key": cat.key if cat else str(category_id), "name": cat.name if cat else "", "this_month_cents": this_cents,
                           "usual_cents": usual, "pct": pct, "extra_cents": this_cents - usual})
    spikes.sort(key=lambda s: s["extra_cents"], reverse=True)
    return {"spikes": spikes, "eligible": eligible, "history_days": None if first_entry is None else (today - first_entry).days + 1,
            "months": [m.isoformat() for m in prior], "threshold_pct": settings.expense_spike_pct}
