"""Weekly shift templates → LaborShift rows + rule checks."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

import models
from time_utils import utcnow

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _parse_hhmm(value: str) -> time:
    hour, minute = value.strip().split(":")
    return time(hour=int(hour), minute=int(minute))


def _slot_hours(start: str, end: str) -> float:
    s = _parse_hhmm(start)
    e = _parse_hhmm(end)
    start_dt = datetime.combine(date.min, s)
    end_dt = datetime.combine(date.min, e)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return (end_dt - start_dt).total_seconds() / 3600.0


def get_or_create_team_rules(db: Session, restaurant_id: int) -> models.TeamRules:
    row = db.query(models.TeamRules).filter(models.TeamRules.restaurant_id == restaurant_id).first()
    if row:
        return row
    row = models.TeamRules(restaurant_id=restaurant_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def weekly_hours_for_member(db: Session, restaurant_id: int, staff_member_id: int) -> float:
    slots = db.query(models.StaffWeeklyShift).filter(
        models.StaffWeeklyShift.restaurant_id == restaurant_id,
        models.StaffWeeklyShift.staff_member_id == staff_member_id,
    ).all()
    return sum(_slot_hours(s.start_time, s.end_time) for s in slots)


def scheduled_weekdays(db: Session, restaurant_id: int, staff_member_id: int) -> set[int]:
    rows = db.query(models.StaffWeeklyShift).filter(
        models.StaffWeeklyShift.restaurant_id == restaurant_id,
        models.StaffWeeklyShift.staff_member_id == staff_member_id,
    ).all()
    return {r.weekday for r in rows}


def check_team_rules(
    db: Session,
    restaurant_id: int,
    slots_by_member: dict[int, list[dict]],
) -> list[str]:
    rules = get_or_create_team_rules(db, restaurant_id)
    if not rules.alerts_enabled:
        return []
    warnings: list[str] = []
    for staff_id, slots in slots_by_member.items():
        hours = sum(_slot_hours(s["start_time"], s["end_time"]) for s in slots)
        if hours > rules.max_hours_per_week:
            member = db.query(models.StaffMember).filter(models.StaffMember.id == staff_id).first()
            name = member.name if member else f"Staff #{staff_id}"
            warnings.append(f"{name} is scheduled for {hours:.1f} hours this week (max {rules.max_hours_per_week:g}).")
        days = {int(s["weekday"]) for s in slots}
        if len(days) > rules.max_consecutive_days:
            member = db.query(models.StaffMember).filter(models.StaffMember.id == staff_id).first()
            name = member.name if member else f"Staff #{staff_id}"
            warnings.append(
                f"{name} is scheduled {len(days)} days with no rest in the week "
                f"(max {rules.max_consecutive_days} days in a row — check against your staff contracts)."
            )
    return warnings


def materialize_week(
    db: Session,
    restaurant_id: int,
    week_start: date,
) -> int:
    """Create LaborShift rows from weekly templates for Mon–Sun of week_start."""
    templates = db.query(models.StaffWeeklyShift).filter(
        models.StaffWeeklyShift.restaurant_id == restaurant_id,
    ).all()
    overrides = db.query(models.StaffShiftOverride).filter(
        models.StaffShiftOverride.restaurant_id == restaurant_id,
        models.StaffShiftOverride.shift_date >= week_start,
        models.StaffShiftOverride.shift_date < week_start + timedelta(days=7),
    ).all()
    override_map: dict[tuple[int, date], models.StaffShiftOverride] = {
        (o.staff_member_id, o.shift_date): o for o in overrides
    }
    created = 0
    by_member_weekday: dict[tuple[int, int], models.StaffWeeklyShift] = {
        (t.staff_member_id, t.weekday): t for t in templates
    }
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        weekday = day.weekday()
        members_today: set[int] = {k[0] for k in by_member_weekday if k[1] == weekday}
        for staff_id in members_today:
            template = by_member_weekday[(staff_id, weekday)]
            ov = override_map.get((staff_id, day))
            if ov and ov.kind == "missed":
                continue
            active_staff_id = staff_id
            if ov and ov.kind == "swap" and ov.swap_staff_member_id:
                active_staff_id = ov.swap_staff_member_id
            exists = db.query(models.LaborShift).filter(
                models.LaborShift.restaurant_id == restaurant_id,
                models.LaborShift.staff_member_id == active_staff_id,
                models.LaborShift.shift_date == day,
            ).first()
            if exists:
                continue
            start = _parse_hhmm(template.start_time)
            end = _parse_hhmm(template.end_time)
            scheduled_start = datetime.combine(day, start)
            scheduled_end = datetime.combine(day, end)
            if scheduled_end <= scheduled_start:
                scheduled_end += timedelta(days=1)
            hours = _slot_hours(template.start_time, template.end_time)
            member = db.query(models.StaffMember).filter(models.StaffMember.id == active_staff_id).first()
            labor_cost = None
            if member and member.daily_pay_rate_cents:
                labor_cost = member.daily_pay_rate_cents
            elif member and member.hourly_rate:
                labor_cost = int(round(hours * member.hourly_rate))
            shift = models.LaborShift(
                restaurant_id=restaurant_id,
                staff_member_id=active_staff_id,
                shift_date=day,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                scheduled_hours=hours,
                labor_cost=labor_cost,
            )
            db.add(shift)
            created += 1
    db.commit()
    return created


def team_overview(db: Session, restaurant_id: int, today: date) -> dict:
    rules = get_or_create_team_rules(db, restaurant_id)
    week_start = today - timedelta(days=today.weekday())
    members = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant_id,
        models.StaffMember.is_active.is_(True),
    ).all()
    slots = db.query(models.StaffWeeklyShift).filter(
        models.StaffWeeklyShift.restaurant_id == restaurant_id,
    ).all()
    slots_by_member: dict[int, list] = defaultdict(list)
    for s in slots:
        slots_by_member[s.staff_member_id].append(s)
    shifts_today = db.query(models.LaborShift).filter(
        models.LaborShift.restaurant_id == restaurant_id,
        models.LaborShift.shift_date == today,
    ).all()
    on_shift = []
    for shift in shifts_today:
        member = next((m for m in members if m.id == shift.staff_member_id), None)
        if member:
            on_shift.append(
                {
                    "staff_member_id": member.id,
                    "name": member.name,
                    "role_title": member.role_title,
                    "scheduled_hours": shift.scheduled_hours,
                }
            )
    week_grid = []
    for m in members:
        rows = []
        for s in slots_by_member.get(m.id, []):
            rows.append(
                {
                    "weekday": s.weekday,
                    "day_name": WEEKDAY_NAMES[s.weekday],
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                }
            )
        week_grid.append(
            {
                "staff_member_id": m.id,
                "name": m.name,
                "role_title": m.role_title,
                "slots": sorted(rows, key=lambda r: r["weekday"]),
                "weekly_hours": round(weekly_hours_for_member(db, restaurant_id, m.id), 1),
            }
        )
    warnings = check_team_rules(
        db,
        restaurant_id,
        {
            mid: [
                {"weekday": s.weekday, "start_time": s.start_time, "end_time": s.end_time}
                for s in slots_by_member.get(mid, [])
            ]
            for mid in {m.id for m in members}
        },
    )
    labour_cost_cents = sum(s.labor_cost or 0 for s in shifts_today)
    return {
        "today": str(today),
        "week_start": str(week_start),
        "on_shift_today": on_shift,
        "week_schedule": week_grid,
        "overwork_warnings": warnings,
        "labour_cost_today_cents": labour_cost_cents,
        "shift_sales_status": "coming",
        "rules": {
            "alerts_enabled": rules.alerts_enabled,
            "max_hours_per_week": rules.max_hours_per_week,
            "max_consecutive_days": rules.max_consecutive_days,
        },
    }