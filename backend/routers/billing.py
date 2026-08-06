"""
backend/routers/billing.py
───────────────────────────
Per-tenant subscription state, and the enforcement that makes it mean something.

What changed 2026-08-06
───────────────────────
Before this, a subscription was a string an admin set on themselves. Every
tenant was created `plan="free", status="active", provider="manual"`,
`/billing/plan` wrote the field with no payment gate, and nothing anywhere in
the codebase ever read the result. The product could take M-Pesa payments *for*
restaurants (payments/mpesa_client.py — a real Daraja integration) and had no
way at all to take payment *from* them. Every shilling of the company's own
revenue was invoiced by hand, outside the system.

This module now runs a real state machine — trial, paid period, lapse, grace,
cancellation — and exposes `require_active_subscription` so routes can actually
be gated. What it deliberately does NOT do is pick a payment processor.

Why the processor stays pluggable
─────────────────────────────────
`provider="manual"` remains the default and `record_payment()` is the manual
recording endpoint: an admin confirms money arrived (M-Pesa till, bank transfer)
and the period extends. That is how this business collects today, and it is a
complete, working billing loop — invoicing is manual, but *enforcement* is not.
Wiring M-Pesa recurring or Stripe later means implementing one adapter that
calls `extend_period()`; no route, schema or gate below changes.

What gets gated, and what must never be
───────────────────────────────────────
`require_active_subscription` is applied to the intelligence layer (`/ai/*`) —
the thing a restaurant is actually paying for.

It is deliberately NOT applied to POS, KDS, orders, menu, payments or auth. A
restaurant whose card bounced must still be able to take orders and feed people
tonight. Locking the till over a billing state would strand a dining room
mid-service, and any owner it happened to once would tear the system out the
next morning — correctly. Non-payment should cost you the analytics, not your
ability to trade.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.orm import Session

import auth
import models
from auth import require_role
from database import get_db
from time_utils import utcnow

router = APIRouter(prefix="/billing", tags=["billing"])

VALID_PLANS = {"free", "pro", "enterprise"}

# Status values. `trialing` and `active` both grant access; `past_due` and
# `canceled` do not. `past_due` is reached by a period lapsing, not by an admin
# setting it — see _effective_status().
STATUS_TRIALING = "trialing"
STATUS_ACTIVE   = "active"
STATUS_PAST_DUE = "past_due"
STATUS_CANCELED = "canceled"

GRANTING_STATUSES = {STATUS_TRIALING, STATUS_ACTIVE}

# Days added per recorded payment when the caller doesn't specify. A calendar
# month would be more natural, but a fixed 30 keeps the arithmetic honest across
# month lengths and matches the 30-day windows every analytics module uses.
DEFAULT_PERIOD_DAYS = 30

# How long a lapsed subscription keeps working after its period ends. This is a
# deliberate kindness with a hard edge: M-Pesa payments from a restaurant owner
# arrive when the owner remembers, not on a schedule, and cutting the analytics
# off at midnight on day 30 over a payment that lands on day 31 buys nothing.
GRACE_DAYS = 3

# New tenants get a trial rather than a free-forever plan, so the paid state is
# the default destination and enforcement is exercised from day one instead of
# being switched on later against live restaurants.
TRIAL_DAYS = 14


def _get_or_create(db: Session, tenant_id: int) -> models.Subscription:
    sub = db.query(models.Subscription).filter(
        models.Subscription.tenant_id == tenant_id
    ).first()
    if not sub:
        sub = models.Subscription(
            tenant_id=tenant_id,
            plan="free",
            status=STATUS_TRIALING,
            provider="manual",
            current_period_end=utcnow() + timedelta(days=TRIAL_DAYS),
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return sub


def _effective_status(sub: models.Subscription) -> str:
    """
    The subscription's real state right now, which is not always the stored one.

    A stored `active` whose `current_period_end` passed (plus grace) is
    `past_due` in fact, whatever the column says. Computing this on read rather
    than relying on a nightly job means enforcement can't silently fail because
    a scheduler didn't run — the single-worker APScheduler in main.py is exactly
    the kind of thing that stops quietly.
    """
    stored = (sub.status or "").strip().lower()
    if stored == STATUS_CANCELED:
        return STATUS_CANCELED
    if stored not in GRANTING_STATUSES:
        return stored or STATUS_PAST_DUE
    if sub.current_period_end is None:
        # No expiry recorded — treat as open-ended. This is what an enterprise
        # tenant on an offline contract looks like.
        return stored
    if utcnow() <= sub.current_period_end + timedelta(days=GRACE_DAYS):
        return stored
    return STATUS_PAST_DUE


def is_active(sub: models.Subscription) -> bool:
    return _effective_status(sub) in GRANTING_STATUSES


def _days_remaining(sub: models.Subscription) -> int | None:
    if sub.current_period_end is None:
        return None
    delta = sub.current_period_end - utcnow()
    return max(0, int(delta.total_seconds() // 86400))


def _serialize(sub: models.Subscription) -> dict:
    effective = _effective_status(sub)
    return {
        "plan": sub.plan,
        # `status` reports the EFFECTIVE state so a client never has to
        # re-implement the lapse arithmetic to know whether it has access.
        "status": effective,
        "stored_status": sub.status,
        "provider": sub.provider,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "days_remaining": _days_remaining(sub),
        "in_grace_period": effective in GRANTING_STATUSES
                           and sub.current_period_end is not None
                           and utcnow() > sub.current_period_end,
        "is_active": effective in GRANTING_STATUSES,
    }


def extend_period(sub: models.Subscription, days: int = DEFAULT_PERIOD_DAYS) -> None:
    """
    Add a paid period. The single seam a real payment processor plugs into:
    an M-Pesa recurring callback or a Stripe webhook calls this and nothing
    else in the module needs to know which one did.

    Extends from whichever is later — now, or the existing period end — so
    paying early adds time instead of throwing it away, and paying after a lapse
    doesn't back-date the new period into the past.
    """
    base = utcnow()
    if sub.current_period_end and sub.current_period_end > base:
        base = sub.current_period_end
    sub.current_period_end = base + timedelta(days=days)
    sub.status = STATUS_ACTIVE


# ── Enforcement dependency ───────────────────────────────────────────────────

def require_active_subscription(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
) -> models.Subscription:
    """
    Gate a route on a paying (or trialing) tenant.

    402 Payment Required, not 403: the caller is correctly authenticated and
    correctly authorised — the account simply owes money. A client can act on
    that distinction (show a renewal prompt, not an access-denied error), and it
    keeps this cleanly separable from `require_role`'s RBAC failures in logs.
    """
    sub = _get_or_create(db, current_user.tenant_id)
    if not is_active(sub):
        raise HTTPException(
            status_code=http_status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": "Subscription inactive — renew to restore intelligence features.",
                "status": _effective_status(sub),
                "plan": sub.plan,
                "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            },
        )
    return sub


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/")
async def get_subscription(
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """This tenant's subscription, with its effective (lapse-aware) state."""
    return _serialize(_get_or_create(db, current_user.tenant_id))


