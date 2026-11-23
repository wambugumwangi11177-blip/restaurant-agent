"""Approval cards, reminders, and requester notifications (plain language)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

import models
from ai.notify import notify_user
from time_utils import utcnow

NAIROBI = ZoneInfo("Africa/Nairobi")

# pending kinds → who must act (staff_role string)
_ACTOR_ROLE: dict[str, str] = {
    "waste": "owner",
    "spoilage": "owner",
    "close": "owner",
    "cost": "owner",
    "handover": "owner",
    "schedule": "owner",
    "delivery": "owner",
    "zone_photo": "owner",
}

_REMINDER_DELAYS = [
    timedelta(0),
    timedelta(minutes=30),
    timedelta(hours=2),
    None,  # next day 09:00
]


def _next_nairobi_9am_naive_utc(after_naive_utc: datetime) -> datetime:
    """Next 09:00 Africa/Nairobi, returned as naive UTC (matches DB datetimes)."""
    base = after_naive_utc if after_naive_utc.tzinfo is None else after_naive_utc.replace(tzinfo=None)
    local = base.replace(tzinfo=timezone.utc).astimezone(NAIROBI)
    target = local.replace(hour=9, minute=0, second=0, microsecond=0)
    if local >= target:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc).replace(tzinfo=None)


def _actor_label(role: str) -> str:
    role = (role or "owner").lower()
    return {
        "owner": "Owner",
        "manager": "Manager",
        "controller": "Accountant",
        "stockkeeper": "Store",
    }.get(role, role.title())


def viewer_is_actor(user: models.User, actor_role: str) -> bool:
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return actor_role == "owner"
    if user.staff_role and user.staff_role.value == actor_role:
        return True
    return False


def enrich_approval_item(item: dict, viewer: models.User) -> dict:
    kind = item.get("kind") or ""
    actor_role = _ACTOR_ROLE.get(kind, "owner")
    is_actor = viewer_is_actor(viewer, actor_role)
    waiting = _actor_label(actor_role)
    if is_actor and item.get("status") == "needs_approval":
        card_title = "This needs you"
        card_subtitle = item.get("action") or item.get("headline") or ""
    elif item.get("status") == "needs_approval":
        card_title = f"Waiting on {waiting}"
        card_subtitle = item.get("action") or item.get("headline") or ""
    else:
        card_title = ""
        card_subtitle = ""
    out = dict(item)
    out["approval_card_title"] = card_title
    out["approval_card_subtitle"] = card_subtitle
    out["approval_viewer_is_actor"] = is_actor
    out["approval_waiting_on"] = waiting if item.get("status") == "needs_approval" else None
    return out


def ensure_reminder_row(
    db: Session,
    restaurant_id: int,
    kind: str,
    entity_id: int,
    requester_user_id: int | None,
    actor_role: str = "owner",
) -> models.ApprovalReminder:
    row = db.query(models.ApprovalReminder).filter(
        models.ApprovalReminder.restaurant_id == restaurant_id,
        models.ApprovalReminder.kind == kind,
        models.ApprovalReminder.entity_id == entity_id,
    ).first()
    if row:
        return row
    row = models.ApprovalReminder(
        restaurant_id=restaurant_id,
        kind=kind,
        entity_id=entity_id,
        requester_user_id=requester_user_id,
        actor_staff_role=actor_role,
        stage=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def process_due_reminders(db: Session, restaurant_id: int) -> None:
    now = utcnow()
    pending = db.query(models.ApprovalReminder).filter(
        models.ApprovalReminder.restaurant_id == restaurant_id,
        models.ApprovalReminder.resolved_at.is_(None),
    ).all()
    for row in pending:
        if row.stage >= len(_REMINDER_DELAYS):
            continue
        delay = _REMINDER_DELAYS[row.stage]
        due = row.created_at or now
        if delay is None:
            due_at = _next_nairobi_9am_naive_utc(due)
        else:
            due_at = due + delay
        if row.last_sent_at and row.stage > 0:
            continue
        if now < due_at and row.stage > 0:
            continue
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
        if not restaurant:
            continue
        targets = db.query(models.User).filter(
            models.User.tenant_id == restaurant.tenant_id,
            models.User.is_active.is_(True),
        ).all()
        actor_users = [
            u for u in targets
            if viewer_is_actor(u, row.actor_staff_role)
        ]
        title = "Still needs a decision"
        body = f"A {row.kind.replace('_', ' ')} item is still waiting."
        for u in actor_users:
            notify_user(db, u.id, title, body, "approval_reminder", url="/eleven/approvals")
        row.last_sent_at = now
        row.stage += 1
        db.commit()


def resolve_reminder(db: Session, restaurant_id: int, kind: str, entity_id: int) -> None:
    row = db.query(models.ApprovalReminder).filter(
        models.ApprovalReminder.restaurant_id == restaurant_id,
        models.ApprovalReminder.kind == kind,
        models.ApprovalReminder.entity_id == entity_id,
    ).first()
    if row:
        row.resolved_at = utcnow()
        db.commit()


def notify_requester_outcome(
    db: Session,
    requester_user_id: int | None,
    *,
    title: str,
    body: str,
    url: str = "/store/requests",
) -> None:
    if not requester_user_id:
        return
    notify_user(db, requester_user_id, title, body, "approval_decision", url=url)