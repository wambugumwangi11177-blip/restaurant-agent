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
windows to the restaurant's own recent order activity instead of wall-clock
time. A restaurant with live orders today gets ~today (same behaviour as
before); a restaurant whose data stops earlier gets analysed against its own
last real activity.

Why the Nth-most-recent order, not simply the single most recent (found
2026-07-07 against the real Lavy dataset): that dataset is dense through
2026-04 (~6,000 orders/month) then has EXACTLY ONE order in 2026-05 and one
in 2026-06 — almost certainly straggler/test rows left over from the import.
Anchoring to the single last order (2026-06-05) gave a trailing-30-day window
containing just those two stragglers: KES 630 of "revenue" and zero pricing
signal, right next to a dense ~6,000-order month. Anchoring instead to the
date of the ANCHOR_SAMPLE_SIZE-th most recent order steps over a handful of
stragglers and lands the window on the last period with real volume. For a
genuinely live/busy restaurant the Nth-most-recent order is still ~now, so
behaviour there is unchanged.

Deliberately NOT used for genuinely real-time/operational logic (today's
reservations, morning briefing scheduling, WhatsApp cooldown windows, overdue
purchase-order checks) — those need actual wall-clock time, not a
data-anchored substitute.
"""

from datetime import datetime
from sqlalchemy.orm import Session
import models

# The analysis window should end where the most recent ~30 orders happened,
# not at a single straggler order. 30 is also the minimum sample the
# downstream velocity/trend math wants to be meaningful, so it doubles as a
# "enough data to analyse" floor.
ANCHOR_SAMPLE_SIZE = 30


def analysis_anchor(db: Session, restaurant_id: int) -> datetime:
    """Effective 'now' for time-windowed analytics queries — see module docstring."""
    rows = (
        db.query(models.Order.created_at)
        .filter(models.Order.restaurant_id == restaurant_id)
        .order_by(models.Order.created_at.desc())
        .limit(ANCHOR_SAMPLE_SIZE)
        .all()
    )
    if not rows:
        return datetime.utcnow()
    # rows are newest-first; rows[-1] is the ANCHOR_SAMPLE_SIZE-th most recent
    # order (or the oldest order the restaurant has, if it has fewer than that).
    return rows[-1][0] or datetime.utcnow()