@router.post("/plan")
async def set_plan(
    body: dict,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Change this tenant's plan tier. Deliberately does NOT grant access time —
    that only ever comes from `/billing/record-payment`. Before this split, an
    admin could hand themselves `plan="enterprise"` and `status="active"` in one
    call, which is precisely why billing meant nothing.

    Body: {"plan": "pro"}.
    """
    plan = (body or {}).get("plan", "").strip().lower()
    if plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail=f"plan must be one of {sorted(VALID_PLANS)}")
    sub = _get_or_create(db, current_user.tenant_id)
    sub.plan = plan
    db.commit()
    db.refresh(sub)
    return _serialize(sub)


@router.post("/record-payment")
async def record_payment(
    body: dict = None,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Record that money arrived and extend the paid period.

    With `provider="manual"` this is the human step: an admin confirms the
    M-Pesa or bank transfer landed. When a processor is wired later, its webhook
    calls `extend_period()` directly and this endpoint stays as the manual
    fallback for offline payments — which, for restaurants paying by till
    number, will never fully go away.

    Body: {"days": 30} (optional).
    """
    # Explicit None check, not `or DEFAULT_PERIOD_DAYS`: 0 is falsy, so `or`
    # would silently turn a rejected {"days": 0} into a granted 30-day period.
    raw = (body or {}).get("days")
    try:
        days = DEFAULT_PERIOD_DAYS if raw is None else int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="days must be an integer")
    if days <= 0 or days > 366:
        raise HTTPException(status_code=400, detail="days must be between 1 and 366")

    sub = _get_or_create(db, current_user.tenant_id)
    extend_period(sub, days)
    db.commit()
    db.refresh(sub)
    return _serialize(sub)


@router.post("/cancel")
async def cancel_subscription(
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Cancel immediately. `current_period_end` is left untouched so the remaining
    paid time is still on record — reinstating is a `record-payment` away and
    the history shows what was actually bought.
    """
    sub = _get_or_create(db, current_user.tenant_id)
    sub.status = STATUS_CANCELED
    db.commit()
    db.refresh(sub)
    return _serialize(sub)
