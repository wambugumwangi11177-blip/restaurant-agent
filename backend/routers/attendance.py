"""
backend/routers/attendance.py
──────────────────────────────
Staff clock-in / clock-out (migration 037) — building on LaborShift, a model
that already existed (actual_start/actual_end were always its clock-in/out
columns) but had no router at all until the owner's 2026-07-19 operational
walkthrough: "the staff, the term they clock in and clock out."

GPS check-in rides on top of the same clock-in call: if the client sends
lat/lng and the restaurant has its own latitude/longitude set (via
PUT /restaurant), the distance between them is checked against
_PROXIMITY_THRESHOLD_METERS. A clock-in is never blocked by this — it only
sets clock_in_flagged and notifies oversight, the same "flag, don't block"
posture as directive 016's variance detection. If the restaurant has no
coordinates set, the check is skipped entirely rather than guessed at.

Any authenticated staff account may clock themselves in/out — there is no
_CAN_WRITE role gate here, because everyone (Owner included) clocks in for
their own shift. What's gated is *whose* shift: a user can only act on the
StaffMember row linked to their own user_id.
"""

import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, timedelta

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from time_utils import utcnow

router = APIRouter(prefix="/attendance", tags=["attendance"])

# Beyond this, a clock-in is flagged for oversight (not blocked). 200m is
# generous enough to cover a large property/parking lot while still catching
# a clock-in from across town.
_PROXIMITY_THRESHOLD_METERS = 200.0


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0  # Earth radius, meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _own_staff_member(db: Session, restaurant_id: int, user_id: int) -> models.StaffMember:
    member = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant_id,
        models.StaffMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(
            status_code=400,
            detail="No staff record is linked to your account — ask an owner/manager to add you to the roster first.",
        )
    return member


def _shift_out(shift: models.LaborShift, staff_name: str) -> dict:
    return {
        "id": shift.id,
        "restaurant_id": shift.restaurant_id,
        "staff_member_id": shift.staff_member_id,
        "staff_name": staff_name,
        "shift_date": shift.shift_date,
        "actual_start": shift.actual_start,
        "actual_end": shift.actual_end,
        "actual_hours": shift.actual_hours,
        "labor_cost": shift.labor_cost,
        "clock_in_flagged": shift.clock_in_flagged,
    }


@router.get("/status", response_model=schemas.AttendanceStatusOut)
async def attendance_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    member = _own_staff_member(db, restaurant.id, current_user.id)

    open_shift = db.query(models.LaborShift).filter(
        models.LaborShift.staff_member_id == member.id,
        models.LaborShift.actual_start.isnot(None),
        models.LaborShift.actual_end.is_(None),
    ).order_by(models.LaborShift.actual_start.desc()).first()

    if not open_shift:
        return {"clocked_in": False, "shift": None}
    return {"clocked_in": True, "shift": _shift_out(open_shift, member.name)}


@router.post("/clock-in", response_model=schemas.LaborShiftOut, status_code=201)
async def clock_in(
    body: schemas.ClockInBody,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    member = _own_staff_member(db, restaurant.id, current_user.id)

    already_open = db.query(models.LaborShift).filter(
        models.LaborShift.staff_member_id == member.id,
        models.LaborShift.actual_start.isnot(None),
        models.LaborShift.actual_end.is_(None),
    ).first()
    if already_open:
        raise HTTPException(status_code=409, detail="You're already clocked in.")

    now = utcnow()
    flagged = False
    if body.lat is not None and body.lng is not None and restaurant.latitude is not None and restaurant.longitude is not None:
        distance = _haversine_meters(body.lat, body.lng, restaurant.latitude, restaurant.longitude)
        flagged = distance > _PROXIMITY_THRESHOLD_METERS

    shift = models.LaborShift(
        restaurant_id=restaurant.id,
        staff_member_id=member.id,
        shift_date=now.date(),
        actual_start=now,
        clock_in_lat=body.lat,
        clock_in_lng=body.lng,
        clock_in_flagged=flagged,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)

    from events.bus import emit_async, EventType
    emit_async(EventType.SHIFT_STARTED, {
        "restaurant_id": restaurant.id,
        "staff_name": member.name,
    })
    if flagged:
        emit_async(EventType.SHIFT_CLOCK_IN_FLAGGED, {
            "restaurant_id": restaurant.id,
            "staff_name": member.name,
            "distance_meters": distance,
        })

    return _shift_out(shift, member.name)


@router.post("/clock-out", response_model=schemas.LaborShiftOut)
async def clock_out(
    body: schemas.ClockOutBody,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    member = _own_staff_member(db, restaurant.id, current_user.id)

    shift = db.query(models.LaborShift).filter(
        models.LaborShift.staff_member_id == member.id,
        models.LaborShift.actual_start.isnot(None),
        models.LaborShift.actual_end.is_(None),
    ).order_by(models.LaborShift.actual_start.desc()).first()
    if not shift:
        raise HTTPException(status_code=400, detail="You're not currently clocked in.")

    now = utcnow()
    shift.actual_end = now
    shift.clock_out_lat = body.lat
    shift.clock_out_lng = body.lng
    hours = max((now - shift.actual_start).total_seconds() / 3600.0, 0.0)
    shift.actual_hours = round(hours, 2)
    shift.labor_cost = round(hours * (member.hourly_rate or 0))

    db.commit()
    db.refresh(shift)

    from events.bus import emit_async, EventType
    emit_async(EventType.SHIFT_ENDED, {
        "restaurant_id": restaurant.id,
        "staff_name": member.name,
        "actual_hours": shift.actual_hours,
    })

    return _shift_out(shift, member.name)


# Manager/Owner visibility — a basic timesheet. Directive 015 has no
# dedicated matrix row for attendance; reuses the `staff` domain's gate
# (Manager+) since roster/labor visibility is that domain's concern.
@router.get("/", response_model=List[schemas.LaborShiftOut])
async def list_shifts(
    staff_member_id: Optional[int] = Query(None),
    days: int = Query(7, gt=0, le=90),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(models.StaffRole.MANAGER)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    since = utcnow().date() - timedelta(days=days)
    q = db.query(models.LaborShift).filter(
        models.LaborShift.restaurant_id == restaurant.id,
        models.LaborShift.shift_date >= since,
    )
    if staff_member_id is not None:
        q = q.filter(models.LaborShift.staff_member_id == staff_member_id)

    shifts = q.order_by(models.LaborShift.shift_date.desc(), models.LaborShift.actual_start.desc()).limit(500).all()
    member_ids = {s.staff_member_id for s in shifts}
    members_by_id = {
        m.id: m for m in db.query(models.StaffMember).filter(models.StaffMember.id.in_(member_ids)).all()
    } if member_ids else {}
    return [_shift_out(s, members_by_id.get(s.staff_member_id).name if members_by_id.get(s.staff_member_id) else "Unknown") for s in shifts]
