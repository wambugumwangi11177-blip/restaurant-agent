"""
backend/time_utils.py
─────────────────────
One source of truth for "now, in UTC" and for the restaurant's business day.

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

Operational "today" (POS / Orders / Sales / Home KPIs / Bookings) is NOT UTC
midnight. Kenyan venues run on Africa/Nairobi. `business_today()` +
`utc_naive_range_for_day()` convert a Nairobi calendar day onto the naive-UTC
`created_at` column so Home, Orders and Sales agree.

Zero project imports on purpose — `models.py` imports this, and models.py sits
near the bottom of the import graph.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


BUSINESS_TZ_NAME = "Africa/Nairobi"
BUSINESS_TZ = ZoneInfo(BUSINESS_TZ_NAME)


def utcnow() -> datetime:
    """
    Current UTC time as a NAIVE datetime — the exact semantics of the deprecated
    `datetime.utcnow()`, which this replaces everywhere in the backend.

    Use for anything compared against, or written to, a `DateTime` column.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def aware_utcnow() -> datetime:
    """
    Current UTC time as a timezone-AWARE datetime.

    Correct for anything leaving the process (API payloads, log timestamps,
    third-party APIs). Never compare the result against a value read from a
    `DateTime` column without attaching tzinfo first — see this module's docstring.
    """
    return datetime.now(timezone.utc)


def business_today(now: datetime | None = None) -> date:
    """
    The venue's current calendar date in Africa/Nairobi.

    `now` is optional and used by tests. Naive datetimes are treated as UTC
    (the storage contract). Aware datetimes are converted.
    """
    if now is None:
        return datetime.now(BUSINESS_TZ).date()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(BUSINESS_TZ).date()


def utc_naive_range_for_day(day: date) -> tuple[datetime, datetime]:
    """
    Half-open naive-UTC window `[start, end)` covering `day` in Africa/Nairobi.

    Filter with `created_at >= start AND created_at < end`. Do not use
    `func.date(created_at) == utcnow().date()` — that is the UTC date, which
    disagrees with Nairobi between 00:00 and 03:00 EAT and is what made
    Orders show KES 0 while Home showed yesterday's takings.
    """
    start_eat = datetime(day.year, day.month, day.day, tzinfo=BUSINESS_TZ)
    end_eat = start_eat + timedelta(days=1)
    start_utc = start_eat.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_eat.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc
