"""
backend/routers/staff.py
──────────────────────────
Staff roster and shift tracking — the write path for `StaffMember` and
`LaborShift`.

Why this exists
───────────────
Both tables shipped with the labor-intelligence work (Layer 4) and were read by
`ai/labor/intelligence.py` for labor cost %, sales per employee hour, overtime
detection and staffing recommendations. But a grep for writers across the whole
codebase — including `populate_production.py`, which seeds everything else —
found none. Not one row could ever exist, so:

  • `get_labor_intelligence()` hit its `if not shifts: return _empty_response()`
    branch on every restaurant, always;
  • `ai/roi/savings.py` fell back to `DEFAULT_HOURLY_RATE_CENTS` (KES 250/hr)
    for its money conversion, meaning the "hours saved" figure shown to owners
    was priced at a constant rather than at what they actually pay people.

Design notes
────────────
• **Clock-in/clock-out are separate endpoints, not a shift PATCH.** They're the
  two events staff actually perform, they're the ones that must be idempotent
  (a double-tap at the end of a long shift must not restart the clock), and
  keeping them distinct means the roster edit surface stays admin-only while
  clocking stays open to the staff member on the floor.

• **`labor_cost` is computed at clock-out, from the rate in force at that
  moment.** Recomputing it later from the current `hourly_rate` would silently
  rewrite history every time someone got a raise, and labor cost % for past
  months would move under the owner's feet.

• **Deactivation is a soft delete.** `LaborShift` rows carry the cost history
  that labor analytics reads over a 30-day window; hard-deleting a leaver would
  delete last month's labor cost with them.
"""

from datetime import date as date_type
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db
from routers.deps import get_or_create_restaurant
from time_utils import utcnow

router = APIRouter(prefix="/staff", tags=["staff"])


def _hours_between(start, end) -> float:
    """Elapsed hours, clamped at 0 so a clock adjustment can't bill negative time."""
    if not start or not end:
        return 0.0
    return max(0.0, (end - start).total_seconds() / 3600.0)


def _shift_out(shift: models.LaborShift, staff_name: str) -> dict:
    return {
        "id": shift.id,
        "staff_member_id": shift.staff_member_id,
        "staff_name": staff_name,
        "shift_date": shift.shift_date,
        "scheduled_start": shift.scheduled_start,
        "scheduled_end": shift.scheduled_end,
        "actual_start": shift.actual_start,
        "actual_end": shift.actual_end,
        "scheduled_hours": shift.scheduled_hours,
        "actual_hours": shift.actual_hours,
        "labor_cost": shift.labor_cost,
        "notes": shift.notes or "",
    }


def _load_owned_staff(db: Session, restaurant_id: int, staff_id: int) -> models.StaffMember:
    """Scope the query by restaurant_id so a cross-tenant id simply 404s."""
    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.restaurant_id == restaurant_id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return staff


def _load_owned_shift(db: Session, restaurant_id: int, shift_id: int) -> models.LaborShift:
    shift = db.query(models.LaborShift).filter(
        models.LaborShift.id == shift_id,
        models.LaborShift.restaurant_id == restaurant_id,
    ).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    return shift


# ── Roster ───────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.StaffMemberOut])
async def list_staff(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    q = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant.id
    )
    if not include_inactive:
        q = q.filter(models.StaffMember.is_active == True)  # noqa: E712
    return q.order_by(models.StaffMember.name).all()


