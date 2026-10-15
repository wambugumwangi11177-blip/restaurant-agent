"""
backend/ai/cash_reconciliation/intelligence.py
─────────────────────────────────────────────────
Cash reconciliation (Sprint 4) — scoped honestly. There's no bank-feed
integration in this codebase, so a real till/M-Pesa/bank three-way
reconciliation isn't buildable yet. What's buildable today, and still a real
"is the money right" signal:

  1. Drawer-count variance: a staff member physically counts the cash drawer
     at shift end; expected_amount is computed from Order rows
     (payment_method=CASH, is_paid=True) for the same window. A gap beyond
     tolerance is flagged — same "threshold, not zero-tolerance" posture as
     the missing-stock flag in ai/stock_custody.py (spoilage/float errors are
     real and not theft, which is why there's a tolerance).
  2. M-Pesa settlement gaps: reuses ai.fraud.detection.payment_mismatches
     directly rather than reimplementing it — an M-Pesa order marked paid
     with no Safaricom receipt is exactly the same signal here as in the
     fraud report, just surfaced under the "does the money match" framing.

True bank-statement reconciliation (matching to an actual bank deposit) is a
future phase gated on a bank/PSP integration this codebase doesn't have —
that's the honest scope, not "till vs M-Pesa vs bank" as originally pitched.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from time_utils import utcnow
from ai.fraud.detection import payment_mismatches as mpesa_payment_mismatches
from owner.settings import Settings, resolve

# The drawer tolerance — a shilling amount or a share of takings, whichever is larger — is the owner's
# setting (settings.cash_tolerance_cents / cash_tolerance_pct; defaults KES 200 / 1%): a small, consistent till
# float discrepancy (change-making errors, rounding) is normal and shouldn't page anyone; a real gap should.


def drawer_tolerance_cents(expected_cents: int, settings: Settings) -> int:
    return max(settings.cash_tolerance_cents, int(expected_cents * settings.cash_tolerance_pct / 100))


class DrawerCountError(Exception):
    """Precondition failures for submitting a drawer count."""


@dataclass
class DrawerVarianceResult:
    count_id: int
    expected_amount_cents: int
    counted_amount_cents: int
    variance_cents: int
    flagged: bool


@dataclass
class CashReconciliationReport:
    drawer_variances: list = field(default_factory=list)
    mpesa_mismatches: list = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return bool(
            any(v.flagged for v in self.drawer_variances) or self.mpesa_mismatches
        )


def expected_cash_amount_cents(db: Session, restaurant_id: int, window_start, window_end) -> int:
    """Sum of Order.total (cents) for cash orders marked paid in the window —
    the "what the register should hold" side of the comparison."""
    total = db.query(func.sum(models.Order.total)).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.payment_method == models.PaymentMethod.CASH,
        models.Order.is_paid == True,  # noqa: E712
        models.Order.created_at >= window_start,
        models.Order.created_at < window_end,
    ).scalar()
    return int(total or 0)


def record_drawer_count(
    db: Session,
    restaurant_id: int,
    counted_by_user_id: int,
    counted_amount_cents: int,
    window_start,
    window_end,
    labor_shift_id: int | None = None,
    notes: str = "",
    settings: Settings | None = None,
) -> models.CashDrawerCount:
    """
    Record a physical drawer count and compute variance against expected
    cash-order revenue for the same window. Mirrors
    ai/stock_custody.py::submit_count's shape (compute expected, snapshot it,
    persist, flag if beyond tolerance).
    """
    settings = resolve(db, restaurant_id, settings)
    if counted_amount_cents < 0:
        raise DrawerCountError("counted_amount_cents cannot be negative")
    if window_end <= window_start:
        raise DrawerCountError("window_end must be after window_start")

    expected = expected_cash_amount_cents(db, restaurant_id, window_start, window_end)

    count = models.CashDrawerCount(
        restaurant_id=restaurant_id,
        labor_shift_id=labor_shift_id,
        window_start=window_start,
        window_end=window_end,
        expected_amount_cents=expected,
        counted_amount_cents=counted_amount_cents,
        counted_by_user_id=counted_by_user_id,
        notes=notes,
    )
    db.add(count)
    db.commit()
    db.refresh(count)

    from ai.evaluation.tracker import write_audit_log
    write_audit_log(
        db, restaurant_id, "cash_drawer_count_recorded", "cash_reconciliation",
        entity_type="cash_drawer_count", entity_id=count.id,
        before={"expected_amount_cents": expected},
        after={"counted_amount_cents": counted_amount_cents},
        reasoning=f"Drawer count: expected {expected} cents, counted {counted_amount_cents} cents.",
    )

    variance = counted_amount_cents - expected
    if abs(variance) > drawer_tolerance_cents(expected, settings):
        from events.bus import emit_async, EventType
        emit_async(EventType.CASH_RECONCILIATION_FLAGGED, {
            "restaurant_id": restaurant_id,
            "count_id": count.id,
            "expected_amount_cents": expected,
            "counted_amount_cents": counted_amount_cents,
            "variance_cents": variance,
        })

    return count


def compute_reconciliation_report(
    db: Session, restaurant_id: int, window_hours: int = 24, settings: Settings | None = None
) -> CashReconciliationReport:
    """On-demand combined view: recent drawer-count variances + M-Pesa
    settlement gaps. Callers: routers/cash_reconciliation.py (dashboard) and
    the SHIFT_ENDED handler (ai/orchestrator/executive.py or push_notifier.py)
    which triggers a fresh drawer expectation, not this report directly —
    this function is read-only over whatever counts already exist."""
    settings = resolve(db, restaurant_id, settings)
    since = utcnow() - timedelta(hours=window_hours)

    counts = db.query(models.CashDrawerCount).filter(
        models.CashDrawerCount.restaurant_id == restaurant_id,
        models.CashDrawerCount.counted_at >= since,
    ).all()

    drawer_variances = []
    for c in counts:
        variance = c.counted_amount_cents - c.expected_amount_cents
        tolerance = drawer_tolerance_cents(c.expected_amount_cents, settings)
        drawer_variances.append(DrawerVarianceResult(
            count_id=c.id,
            expected_amount_cents=c.expected_amount_cents,
            counted_amount_cents=c.counted_amount_cents,
            variance_cents=variance,
            flagged=abs(variance) > tolerance,
        ))

    return CashReconciliationReport(
        drawer_variances=drawer_variances,
        mpesa_mismatches=mpesa_payment_mismatches(db, restaurant_id, window_hours),
    )


# ── recurring gaps (figure 6.1 P7: "Tuesday night drawer short × 4 weeks") ───────────────────────────────────────

SHIFT_SPLIT_HOUR_EAT = 14       # a counting window that starts before 14:00 Nairobi is the day shift, otherwise the evening
RECURRING_LOOKBACK = 4          # the latest four counts of the same weekday and shift …
RECURRING_MIN_SHORT = 3         # … three of which came up short beyond the tolerance, make a pattern
RECURRING_HISTORY_WEEKS = 12    # counts older than this are not looked at
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass
class RecurringGap:
    weekday: int                  # Nairobi weekday, Monday = 0
    shift: str                    # "day" | "evening"
    times_short: int              # of the latest `of_last` counts of this weekday and shift, how many were short beyond tolerance
    of_last: int
    short_cents: list = field(default_factory=list)   # each shortage that counted, newest first

    @property
    def when(self) -> str:
        return f"{WEEKDAY_NAMES[self.weekday]} {self.shift}"

    @property
    def total_short_cents(self) -> int:
        return sum(self.short_cents)

    @property
    def average_short_cents(self) -> int:
        return round(self.total_short_cents / len(self.short_cents)) if self.short_cents else 0


def recurring_drawer_gaps(db: Session, restaurant_id: int, settings: Settings | None = None, *,
                          lookback: int = RECURRING_LOOKBACK, min_short: int = RECURRING_MIN_SHORT) -> list[RecurringGap]:
    """The same weekday and shift coming up short, again and again — a signal to look at that shift, not a finding about
    anyone. Read-only. A count is *short* when the drawer held less than expected by more than the owner's tolerance.

    Needs at least `min_short` counts of the same weekday and shift; returns the patterns worst first (largest total).
    """
    settings = resolve(db, restaurant_id, settings)
    since = utcnow() - timedelta(weeks=RECURRING_HISTORY_WEEKS)
    counts = db.query(models.CashDrawerCount).filter(
        models.CashDrawerCount.restaurant_id == restaurant_id,
        models.CashDrawerCount.window_start >= since,
    ).order_by(models.CashDrawerCount.window_start.desc()).all()

    groups: dict[tuple[int, str], list] = {}
    for c in counts:
        local = c.window_start + timedelta(hours=3)                       # Nairobi (UTC+3, no daylight saving)
        shift = "day" if local.hour < SHIFT_SPLIT_HOUR_EAT else "evening"
        groups.setdefault((local.weekday(), shift), []).append(c)

    patterns = []
    for (weekday, shift), rows in groups.items():
        latest = rows[:lookback]                                          # newest first
        if len(latest) < min_short:
            continue
        short = [c.expected_amount_cents - c.counted_amount_cents for c in latest
                 if c.expected_amount_cents - c.counted_amount_cents > drawer_tolerance_cents(c.expected_amount_cents, settings)]
        if len(short) >= min_short:
            patterns.append(RecurringGap(weekday, shift, len(short), len(latest), short))
    return sorted(patterns, key=lambda p: p.total_short_cents, reverse=True)
