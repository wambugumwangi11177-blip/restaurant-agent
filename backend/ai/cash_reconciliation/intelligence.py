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
     ai/stock_custody.py's VARIANCE_THRESHOLD (spoilage/float errors are
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

# KES 200 (in cents) or 1% of expected, whichever is larger — a small,
# consistent till float discrepancy (change-making errors, rounding) is
# normal and shouldn't page anyone; a real gap should.
DRAWER_TOLERANCE_CENTS = 20000
DRAWER_TOLERANCE_PCT = 0.01


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
) -> models.CashDrawerCount:
    """
    Record a physical drawer count and compute variance against expected
    cash-order revenue for the same window. Mirrors
    ai/stock_custody.py::submit_count's shape (compute expected, snapshot it,
    persist, flag if beyond tolerance).
    """
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
    tolerance = max(DRAWER_TOLERANCE_CENTS, int(expected * DRAWER_TOLERANCE_PCT))
    if abs(variance) > tolerance:
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
    db: Session, restaurant_id: int, window_hours: int = 24
) -> CashReconciliationReport:
    """On-demand combined view: recent drawer-count variances + M-Pesa
    settlement gaps. Callers: routers/cash_reconciliation.py (dashboard) and
    the SHIFT_ENDED handler (ai/orchestrator/executive.py or push_notifier.py)
    which triggers a fresh drawer expectation, not this report directly —
    this function is read-only over whatever counts already exist."""
    since = utcnow() - timedelta(hours=window_hours)

    counts = db.query(models.CashDrawerCount).filter(
        models.CashDrawerCount.restaurant_id == restaurant_id,
        models.CashDrawerCount.counted_at >= since,
    ).all()

    drawer_variances = []
    for c in counts:
        variance = c.counted_amount_cents - c.expected_amount_cents
        tolerance = max(DRAWER_TOLERANCE_CENTS, int(c.expected_amount_cents * DRAWER_TOLERANCE_PCT))
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