@router.post("/", response_model=schemas.StaffMemberOut)
async def create_staff(
    body: schemas.StaffMemberCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    """Admin-only: wages are payroll data, and hourly_rate drives labor cost %."""
    restaurant = get_or_create_restaurant(db, current_user)
    if body.hourly_rate < 0:
        raise HTTPException(status_code=400, detail="hourly_rate cannot be negative")

    staff = models.StaffMember(
        restaurant_id=restaurant.id,
        name=body.name,
        role_title=body.role_title,
        hourly_rate=body.hourly_rate,
        user_id=body.user_id,
        is_active=True,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


@router.put("/{staff_id}", response_model=schemas.StaffMemberOut)
async def update_staff(
    staff_id: int,
    body: schemas.StaffMemberUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    staff = _load_owned_staff(db, restaurant.id, staff_id)

    updates = body.model_dump(exclude_unset=True)
    if updates.get("hourly_rate") is not None and updates["hourly_rate"] < 0:
        raise HTTPException(status_code=400, detail="hourly_rate cannot be negative")
    for key, value in updates.items():
        setattr(staff, key, value)

    # Deliberately does NOT backfill labor_cost on existing shifts — see the
    # module docstring. A raise applies to future shifts, not to last month's.
    db.commit()
    db.refresh(staff)
    return staff


@router.delete("/{staff_id}")
async def deactivate_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    """Soft delete — their shift history is this restaurant's labor cost history."""
    restaurant = get_or_create_restaurant(db, current_user)
    staff = _load_owned_staff(db, restaurant.id, staff_id)
    staff.is_active = False
    db.commit()
    return {"message": f"{staff.name} deactivated", "id": staff.id}


# ── Shifts ───────────────────────────────────────────────────────────────────

@router.get("/shifts/", response_model=List[schemas.ShiftOut])
async def list_shifts(
    start_date: Optional[date_type] = Query(None),
    end_date: Optional[date_type] = Query(None),
    staff_member_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    q = db.query(models.LaborShift).filter(
        models.LaborShift.restaurant_id == restaurant.id
    )
    if start_date:
        q = q.filter(models.LaborShift.shift_date >= start_date)
    if end_date:
        q = q.filter(models.LaborShift.shift_date <= end_date)
    if staff_member_id:
        q = q.filter(models.LaborShift.staff_member_id == staff_member_id)

    shifts = q.order_by(models.LaborShift.shift_date.desc()).limit(500).all()
    if not shifts:
        return []

    names = {
        s.id: s.name
        for s in db.query(models.StaffMember).filter(
            models.StaffMember.id.in_({sh.staff_member_id for sh in shifts})
        ).all()
    }
    return [_shift_out(sh, names.get(sh.staff_member_id, "")) for sh in shifts]


@router.post("/shifts/", response_model=schemas.ShiftOut)
async def create_shift(
    body: schemas.ShiftCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    """Schedule a shift. Rostering is a management action, so admin-only."""
    restaurant = get_or_create_restaurant(db, current_user)
    staff = _load_owned_staff(db, restaurant.id, body.staff_member_id)

    scheduled_hours = None
    if body.scheduled_start and body.scheduled_end:
        if body.scheduled_end <= body.scheduled_start:
            raise HTTPException(
                status_code=400, detail="scheduled_end must be after scheduled_start"
            )
        scheduled_hours = _hours_between(body.scheduled_start, body.scheduled_end)

    shift = models.LaborShift(
        restaurant_id=restaurant.id,
        staff_member_id=staff.id,
        shift_date=body.shift_date,
        scheduled_start=body.scheduled_start,
        scheduled_end=body.scheduled_end,
        scheduled_hours=scheduled_hours,
        notes=body.notes,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return _shift_out(shift, staff.name)


@router.post("/shifts/{shift_id}/clock-in", response_model=schemas.ShiftOut)
async def clock_in(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Idempotent: clocking in twice keeps the FIRST timestamp. Re-stamping would
    quietly shorten the shift and undercount the restaurant's labor cost.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    shift = _load_owned_shift(db, restaurant.id, shift_id)
    staff = _load_owned_staff(db, restaurant.id, shift.staff_member_id)

    if shift.actual_start is None:
        shift.actual_start = utcnow()
        db.commit()
        db.refresh(shift)
    return _shift_out(shift, staff.name)


@router.post("/shifts/{shift_id}/clock-out", response_model=schemas.ShiftOut)
async def clock_out(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Close the shift and compute actual_hours + labor_cost.

    Also idempotent — a double-tap at the end of a long shift must not extend
    the clock or recompute the cost. `labor_cost` is priced at the rate in force
    right now and then frozen, so a later raise never rewrites this month's
    labor cost %.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    shift = _load_owned_shift(db, restaurant.id, shift_id)
    staff = _load_owned_staff(db, restaurant.id, shift.staff_member_id)

    if shift.actual_end is not None:
        return _shift_out(shift, staff.name)
    if shift.actual_start is None:
        raise HTTPException(status_code=400, detail="Cannot clock out before clocking in")

    shift.actual_end = utcnow()
    shift.actual_hours = round(_hours_between(shift.actual_start, shift.actual_end), 2)
    # hourly_rate is cents/hour, so hours × rate is already cents — no ×100 here.
    shift.labor_cost = int(round(shift.actual_hours * (staff.hourly_rate or 0)))
    db.commit()
    db.refresh(shift)
    return _shift_out(shift, staff.name)


@router.delete("/shifts/{shift_id}")
async def delete_shift(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    shift = _load_owned_shift(db, restaurant.id, shift_id)
    db.delete(shift)
    db.commit()
    return {"message": "Shift deleted", "id": shift_id}
