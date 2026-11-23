"""Weekly shift templates → LaborShift rows + rule checks."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

import models
from time_utils import utcnow

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
NAIROBI = ZoneInfo("Africa/Nairobi")


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


def nairobi_now() -> datetime:
    return utcnow().replace(tzinfo=timezone.utc).astimezone(NAIROBI)


def nairobi_today() -> date:
    return nairobi_now().date()


def longest_consecutive_run(weekdays: set[int]) -> int:
    if not weekdays:
        return 0
    sorted_days = sorted(weekdays)
    best = cur = 1
    for i in range(1, len(sorted_days)):
        if sorted_days[i] == sorted_days[i - 1] + 1:
            cur += 1
        else:
            best = max(best, cur)
            cur = 1
    return max(best, cur)


def compact_schedule_labels(slots: list[dict]) -> list[str]:
    """e.g. Mon–Thu 09:00–17:00 from per-weekday slot rows."""
    if not slots:
        return []
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for s in slots:
        groups[(s["start_time"], s["end_time"])].append(int(s["weekday"]))
    labels: list[str] = []
    for (start, end), days in groups.items():
        days = sorted(set(days))
        ranges: list[str] = []
        i = 0
        while i < len(days):
            j = i
            while j + 1 < len(days) and days[j + 1] == days[j] + 1:
                j += 1
            ranges.append(DAY_ABBR[days[i]] if i == j else f"{DAY_ABBR[days[i]]}–{DAY_ABBR[days[j]]}")
            i = j + 1
        time_part = f" {start}–{end}"
        labels.extend(f"{r}{time_part}" for r in ranges)
    return sorted(labels, key=lambda x: x[:3])


def _time_in_shift(now_local: datetime, start_str: str, end_str: str) -> bool:
    s = _parse_hhmm(start_str)
    e = _parse_hhmm(end_str)
    start_dt = datetime.combine(now_local.date(), s, tzinfo=NAIROBI)
    end_dt = datetime.combine(now_local.date(), e, tzinfo=NAIROBI)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    return start_dt <= now_local <= end_dt


def people_on_shift_now(db: Session, restaurant_id: int, now_local: datetime | None = None) -> list[dict]:
    """Floor staff whose weekly slot window contains now (Africa/Nairobi)."""
    now_local = now_local or nairobi_now()
    weekday = now_local.weekday()
    today = now_local.date()
    members = {
        m.id: m
        for m in db.query(models.StaffMember).filter(
            models.StaffMember.restaurant_id == restaurant_id,
            models.StaffMember.is_active.is_(True),
        ).all()
    }
    slots = db.query(models.StaffWeeklyShift).filter(
        models.StaffWeeklyShift.restaurant_id == restaurant_id,
        models.StaffWeeklyShift.weekday == weekday,
    ).all()
    overrides = {
        (o.staff_member_id, o.shift_date): o
        for o in db.query(models.StaffShiftOverride).filter(
            models.StaffShiftOverride.restaurant_id == restaurant_id,
            models.StaffShiftOverride.shift_date == today,
        ).all()
    }
    active: dict[int, tuple[models.StaffWeeklyShift, int]] = {}
    for slot in slots:
        ov = overrides.get((slot.staff_member_id, today))
        if ov and ov.kind == "missed":
            continue
        staff_id = slot.staff_member_id
        if ov and ov.kind == "swap" and ov.swap_staff_member_id:
            staff_id = ov.swap_staff_member_id
        if _time_in_shift(now_local, slot.start_time, slot.end_time):
            active[staff_id] = (slot, staff_id)
    rows: list[dict] = []
    for staff_id, (slot, _) in active.items():
        member = members.get(staff_id)
        if not member:
            continue
        rows.append(
            {
                "staff_member_id": member.id,
                "name": member.name,
                "role_title": member.role_title,
                "window": f"{slot.start_time}–{slot.end_time}",
            }
        )
    rows.sort(key=lambda r: r["name"].lower())
    return rows


def build_schedule_board(db: Session, restaurant_id: int) -> dict:
    today = nairobi_today()
    weekday = today.weekday()
    members = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant_id,
        models.StaffMember.is_active.is_(True),
    ).order_by(models.StaffMember.name).all()
    slot_rows = db.query(models.StaffWeeklyShift).filter(
        models.StaffWeeklyShift.restaurant_id == restaurant_id,
    ).all()
    slots_by_member: dict[int, list] = defaultdict(list)
    for s in slot_rows:
        slots_by_member[s.staff_member_id].append(s)
    flat_slots = [
        {
            "id": s.id,
            "staff_member_id": s.staff_member_id,
            "weekday": s.weekday,
            "start_time": s.start_time,
            "end_time": s.end_time,
        }
        for s in slot_rows
    ]
    roster: list[dict] = []
    member_summaries: list[dict] = []
    scheduled_today: list[int] = []
    for m in members:
        raw = [
            {"weekday": s.weekday, "start_time": s.start_time, "end_time": s.end_time}
            for s in slots_by_member.get(m.id, [])
        ]
        hours = round(sum(_slot_hours(s["start_time"], s["end_time"]) for s in raw), 1)
        compact = compact_schedule_labels(raw)
        weekdays = sorted({int(s["weekday"]) for s in raw})
        if weekday in weekdays:
            scheduled_today.append(m.id)
        roster.append({"id": m.id, "name": m.name, "role_title": m.role_title, "has_login": m.user_id is not None})
        member_summaries.append(
            {
                "staff_member_id": m.id,
                "name": m.name,
                "role_title": m.role_title,
                "compact_lines": compact,
                "weekly_hours": hours,
                "weekdays": weekdays,
            }
        )
    return {
        "slots": flat_slots,
        "roster": roster,
        "members": member_summaries,
        "today_weekday": weekday,
        "scheduled_today_ids": scheduled_today,
        "timezone": "Africa/Nairobi",
        "today": str(today),
    }


def touch_login_staff_shift(db: Session, restaurant_id: int, user_id: int, when: datetime | None = None) -> None:
    """Managers/logging staff: record actual start on day open or handover."""
    when = when or utcnow()
    member = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant_id,
        models.StaffMember.user_id == user_id,
        models.StaffMember.is_active.is_(True),
    ).first()
    if member is None:
        return
    day = when.date()
    shift = db.query(models.LaborShift).filter(
        models.LaborShift.restaurant_id == restaurant_id,
        models.LaborShift.staff_member_id == member.id,
        models.LaborShift.shift_date == day,
    ).first()
    if shift is None:
        db.add(
            models.LaborShift(
                restaurant_id=restaurant_id,
                staff_member_id=member.id,
                shift_date=day,
                actual_start=when,
                notes="floor",
            )
        )
    elif shift.actual_start is None:
        shift.actual_start = when
    db.commit()


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
        streak = longest_consecutive_run(days)
        if streak > rules.max_consecutive_days:
            member = db.query(models.StaffMember).filter(models.StaffMember.id == staff_id).first()
            name = member.name if member else f"Staff #{staff_id}"
            warnings.append(
                f"{name} is scheduled {streak} days in a row "
                f"(max {rules.max_consecutive_days} — check against your staff contracts)."
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


def team_overview(db: Session, restaurant_id: int, today: date | None = None) -> dict:
    today = today or nairobi_today()
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
    on_shift = people_on_shift_now(db, restaurant_id)
    shifts_today = db.query(models.LaborShift).filter(
        models.LaborShift.restaurant_id == restaurant_id,
        models.LaborShift.shift_date == today,
    ).all()
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
        compact = compact_schedule_labels(
            [{"weekday": s.weekday, "start_time": s.start_time, "end_time": s.end_time} for s in slots_by_member.get(m.id, [])]
        )
        hours = round(sum(_slot_hours(s.start_time, s.end_time) for s in slots_by_member.get(m.id, [])), 1)
        week_grid.append(
            {
                "staff_member_id": m.id,
                "name": m.name,
                "role_title": m.role_title,
                "slots": sorted(rows, key=lambda r: r["weekday"]),
                "compact_lines": compact,
                "weekly_hours": hours,
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
        "on_shift_now": on_shift,
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