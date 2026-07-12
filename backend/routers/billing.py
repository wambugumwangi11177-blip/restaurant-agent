"""
backend/routers/billing.py
───────────────────────────
Per-tenant subscription management (Phase 10). Provider-agnostic state: the plan/
status machine works today with the "manual" provider (owner/admin sets the plan);
wiring a real processor (M-Pesa recurring / Stripe) later is a pluggable business
decision that doesn't change this surface. Admin-only.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import require_role
import models

router = APIRouter(prefix="/billing", tags=["billing"])

VALID_PLANS = {"free", "pro", "enterprise"}


def _get_or_create(db: Session, tenant_id: int) -> models.Subscription:
    sub = db.query(models.Subscription).filter(
        models.Subscription.tenant_id == tenant_id
    ).first()
    if not sub:
        sub = models.Subscription(tenant_id=tenant_id, plan="free", status="active", provider="manual")
        db.add(sub); db.commit(); db.refresh(sub)
    return sub


def _serialize(sub: models.Subscription) -> dict:
    return {
        "plan": sub.plan,
        "status": sub.status,
        "provider": sub.provider,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


@router.get("/")
async def get_subscription(
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """This tenant's subscription (defaults to a free/active/manual row)."""
    return _serialize(_get_or_create(db, current_user.tenant_id))


@router.post("/plan")
async def set_plan(
    body: dict,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """
    Change this tenant's plan. With provider="manual" this simply records the
    selection; a real processor would gate the change on a successful payment.
    Body: {"plan": "pro"}.
    """
    plan = (body or {}).get("plan", "").strip().lower()
    if plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail=f"plan must be one of {sorted(VALID_PLANS)}")
    sub = _get_or_create(db, current_user.tenant_id)
    sub.plan = plan
    sub.status = "active"
    db.commit(); db.refresh(sub)
    return _serialize(sub)
