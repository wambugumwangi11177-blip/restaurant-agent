"""
backend/time_utils.py
─────────────────────
One source of truth for "now, in UTC".

`datetime.utcnow()` is deprecated (removal scheduled) and emitted 155 warnings
across this test suite. The obvious replacement — `datetime.now(timezone.utc)` —
is NOT a drop-in here, and swapping it in mechanically would have introduced a
runtime bug rather than fixed a warning:

`utcnow()` returns a NAIVE datetime (no tzinfo). `now(timezone.utc)` returns an
AWARE one. Every `DateTime` column in models.py is naive (none declare
`timezone=True`), so every value loaded back from the database is naive too. Python
raises `TypeError: can't subtract offset-naive and offset-aware datetimes` the
moment the two meet — and this codebase subtracts wall-clock now from DB-loaded
timestamps in at least a dozen places (`ai/analysis_clock.py`'s `datetime.utcnow()
- latest`, every `cutoff = datetime.utcnow() - timedelta(...)` in pricing,
marketing, evaluation, executive...). Those would have started failing in
production while the tests — which mostly construct their own naive fixtures —
kept passing.

So this helper preserves the existing naive-UTC contract exactly, and only removes
the deprecated call. Behaviour is byte-for-byte identical to `datetime.utcnow()`.

Migrating the whole codebase to timezone-aware datetimes is a real, separate change:
it means `DateTime(timezone=True)` columns, an Alembic migration per table, and an
audit of every naive comparison. Worth doing, not worth smuggling into a
deprecation cleanup. When that happens, this function is the single place that
flips, and `aware_utcnow()` below is what it flips to.

Zero project imports on purpose — `models.py` imports this, and models.py sits
near the bottom of the import graph.
"""

from datetime import date, datetime, time, timedelta, timezone

# Nairobi is UTC+3 all year (no daylight saving). The database stores naive UTC; the OWNER's day is the Nairobi day.
EAT_OFFSET = timedelta(hours=3)
# A service that runs past midnight is still "today" until 06:00 Nairobi. Ask, Home and the daily
# report share this so "sales today" and a why about that service name the same paid total.
SERVICE_ROLLOVER_HOUR = 6


