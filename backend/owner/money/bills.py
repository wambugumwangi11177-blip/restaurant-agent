"""
backend/owner/money/bills.py — when a recurring bill next falls due.

  monthly  `due_day` is the day of the month; a short month clamps (day 31 in April is the 30th, in February the 28th/29th)
  weekly   `due_day` is the weekday, Monday = 0
  yearly   `due_month` + `due_day`; 29 February clamps to the 28th in a common year

A bill is not due before `start_on` or after `end_on`; due today still counts as "next". Pure functions, no database.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta


def _clamp(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_due(bill, today: date) -> date | None:
    """The next date on or after `today` (and on or after the bill's start) when `bill` falls due, or None if it has ended."""
    frm = max(today, bill.start_on)
    if bill.frequency == "weekly":
        due = frm + timedelta(days=(bill.due_day - frm.weekday()) % 7)
    elif bill.frequency == "monthly":
        due = _clamp(frm.year, frm.month, bill.due_day)
        if due < frm:
            year, month = (frm.year + 1, 1) if frm.month == 12 else (frm.year, frm.month + 1)
            due = _clamp(year, month, bill.due_day)
    elif bill.frequency == "yearly":
        due = _clamp(frm.year, bill.due_month, bill.due_day)
        if due < frm:
            due = _clamp(frm.year + 1, bill.due_month, bill.due_day)
    else:
        raise ValueError(f"unknown frequency {bill.frequency!r}")
    if bill.end_on is not None and due > bill.end_on:
        return None
    return due


def check_rule(frequency: str, due_day: int, due_month: int | None) -> None:
    """Raise ValueError unless the due rule makes sense for the frequency."""
    if frequency not in ("monthly", "weekly", "yearly"):
        raise ValueError("frequency must be monthly, weekly or yearly")
    if frequency == "monthly" and not (1 <= due_day <= 31):
        raise ValueError("a monthly bill falls due on a day from 1 to 31")
    if frequency == "weekly" and not (0 <= due_day <= 6):
        raise ValueError("a weekly bill falls due on a weekday from 0 (Monday) to 6 (Sunday)")
    if frequency == "yearly":
        if due_month is None or not (1 <= due_month <= 12):
            raise ValueError("a yearly bill needs the month it falls due (1 to 12)")
        if not (1 <= due_day <= 31):
            raise ValueError("a yearly bill falls due on a day from 1 to 31")
    elif due_month is not None:
        raise ValueError("a month only makes sense for a yearly bill")
