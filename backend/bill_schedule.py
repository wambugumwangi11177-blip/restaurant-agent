"""Due dates and reminders for approved running costs."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

RESTAURANT_TZ = ZoneInfo("Africa/Nairobi")
DEFAULT_REMIND_DAYS = 3


def business_today() -> date:
    return datetime.now(RESTAURANT_TZ).date()


def compute_next_due(from_day: date, cadence: str, due_day: int | None) -> date:
    due_day = max(1, min(31, due_day or 1))
    if cadence == "weekly":
        return from_day + timedelta(days=7)
    if cadence == "yearly":
        target_year = from_day.year + 1
        day = min(due_day, monthrange(target_year, from_day.month)[1])
        return date(target_year, from_day.month, day)
    year, month = from_day.year, from_day.month
    day = min(due_day, monthrange(year, month)[1])
    candidate = date(year, month, day)
    if candidate > from_day:
        return candidate
    month += 1
    if month > 12:
        month = 1
        year += 1
    day = min(due_day, monthrange(year, month)[1])
    return date(year, month, day)


def reminder_bucket(next_due_on: date | None, payment_state: str, status: str, today: date, remind_days: int) -> str | None:
    if status != "approved" or next_due_on is None:
        return None
    if payment_state == "paid":
        if today < next_due_on - timedelta(days=remind_days):
            return None
        payment_state = "unpaid"
    if payment_state != "unpaid":
        return None
    days_left = (next_due_on - today).days
    if days_left < 0:
        return "overdue"
    if days_left <= remind_days:
        return "due_soon"
    return None