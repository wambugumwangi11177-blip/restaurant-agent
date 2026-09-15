"""Canonical reporting periods shared by every external-source calculation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

NAIROBI = ZoneInfo("Africa/Nairobi")


@dataclass(frozen=True)
class ReportPeriod:
    kind: str
    start: datetime
    end: datetime
    timezone: str = "Africa/Nairobi"


def period_for(kind: str, anchor: date | None = None) -> ReportPeriod:
    """Calendar period with half-open [start, end) Nairobi boundaries.

    The caller explicitly chooses whether `anchor` is current or a closed
    historical date; this function never silently substitutes the last order
    date for today.
    """
    day = anchor or datetime.now(NAIROBI).date()
    if kind == "daily":
        start_day, end_day = day, day + timedelta(days=1)
    elif kind == "weekly":
        start_day = day - timedelta(days=day.weekday())  # Monday
        end_day = start_day + timedelta(days=7)
    elif kind == "monthly":
        start_day = day.replace(day=1)
        end_day = (start_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    elif kind == "yearly":
        start_day = day.replace(month=1, day=1)
        end_day = start_day.replace(year=start_day.year + 1)
    else:
        raise ValueError("kind must be daily, weekly, monthly, or yearly")
    return ReportPeriod(kind, datetime.combine(start_day, time.min, NAIROBI), datetime.combine(end_day, time.min, NAIROBI))
