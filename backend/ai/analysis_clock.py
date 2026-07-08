"""
backend/ai/analysis_clock.py
──────────────────────────────
Every AI analytics module (revenue forecasting, menu engineering, pricing,
labor, inventory, reservations, KDS, profit, supply chain) computes rolling
windows like "last 30 days" anchored to `utcnow()` — wall-clock
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
from sqlalchemy import func
from sqlalchemy.orm import Session
import models
from time_utils import utcnow

# The analysis window should end where the most recent ~30 orders happened,
# not at a single straggler order. 30 is also the minimum sample the
# downstream velocity/trend math wants to be meaningful, so it doubles as a
# "enough data to analyse" floor.
ANCHOR_SAMPLE_SIZE = 30

# How far the newest real order may lag wall-clock time before we flag the
# dataset as stale. The whole point of analysis_anchor() is that it silently
# analyses a restaurant's last real activity even when that stopped days ago —
# which is exactly the behaviour that hides a broken order feed. A live
# restaurant orders every day, so a gap past this many days almost always
# means "the data stopped flowing" (import finished, integration broke), not
# "quiet week". Deliberately generous so a normal closed-day or two doesn't
# trip it. Freshness is measured against the SINGLE most recent order (has the
# feed gone quiet?), not the 30th — that's a separate question from where the
# analysis window sits.
STALE_AFTER_DAYS = 3


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
        return utcnow()
    # rows are newest-first; rows[-1] is the ANCHOR_SAMPLE_SIZE-th most recent
    # order (or the oldest order the restaurant has, if it has fewer than that).
    return rows[-1][0] or utcnow()


def data_freshness(db: Session, restaurant_id: int) -> dict:
    """
    Staleness signal for the analytics dashboard. Because analysis_anchor()
    intentionally makes stale/imported data look analysable, a broken order
    feed is otherwise indistinguishable from a healthy restaurant. This surfaces
    that: it reports how far the newest order lags real (wall-clock) time so the
    frontend can warn "you're looking at N-day-old data".

    Returns:
      latest_order_at : ISO timestamp of the most recent order, or None if no orders
      data_age_days   : whole days between that order and wall-clock now (0 if none)
      is_stale        : True when data_age_days > STALE_AFTER_DAYS
      stale_after_days: the threshold, so the client doesn't hard-code it
    """
    latest = (
        db.query(func.max(models.Order.created_at))
        .filter(models.Order.restaurant_id == restaurant_id)
        .scalar()
    )
    if latest is None:
        return {
            "latest_order_at": None,
            "data_age_days": 0,
            "is_stale": False,
            "stale_after_days": STALE_AFTER_DAYS,
        }
    age_days = max((utcnow() - latest).days, 0)
    return {
        "latest_order_at": latest.isoformat(),
        "data_age_days": age_days,
        "is_stale": age_days > STALE_AFTER_DAYS,
        "stale_after_days": STALE_AFTER_DAYS,
    }