def utcnow() -> datetime:
    """
    Current UTC time as a NAIVE datetime — the exact semantics of the deprecated
    `datetime.utcnow()`, which this replaces everywhere in the backend.

    Use for anything compared against, or written to, a `DateTime` column.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def trading_day(utc_naive: datetime | None = None) -> date:
    """The open Nairobi service date. One rule for every "today".

    Before 06:00 Nairobi the previous calendar day is still open: a Friday service
    that is being asked about at 01:30 Saturday is Friday, not an empty Saturday.
    """
    moment = utcnow() if utc_naive is None else utc_naive
    local = moment + EAT_OFFSET
    day = local.date()
    if local.hour < SERVICE_ROLLOVER_HOUR:
        day -= timedelta(days=1)
    return day


def service_day(utc_naive: datetime | None = None) -> date:
    """The Nairobi service date. Same value as trading_day."""
    return trading_day(utc_naive)


_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def service_caption(utc_naive: datetime | None = None) -> str:
    """The trading day the open-service figures belong to.

    Before 06:00 Nairobi the calendar date has moved on and the service has not,
    so the caption says so: "Fri 23 Oct service, still open". After the rollover
    the calendar and the service are the same day: "Sat 24 Oct service".
    """
    moment = utcnow() if utc_naive is None else utc_naive
    local = moment + EAT_OFFSET
    day = trading_day(moment)
    name = f"{_WEEKDAYS[day.weekday()]} {day.day} {_MONTHS[day.month - 1]} service"
    if local.date() != day:
        return f"{name}, still open"
    return name


def _period_key(period: str) -> str:
    return " ".join(period.strip().lower().replace("-", " ").replace("_", " ").split())


def period_label(period: str) -> str:
    """Owner words for the window trading_window computes. Every narrator figure uses this."""
    labels = {
        "today": "the open service day through now (Nairobi, rolls at 06:00)",
        "daily": "the open service day through now (Nairobi, rolls at 06:00)",
        "yesterday": "the full Nairobi day before the open service day",
        "1h": "the last hour",
        "7d": "the last 7 days through now",
        "weekly": "the last 7 days through now",
        "30d": "the last 30 days through now",
        "monthly": "the last 30 days through now",
        "yearly": "the last 365 days through now",
        "this week": "this week, Monday of the open service day through now (Nairobi, rolls at 06:00)",
        "week": "this week, Monday of the open service day through now (Nairobi, rolls at 06:00)",
        "last week": "last week, the previous Monday through this Monday (Nairobi)",
        "this month": "this month, from the 1st of the open service day's month through now (Nairobi, rolls at 06:00)",
        "month": "this month, from the 1st of the open service day's month through now (Nairobi, rolls at 06:00)",
        "last month": "last month, the full calendar month before the open service day (Nairobi)",
    }
    try:
        return labels[_period_key(period)]
    except KeyError:
        raise ValueError(f"unknown trading period {period!r}") from None


def trading_window(period: str, utc_naive: datetime | None = None) -> tuple[datetime, datetime, date]:
    """Naive-UTC sales window for a period, anchored on the open trading day.

    Open periods (today, this week, this month, rolling 7d/30d) end at the moment,
    so the hour after midnight stays inside the service that is still open. Closed
    periods (yesterday, last week, last month) are full Nairobi days. Bookings and
    shifts are not this window: they stay on the calendar day.
    """
    moment = utcnow() if utc_naive is None else utc_naive
    day = trading_day(moment)
    key = _period_key(period)

    def midnight(d: date) -> datetime:
        return datetime.combine(d, time.min) - EAT_OFFSET

    if key in {"today", "daily"}:
        return midnight(day), moment, day
    if key == "yesterday":
        return midnight(day - timedelta(days=1)), midnight(day), day - timedelta(days=1)
    if key == "1h":
        return moment - timedelta(hours=1), moment, day
    if key in {"7d", "weekly"}:
        return moment - timedelta(days=7), moment, day
    if key in {"30d", "monthly"}:
        return moment - timedelta(days=30), moment, day
    if key == "yearly":
        return moment - timedelta(days=365), moment, day
    if key == "last week":
        monday = day - timedelta(days=day.weekday())
        return midnight(monday - timedelta(days=7)), midnight(monday), monday - timedelta(days=7)
    if key in {"this week", "week"}:
        monday = day - timedelta(days=day.weekday())
        return midnight(monday), moment, day
    if key == "last month":
        first = day.replace(day=1)
        previous = (first - timedelta(days=1)).replace(day=1)
        return midnight(previous), midnight(first), previous
    if key in {"this month", "month"}:
        return midnight(day.replace(day=1)), moment, day
    raise ValueError(f"unknown trading period {period!r}")


def service_sales_window(utc_naive: datetime | None = None) -> tuple[datetime, datetime, date]:
    """Naive-UTC [trading-day midnight Nairobi, now). Does not include the rest of the day."""
    return trading_window("today", utc_naive)


def eat_date(utc_naive: datetime) -> date:
    """The Nairobi calendar date of a naive-UTC timestamp read from a DateTime column.

    Use this (in Python) to bucket rows into the owner's days. Never `func.date(column)` over a UTC column:
    it returns the UTC date, which is the wrong day for everything between 21:00 and 24:00 UTC (00:00-03:00
    in Nairobi). See routers/overview.py::_eat_range for the same rule applied to windows.
    """
    return (utc_naive + EAT_OFFSET).date()


def aware_utcnow() -> datetime:
    """
    Current UTC time as a timezone-AWARE datetime.

    Correct for anything leaving the process (API payloads, log timestamps,
    third-party APIs). Never compare the result against a value read from a
    `DateTime` column without attaching tzinfo first — see this module's docstring.
    """
    return datetime.now(timezone.utc)
