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

from datetime import datetime, timezone


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
