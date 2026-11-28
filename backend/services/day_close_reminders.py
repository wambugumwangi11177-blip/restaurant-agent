"""22:00 EAT (configurable) reminders for stock + cash day close."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

import models
from ai.notify import notify_user
from bill_schedule import business_today
from time_utils import utcnow

NAIROBI = ZoneInfo("Africa/Nairobi")
_REPEAT_MINUTES = (0, 30, 60, 90)


def _parse_hhmm(raw: str) -> time:
    text = (raw or "22:00").strip()
    try:
        hour, minute = text.split(":", 1)
        return time(int(hour), int(minute))
    except (ValueError, TypeError):
        return time(22, 0)


def _today_stock_closed(db: Session, restaurant_id: int, day) -> bool:
    return (
        db.query(models.DayClose.id)
        .filter(
            models.DayClose.restaurant_id == restaurant_id,
            models.DayClose.created_at >= datetime.combine(day, time.min),
        )
        .first()
        is not None
    )


def _today_cash_closed(db: Session, restaurant_id: int, day) -> bool:
    return (
        db.query(models.DayCashClose.id)
        .filter(
            models.DayCashClose.restaurant_id == restaurant_id,
            models.DayCashClose.business_date == day,
        )
        .first()
        is not None
    )


def _staff_for_role(db: Session, tenant_id: int, role: models.StaffRole) -> list[models.User]:
    return (
        db.query(models.User)
        .filter(
            models.User.tenant_id == tenant_id,
            models.User.staff_role == role,
            models.User.is_active.is_(True),
        )
        .all()
    )


def _reminder_key(restaurant_id: int, duty: str, day, stage: int) -> str:
    return f"day_close:{restaurant_id}:{duty}:{day.isoformat()}:{stage}"


def _already_sent(db: Session, user_id: int, duty: str, day, stage: int) -> bool:
    tag = f"{duty}:{day.isoformat()}:{stage}"
    rows = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == user_id,
            models.Notification.event_type == "day_close_reminder",
        )
        .order_by(models.Notification.id.desc())
        .limit(40)
        .all()
    )
    return any(tag in (row.body or "") for row in rows)


def process_day_close_reminders(db: Session, restaurant_id: int) -> int:
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if restaurant is None:
        return 0
    local_now = datetime.now(NAIROBI)
    day = business_today()
    start_local = datetime.combine(day, _parse_hhmm(restaurant.day_close_reminder_time), tzinfo=NAIROBI)
    if local_now < start_local:
        return 0
    elapsed_min = int((local_now - start_local).total_seconds() // 60)
    stage = next((s for s in _REPEAT_MINUTES if elapsed_min >= s), None)
    if stage is None:
        return 0
    sent = 0
    stock_done = _today_stock_closed(db, restaurant_id, day)
    cash_done = _today_cash_closed(db, restaurant_id, day)
    if not stock_done:
        for user in _staff_for_role(db, restaurant.tenant_id, models.StaffRole.STOCKKEEPER):
            if _already_sent(db, user.id, "stock", day, stage):
                continue
            notify_user(
                db,
                user.id,
                title="Close the day — stock",
                body=f"Count stock and close with the accountant. [{_reminder_key(restaurant_id, 'stock', day, stage)}]",
                url="/store/close",
                event_type="day_close_reminder",
            )
            sent += 1
    cash_roles = (models.StaffRole.CONTROLLER, models.StaffRole.MANAGER)
    if not cash_done:
        for role in cash_roles:
            for user in _staff_for_role(db, restaurant.tenant_id, role):
                if _already_sent(db, user.id, "cash", day, stage):
                    continue
                notify_user(
                    db,
                    user.id,
                    title="Close the day — cash",
                    body=f"Record cash and M-Pesa counted for today. [{_reminder_key(restaurant_id, 'cash', day, stage)}]",
                    url="/store/cash-close",
                    event_type="day_close_reminder",
                )
                sent += 1
    if sent:
        db.commit()
    return sent


def process_all_day_close_reminders(db: Session) -> int:
    ids = [row.id for row in db.query(models.Restaurant.id).all()]
    return sum(process_day_close_reminders(db, rid) for rid in ids)


def duty_cards_for_viewer(db: Session, restaurant: models.Restaurant, viewer: models.User) -> list[dict]:
    """Synthetic approval-style cards after the configured close time."""
    local_now = datetime.now(NAIROBI)
    day = business_today()
    start_local = datetime.combine(day, _parse_hhmm(restaurant.day_close_reminder_time), tzinfo=NAIROBI)
    if local_now < start_local:
        return []
    cards: list[dict] = []
    stock_done = _today_stock_closed(db, restaurant.id, day)
    cash_done = _today_cash_closed(db, restaurant.id, day)
    if not stock_done and viewer.staff_role == models.StaffRole.STOCKKEEPER:
        cards.append({
            "id": int(day.strftime("%Y%m%d")),
            "kind": "day_close_stock",
            "status": "needs_approval",
            "headline": "Count stock and close the day.",
            "action": "Close stock",
            "actor_staff_role": "stockkeeper",
            "created_at": start_local.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
            "user_id": viewer.id,
            "requester_user_id": viewer.id,
        })
    elif not stock_done and viewer.staff_role not in (models.StaffRole.STOCKKEEPER, models.StaffRole.KITCHEN):
        keepers = _staff_for_role(db, restaurant.tenant_id, models.StaffRole.STOCKKEEPER)
        who = keepers[0].email.split("@")[0] if keepers else "Store"
        cards.append({
            "id": int(day.strftime("%Y%m%d")),
            "kind": "day_close_stock",
            "status": "needs_approval",
            "headline": f"Waiting for {who} to close stock.",
            "action": "Stock close",
            "actor_staff_role": "stockkeeper",
            "created_at": start_local.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
        })
    if not cash_done and viewer.staff_role in (models.StaffRole.CONTROLLER, models.StaffRole.MANAGER):
        cards.append({
            "id": int(day.strftime("%Y%m%d")) + 1,
            "kind": "day_close_cash",
            "status": "needs_approval",
            "headline": "Record cash and M-Pesa for today.",
            "action": "Close cash",
            "actor_staff_role": "controller",
            "created_at": start_local.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
            "user_id": viewer.id,
            "requester_user_id": viewer.id,
        })
    elif not cash_done and viewer.staff_role == models.StaffRole.STOCKKEEPER:
        cards.append({
            "id": int(day.strftime("%Y%m%d")) + 1,
            "kind": "day_close_cash",
            "status": "needs_approval",
            "headline": "Waiting on Accountant to close cash.",
            "action": "Cash close",
            "actor_staff_role": "controller",
            "created_at": start_local.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
        })
    return cards