"""
backend/ai/fraud/detection.py
────────────────────────────────
Suspicious-transaction pattern detection (Sprint 3). Mirrors ai/stock_custody.py's
shape exactly: pure functions over a Session, no HTTP/Twilio/scheduler, so the
math is unit-testable without spinning up the app. stock_custody catches
inventory theft (theoretical vs actual usage); this module catches the class
it can't see — cash/register-level manipulation — using the OrderAudit trail
added in Sprint 1 (previously nowhere recorded who voided/cancelled what).

Four independent patterns, each adaptive per-restaurant/per-staff rather than
a fixed global number — a restaurant with naturally high turnover shouldn't
get flagged for behaving like itself (same "threshold, not zero-tolerance"
philosophy as stock_custody.VARIANCE_THRESHOLD):

  1. void_spikes      — a staff member's cancel/refund count this window blows
                         past their OWN historical baseline (mean + N stddev).
  2. refund_velocity   — a fast burst of cancels/refunds by the same person,
                         independent of #1 (a slow elevated rate over a day
                         vs several in a few minutes are different signals).
  3. payment_mismatches — an M-Pesa order marked paid with no Safaricom
                         receipt on file (manual override, not real settlement).
  4. off_hours_activity — order status changes outside the hours the
                         restaurant's own order history says is normal (no
                         operating-hours field exists to read instead, so the
                         "normal" window is derived, not configured).

Cold-start guards throughout (mirrors ai/pricing/analysis.py's DS-01): a
pattern simply doesn't fire until there's enough history to trust a baseline
against, rather than guessing and producing false positives on day one.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from statistics import mean, pstdev

from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from time_utils import utcnow

MIN_BASELINE_DAYS = 7
VOID_SPIKE_STDDEV_MULTIPLIER = 2.5
VOID_SPIKE_MIN_COUNT = 5   # floor — a 2-vs-0-baseline day is noise, not a statistical spike

REFUND_VELOCITY_WINDOW_MINUTES = 30
REFUND_VELOCITY_MIN_COUNT = 4

OFF_HOURS_HISTORY_DAYS = 30
OFF_HOURS_MIN_ORDERS = 20   # cold-start guard, same reasoning as MIN_BASELINE_DAYS

_CANCEL_LIKE_ACTIONS = [models.OrderAuditAction.CANCEL, models.OrderAuditAction.REFUND]


@dataclass
class VoidSpikeFlag:
    actor_user_id: int
    actor_email: str
    window_count: int
    baseline_mean: float
    baseline_stddev: float


@dataclass
class RefundVelocityFlag:
    actor_user_id: int
    actor_email: str
    count: int
    window_minutes: int
    order_ids: list


@dataclass
class PaymentMismatchFlag:
    order_id: int
    payment_method: str
    total_cents: int
    reason: str


@dataclass
class OffHoursFlag:
    order_id: int
    action: str
    actor_user_id: int | None
    created_at: object
    normal_hour_range: tuple


@dataclass
class FraudReport:
    void_spikes: list = field(default_factory=list)
    refund_velocity: list = field(default_factory=list)
    payment_mismatches: list = field(default_factory=list)
    off_hours: list = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return bool(self.void_spikes or self.refund_velocity
                    or self.payment_mismatches or self.off_hours)


def _detect_void_spikes(db: Session, restaurant_id: int, window_hours: int) -> list:
    now = utcnow()
    window_start = now - timedelta(hours=window_hours)
    baseline_start = now - timedelta(days=30)

    # Per-actor daily cancel/refund counts over the trailing 30 days — this
    # builds each staff member's OWN baseline, not a restaurant-wide number.
    baseline_rows = (
        db.query(
            models.OrderAudit.actor_user_id,
            func.date(models.OrderAudit.created_at),
            func.count(models.OrderAudit.id),
        )
        .filter(
            models.OrderAudit.restaurant_id == restaurant_id,
            models.OrderAudit.action.in_(_CANCEL_LIKE_ACTIONS),
            models.OrderAudit.created_at >= baseline_start,
            models.OrderAudit.created_at < window_start,   # baseline excludes the window itself
            models.OrderAudit.actor_user_id.isnot(None),
        )
        .group_by(models.OrderAudit.actor_user_id, func.date(models.OrderAudit.created_at))
        .all()
    )

    by_actor: dict = {}
    for actor_id, _day, count in baseline_rows:
        by_actor.setdefault(actor_id, []).append(count)

    window_rows = (
        db.query(models.OrderAudit.actor_user_id, func.count(models.OrderAudit.id))
        .filter(
            models.OrderAudit.restaurant_id == restaurant_id,
            models.OrderAudit.action.in_(_CANCEL_LIKE_ACTIONS),
            models.OrderAudit.created_at >= window_start,
            models.OrderAudit.actor_user_id.isnot(None),
        )
        .group_by(models.OrderAudit.actor_user_id)
        .all()
    )

    flags = []
    for actor_id, window_count in window_rows:
        daily_counts = by_actor.get(actor_id, [])
        if len(daily_counts) < MIN_BASELINE_DAYS or window_count < VOID_SPIKE_MIN_COUNT:
            continue
        baseline_mean = mean(daily_counts)
        baseline_stddev = pstdev(daily_counts) if len(daily_counts) > 1 else 0.0
        threshold = baseline_mean + VOID_SPIKE_STDDEV_MULTIPLIER * baseline_stddev
        if window_count > threshold:
            actor = db.query(models.User).filter(models.User.id == actor_id).first()
            flags.append(VoidSpikeFlag(
                actor_user_id=actor_id,
                actor_email=actor.email if actor else "unknown",
                window_count=window_count,
                baseline_mean=round(baseline_mean, 2),
                baseline_stddev=round(baseline_stddev, 2),
            ))
    return flags


def _detect_refund_velocity(db: Session, restaurant_id: int, window_hours: int) -> list:
    scan_start = utcnow() - timedelta(hours=window_hours)
    rows = (
        db.query(models.OrderAudit)
        .filter(
            models.OrderAudit.restaurant_id == restaurant_id,
            models.OrderAudit.action.in_(_CANCEL_LIKE_ACTIONS),
            models.OrderAudit.created_at >= scan_start,
            models.OrderAudit.actor_user_id.isnot(None),
        )
        .order_by(models.OrderAudit.actor_user_id, models.OrderAudit.created_at)
        .all()
    )

    by_actor: dict = {}
    for row in rows:
        by_actor.setdefault(row.actor_user_id, []).append(row)

    velocity_window = timedelta(minutes=REFUND_VELOCITY_WINDOW_MINUTES)
    flags = []
    for actor_id, actor_rows in by_actor.items():
        # Sliding window over this actor's own sorted events — a burst
        # anywhere in the scan window trips it, not just a raw total count.
        i = 0
        while i < len(actor_rows):
            burst = [actor_rows[i]]
            j = i + 1
            while j < len(actor_rows) and actor_rows[j].created_at - actor_rows[i].created_at <= velocity_window:
                burst.append(actor_rows[j])
                j += 1
            if len(burst) >= REFUND_VELOCITY_MIN_COUNT:
                actor = db.query(models.User).filter(models.User.id == actor_id).first()
                flags.append(RefundVelocityFlag(
                    actor_user_id=actor_id,
                    actor_email=actor.email if actor else "unknown",
                    count=len(burst),
                    window_minutes=REFUND_VELOCITY_WINDOW_MINUTES,
                    order_ids=[b.order_id for b in burst],
                ))
                break   # one flag per actor per scan is enough signal
            i += 1
    return flags


def _detect_payment_mismatches(db: Session, restaurant_id: int, window_hours: int) -> list:
    since = utcnow() - timedelta(hours=window_hours)
    orders = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.created_at >= since,
        models.Order.payment_method == models.PaymentMethod.MPESA,
        models.Order.is_paid == True,  # noqa: E712
        models.Order.mpesa_receipt.is_(None),
    ).all()

    return [
        PaymentMismatchFlag(
            order_id=o.id, payment_method=o.payment_method.value, total_cents=o.total or 0,
            reason="Marked paid via M-Pesa with no Safaricom receipt on file — "
                   "likely a manual override, not a real settled payment.",
        )
        for o in orders
    ]


def _detect_off_hours_activity(db: Session, restaurant_id: int, window_hours: int) -> list:
    history_start = utcnow() - timedelta(days=OFF_HOURS_HISTORY_DAYS)
    hour_rows = db.query(func.extract("hour", models.Order.created_at)).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.created_at >= history_start,
    ).all()
    hours = sorted(int(h) for (h,) in hour_rows if h is not None)
    if len(hours) < OFF_HOURS_MIN_ORDERS:
        return []   # not enough history to know "normal" yet — no false positives on day one

    # Normal window = the hours covering the middle 90% of order volume, not a
    # fixed clock range — a restaurant that trades naturally past midnight
    # shouldn't get flagged for its own normal late trade.
    lo_idx = int(len(hours) * 0.05)
    hi_idx = min(int(len(hours) * 0.95), len(hours) - 1)
    normal_range = (hours[lo_idx], hours[hi_idx])

    scan_start = utcnow() - timedelta(hours=window_hours)
    audits = db.query(models.OrderAudit).filter(
        models.OrderAudit.restaurant_id == restaurant_id,
        models.OrderAudit.created_at >= scan_start,
    ).all()

    flags = []
    for a in audits:
        hr = a.created_at.hour
        if normal_range[0] <= normal_range[1]:
            in_range = normal_range[0] <= hr <= normal_range[1]
        else:
            in_range = hr >= normal_range[0] or hr <= normal_range[1]   # wraps past midnight
        if not in_range:
            flags.append(OffHoursFlag(
                order_id=a.order_id, action=a.action.value, actor_user_id=a.actor_user_id,
                created_at=a.created_at, normal_hour_range=normal_range,
            ))
    return flags


def payment_mismatches(db: Session, restaurant_id: int, window_hours: int = 24) -> list:
    """Public entry point for the M-Pesa mismatch check alone — reused by
    ai/cash_reconciliation/intelligence.py's report so the "paid with no
    receipt" signal has exactly one implementation, not a duplicate."""
    return _detect_payment_mismatches(db, restaurant_id, window_hours)


def compute_fraud_report(db: Session, restaurant_id: int, window_hours: int = 24) -> FraudReport:
    """
    Run all four pattern detectors over the trailing `window_hours` (default
    24h — matches stock_custody's daily-shift-scale window). Callers:
    routers/fraud.py (on-demand dashboard report) and main.py's scheduled
    job (every 2h, emits SUSPICIOUS_TRANSACTION_FLAGGED only if anything's
    flagged — see EventType's docstring in events/bus.py).
    """
    return FraudReport(
        void_spikes=_detect_void_spikes(db, restaurant_id, window_hours),
        refund_velocity=_detect_refund_velocity(db, restaurant_id, window_hours),
        payment_mismatches=_detect_payment_mismatches(db, restaurant_id, window_hours),
        off_hours=_detect_off_hours_activity(db, restaurant_id, window_hours),
    )
