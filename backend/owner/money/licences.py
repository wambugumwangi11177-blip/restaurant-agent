"""backend/owner/money/licences.py — how long a licence has left, and what that means for this owner."""
from __future__ import annotations

from datetime import date


def licence_status(expires_on: date, today: date, warning_days: int) -> tuple[int, str]:
    """(days left, 'expired' | 'expiring' | 'ok'). Expiring means within the owner's `licence_warning_days` (default 14)."""
    days_left = (expires_on - today).days
    if days_left < 0:
        return days_left, "expired"
    return days_left, "expiring" if days_left <= warning_days else "ok"
