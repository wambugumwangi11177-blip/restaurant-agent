"""
backend/owner/money/ledger.py — the rules every ledger entry shares: money, dates, who is looking.

  * KES ↔ cents: the API speaks decimal shillings with at most two places; the database holds integer cents. `Decimal`
    all the way in, so 0.1 + 0.2 can never reach a ledger.
  * An entry's day is a NAIROBI calendar date (never a UTC timestamp bucketed by `func.date`, D17).
  * Entries may be dated up to tomorrow (a payment made late in the evening for the next day) and not older than five years.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from time_utils import eat_date, utcnow

MAX_KES = Decimal("100000000")            # KES 100 million: a typo guard, not a business limit
MAX_PAST_DAYS = 365 * 5
LICENCE_MIN_DATE = date(2000, 1, 1)
LICENCE_MAX_DATE = date(2100, 1, 1)
MONTH_MIN = date(2000, 1, 1)
_MONTH = re.compile(r"(\d{4})-(0[1-9]|1[0-2])")


def to_cents(kes: Decimal) -> int:
    """Shillings (at most two decimal places) → integer cents, exactly."""
    cents = kes * 100
    if cents != cents.to_integral_value():
        raise ValueError("amounts have at most two decimal places")
    return int(cents)


def to_kes(cents: int | None) -> float | None:
    return None if cents is None else round(cents / 100, 2)


def parse_money(value) -> Decimal:
    """Accept a JSON number or string; refuse booleans, NaN and infinity; floats go through their shortest repr, not binary."""
    if isinstance(value, bool) or value is None:
        raise ValueError("an amount in shillings is required")
    try:
        d = Decimal(repr(value)) if isinstance(value, float) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError("not a valid amount") from None
    if not d.is_finite():
        raise ValueError("not a valid amount")
    return d


def nairobi_today() -> date:
    return eat_date(utcnow())


def check_entry_date(day: date, *, today: date | None = None) -> date:
    """An entry may be dated up to tomorrow and not more than five years back."""
    today = today or nairobi_today()
    if day > today + timedelta(days=1):
        raise ValueError("a payment cannot be dated more than a day ahead")
    if (today - day).days > MAX_PAST_DAYS:
        raise ValueError("a payment cannot be dated more than five years back")
    return day


def parse_month(value: str, *, today: date | None = None) -> date:
    """"2026-09" → the first day of that month. A month that has not started yet, or before 2000, is refused."""
    m = _MONTH.fullmatch(value or "")
    if m is None:
        raise ValueError("a month looks like 2026-09")
    first = date(int(m.group(1)), int(m.group(2)), 1)
    if first < MONTH_MIN:
        raise ValueError("that month is too far back")
    if first > (today or nairobi_today()).replace(day=1):
        raise ValueError("that month has not started yet")
    return first
