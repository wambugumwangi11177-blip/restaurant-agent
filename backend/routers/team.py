"""Team schedule, roster shifts, and labour overview."""
from __future__ import annotations

import json
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db
from routers.deps import get_or_create_restaurant
from services.labor_schedule import (
    build_schedule_board,
    check_team_rules,
    get_or_create_team_rules,
    materialize_week,
    nairobi_today,
    team_overview,
)
from time_utils import utcnow

router = APIRouter(prefix="/team", tags=["team"])

LOGIN_STAFF_ROLES = {
    models.StaffRole.MANAGER,
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.CONTROLLER,
}

TEAM_FLOOR_MANAGERS = (
    models.StaffRole.OWNER,
    models.StaffRole.MANAGER,
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.CONTROLLER,
)


class WeeklySlotIn(BaseModel):
    staff_member_id: int
    weekday: int = Field(ge=0, le=6)
    start_time: str
    end_time: str


class WeeklyScheduleSave(BaseModel):
    slots: List[WeeklySlotIn]


class TeamRulesIn(BaseModel):
    alerts_enabled: bool = True
    max_hours_per_week: float = Field(default=52, ge=1, le=168)
    max_consecutive_days: int = Field(default=6, ge=1, le=7)


class ShiftOverrideIn(BaseModel):
    staff_member_id: int
    shift_date: date
    kind: str  # missed | swap
    swap_staff_member_id: int | None = None


class RosterStaffIn(BaseModel):
    name: str
    role_title: str
    daily_pay_rate_cents: int | None = Field(default=None, ge=0)
    phone: str | None = None


def _can_see_pay(user: models.User) -> bool:
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return True
    return user.staff_role == models.StaffRole.CONTROLLER


def _member_out(member: models.StaffMember, user: models.User, db: Session) -> dict:
    from routers.staff import _staff_out

    data = _staff_out(member, db)
    if _can_see_pay(user):
        data["daily_pay_rate_cents"] = member.daily_pay_rate_cents
    else:
        data["daily_pay_rate_cents"] = None
    data["has_login"] = member.user_id is not None
    return data


@router.get("/overview")
async def get_overview(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*TEAM_FLOOR_MANAGERS)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    payload = team_overview(db, restaurant.id, nairobi_today())
    if not _can_see_pay(current_user):
        payload["labour_cost_today_cents"] = None
    return payload


@router.get("/rules")
async def get_rules(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(models.StaffRole.OWNER)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    rules = get_or_create_team_rules(db, restaurant.id)
    return {
        "alerts_enabled": rules.alerts_enabled,
        "max_hours_per_week": rules.max_hours_per_week,
        "max_consecutive_days": rules.max_consecutive_days,
        "contract_note": "Checked against your staff contracts.",
    }


@router.put("/rules")
async def put_rules(
    body: TeamRulesIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(models.StaffRole.OWNER)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    rules = get_or_create_team_rules(db, restaurant.id)
    rules.alerts_enabled = body.alerts_enabled
    rules.max_hours_per_week = body.max_hours_per_week
    rules.max_consecutive_days = body.max_consecutive_days
    rules.updated_at = utcnow()
    db.commit()
    return {"status": "saved"}


@router.get("/weekly-slots")
async def list_weekly_slots(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*TEAM_FLOOR_MANAGERS)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    return build_schedule_board(db, restaurant.id)


@router.put("/weekly-slots")
async def save_weekly_slots(
    body: WeeklyScheduleSave,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*TEAM_FLOOR_MANAGERS)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    by_member: dict[int, list[dict]] = {}
    for slot in body.slots:
        by_member.setdefault(slot.staff_member_id, []).append(slot.model_dump())
    warnings = check_team_rules(db, restaurant.id, by_member)
    is_owner = current_user.role in (models.Role.SUPERADMIN, models.Role.ADMIN)
    if warnings and not is_owner:
        req = models.ScheduleChangeRequest(
            restaurant_id=restaurant.id,
            proposed_by_user_id=current_user.id,
            payload_json=json.dumps(body.model_dump()),
            status="needs_approval",
        )
        db.add(req)
        db.commit()
        return {"status": "needs_owner_approval", "warnings": warnings, "request_id": req.id}
    db.query(models.StaffWeeklyShift).filter(
        models.StaffWeeklyShift.restaurant_id == restaurant.id,
    ).delete(synchronize_session=False)
    for slot in body.slots:
        db.add(
            models.StaffWeeklyShift(
                restaurant_id=restaurant.id,
                staff_member_id=slot.staff_member_id,
                weekday=slot.weekday,
                start_time=slot.start_time,
                end_time=slot.end_time,
            )
        )
    db.commit()
    week_start = date.today() - __import__("datetime").timedelta(days=date.today().weekday())
    created = materialize_week(db, restaurant.id, week_start)
    return {"status": "saved", "warnings": warnings, "shifts_materialized": created}


@router.post("/day-override")
async def day_override(
    body: ShiftOverrideIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*TEAM_FLOOR_MANAGERS)),
):
    if body.kind not in ("missed", "swap"):
        raise HTTPException(status_code=400, detail="Choose missed or swap.")
    if body.kind == "swap" and not body.swap_staff_member_id:
        raise HTTPException(status_code=400, detail="Pick who covered the shift.")
    restaurant = get_or_create_restaurant(db, current_user)
    db.add(
        models.StaffShiftOverride(
            restaurant_id=restaurant.id,
            staff_member_id=body.staff_member_id,
            shift_date=body.shift_date,
            kind=body.kind,
            swap_staff_member_id=body.swap_staff_member_id,
            created_by_user_id=current_user.id,
        )
    )
    db.commit()
    week_start = body.shift_date - __import__("datetime").timedelta(days=body.shift_date.weekday())
    materialize_week(db, restaurant.id, week_start)
    return {"status": "saved"}


@router.post("/roster", status_code=201)
async def create_roster_member(
    body: RosterStaffIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*TEAM_FLOOR_MANAGERS)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    member = models.StaffMember(
        restaurant_id=restaurant.id,
        name=body.name,
        role_title=body.role_title,
        daily_pay_rate_cents=body.daily_pay_rate_cents,
        phone=body.phone,
        user_id=None,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    out = _member_out(member, current_user, db)
    return out


@router.get("/roster")
async def list_roster(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*TEAM_FLOOR_MANAGERS)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    rows = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant.id,
        models.StaffMember.is_active.is_(True),
    ).order_by(models.StaffMember.name).all()
    return [_member_out(m, current_user, db) for m in rows]