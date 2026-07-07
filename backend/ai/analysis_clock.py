"""
backend/ai/analysis_clock.py
──────────────────────────────
Every AI analytics module (revenue forecasting, menu engineering, pricing,
labor, inventory, reservations, KDS, profit, supply chain) computes rolling
windows like "last 30 days" anchored to `datetime.utcnow()` — wall-clock
time. That's correct for a restaurant with continuous live order flow, but
wrong for one whose order history is bulk-imported/historical and doesn't
extend all the way to today (found 2026-07-07: real production data for a
108k-order restaurant ends before the current date, so every "last 30 days
from now" window was silently empty — every AI module returned "no data"
even though 2+ years of real orders exist).

`analysis_anchor(db, restaurant_id)` fixes this by anchoring analysis
windows to the restaurant's own most recent order instead of wall-clock
time. A restaurant with live orders today gets today (same behaviour as
before); a restaurant whose data stops earlier gets analysed against its
own last real activity, so "last 30 days" always means the last 30 days
that actually have data.

Deliberately NOT used for genuinely real-time/operational logic (today's
reservations, morning briefing scheduling, WhatsApp cooldown windows) —
those need actual wall-clock time, not a data-anchored substitute.
"""

from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session
import models


def analysis_anchor(db: Session, restaurant_id: int) -> datetime:
    """Effective 'now' for time-windowed analytics queries — see module docstring."""
    latest = (
        db.query(func.max(models.Order.created_at))
        .filter(models.Order.restaurant_id == restaurant_id)
        .scalar()
    )
    return latest or datetime.utcnow()
