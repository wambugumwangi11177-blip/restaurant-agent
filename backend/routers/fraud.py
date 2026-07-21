"""
backend/routers/fraud.py
──────────────────────────
On-demand suspicious-transaction report (Sprint 3). Mirrors
routers/stock_custody.py's variance_report endpoint: read-only, computes the
same thing the scheduled job (main.py's fraud_check, every 2h) checks, gated
to the oversight tiers — front-of-house staff being investigated shouldn't
be the ones who can see the investigation.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
import models
import auth
from routers.deps import get_or_create_restaurant
from ai.fraud import detection as fraud_engine

router = APIRouter(prefix="/fraud", tags=["fraud"])

# Separation of duties, same posture as stock_custody's _CAN_READ_VARIANCE:
# Owner/Manager/Controller read this, front-of-house staff (who could be the
# subject of a flag) cannot.
_CAN_READ = (models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.CONTROLLER)


@router.get("/report")
async def fraud_report(
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_READ)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    report = fraud_engine.compute_fraud_report(db, restaurant.id, window_hours=hours)

    return {
        "restaurant_id": restaurant.id,
        "window_hours": hours,
        "flagged": report.flagged,
        "void_spikes": [
            {
                "actor_user_id": f.actor_user_id, "actor_email": f.actor_email,
                "window_count": f.window_count, "baseline_mean": f.baseline_mean,
                "baseline_stddev": f.baseline_stddev,
            }
            for f in report.void_spikes
        ],
        "refund_velocity": [
            {
                "actor_user_id": f.actor_user_id, "actor_email": f.actor_email,
                "count": f.count, "window_minutes": f.window_minutes, "order_ids": f.order_ids,
            }
            for f in report.refund_velocity
        ],
        "payment_mismatches": [
            {
                "order_id": f.order_id, "payment_method": f.payment_method,
                "total_cents": f.total_cents, "reason": f.reason,
            }
            for f in report.payment_mismatches
        ],
        "off_hours": [
            {
                "order_id": f.order_id, "action": f.action, "actor_user_id": f.actor_user_id,
                "created_at": f.created_at.isoformat() if f.created_at else None,
                "normal_hour_range": list(f.normal_hour_range),
            }
            for f in report.off_hours
        ],
    }
