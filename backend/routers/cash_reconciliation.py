"""
backend/routers/cash_reconciliation.py
──────────────────────────────────────────
Cash reconciliation (Sprint 4) — POST a physical drawer count, GET the
combined report (drawer variances + M-Pesa settlement gaps). Mirrors
routers/stock_custody.py's submit_count/variance_report pair.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from ai.cash_reconciliation import intelligence as cash_engine

router = APIRouter(prefix="/cash-reconciliation", tags=["cash-reconciliation"])

# Same separation-of-duties posture as stock custody: whoever counts the
# drawer shouldn't be the only one who can read the report on themselves.
_CAN_COUNT = (models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.SUPERVISOR)
_CAN_READ = (models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.CONTROLLER)


@router.post("/counts", response_model=schemas.CashDrawerCountOut, status_code=201)
async def submit_drawer_count(
    body: schemas.CashDrawerCountCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_COUNT)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    try:
        count = cash_engine.record_drawer_count(
            db, restaurant.id, current_user.id,
            counted_amount_cents=body.counted_amount_cents,
            window_start=body.window_start, window_end=body.window_end,
            labor_shift_id=body.labor_shift_id, notes=body.notes,
        )
    except cash_engine.DrawerCountError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return count


@router.get("/report")
async def reconciliation_report(
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_READ)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    report = cash_engine.compute_reconciliation_report(db, restaurant.id, window_hours=hours)

    return {
        "restaurant_id": restaurant.id,
        "window_hours": hours,
        "flagged": report.flagged,
        "drawer_variances": [
            {
                "count_id": v.count_id, "expected_amount_cents": v.expected_amount_cents,
                "counted_amount_cents": v.counted_amount_cents,
                "variance_cents": v.variance_cents, "flagged": v.flagged,
            }
            for v in report.drawer_variances
        ],
        "mpesa_mismatches": [
            {
                "order_id": f.order_id, "payment_method": f.payment_method,
                "total_cents": f.total_cents, "reason": f.reason,
            }
            for f in report.mpesa_mismatches
        ],
    }
