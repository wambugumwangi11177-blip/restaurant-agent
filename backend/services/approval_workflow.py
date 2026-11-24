"""Approval cards, reminders, and requester notifications (plain language)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

import models
from ai.notify import notify_user
from money_visibility import money_keys_in
from time_utils import utcnow

NAIROBI = ZoneInfo("Africa/Nairobi")

_ACTOR_ROLE: dict[str, str] = {
    "waste": "owner",
    "spoilage": "owner",
    "close": "owner",
    "cost": "owner",
    "handover": "owner",
    "schedule": "owner",
    "delivery": "owner",
    "zone_photo": "owner",
    "restock": "owner",
    "cost_unknown": "owner",
}

_REMINDER_STAGE_COUNT = 4  # immediate, +30m, +2h, next day 09:00 Nairobi

_TYPE_LABEL: dict[str, str] = {
    "waste": "Write-off",
    "spoilage": "Write-off",
    "restock": "Restock",
    "handover": "Handover",
    "delivery": "Delivery",
    "close": "Day close",
    "cost": "New cost",
    "schedule": "Schedule change",
    "zone_photo": "Zone photo",
    "cost_unknown": "Unknown bill",
}


def _next_day_9am_nairobi_after(created_naive_utc: datetime) -> datetime:
    local = created_naive_utc.replace(tzinfo=timezone.utc).astimezone(NAIROBI)
    target_local = datetime.combine(local.date() + timedelta(days=1), datetime.min.time().replace(hour=9), tzinfo=NAIROBI)
    return target_local.astimezone(timezone.utc).replace(tzinfo=None)


def _due_at_for_stage(created: datetime, stage_index: int) -> datetime:
    created = created or utcnow()
    if stage_index == 0:
        return created
    if stage_index == 1:
        return created + timedelta(minutes=30)
    if stage_index == 2:
        return created + timedelta(hours=2)
    return _next_day_9am_nairobi_after(created)


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


def _viewer_sees_money(user: models.User) -> bool:
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return True
    return user.staff_role == models.StaffRole.CONTROLLER


def format_relative_nairobi(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        raw = iso.replace("Z", "+00:00")
        if "T" not in raw:
            return iso
        dt = datetime.fromisoformat(raw)
        local = dt.replace(tzinfo=timezone.utc).astimezone(NAIROBI) if dt.tzinfo is None else dt.astimezone(NAIROBI)
        today = datetime.now(NAIROBI).date()
        if local.date() == today:
            return f"Today {local.strftime('%H:%M')}"
        if local.date() == today - timedelta(days=1):
            return f"Yesterday {local.strftime('%H:%M')}"
        return local.strftime("%d %b %H:%M")
    except ValueError:
        return iso[:16] if len(iso) > 16 else iso


def approval_type_label(kind: str) -> str:
    return _TYPE_LABEL.get(kind, kind.replace("_", " ").title() or "Request")


def approval_reason_line(item: dict) -> str | None:
    kind = item.get("kind") or ""
    if kind in ("waste", "spoilage"):
        reason = (item.get("reason_text") or "").strip() or (item.get("reason_code") or "").strip()
        return reason or None
    ai = item.get("ai") or {}
    note = (ai.get("note") or "").strip() if isinstance(ai, dict) else None
    if note:
        return note
    if kind == "restock":
        return (item.get("headline") or "").strip() or None
    return None


def approval_detail_bullets(item: dict, viewer: models.User) -> list[str]:
    kind = item.get("kind") or ""
    lines: list[str] = []
    if kind in ("waste", "spoilage"):
        qty = item.get("quantity")
        unit = item.get("unit") or ""
        name = item.get("item_name") or "stock"
        if qty is not None:
            lines.append(f"{name} — {qty:g} {unit}".strip())
        reason = (item.get("reason_text") or "").strip() or (item.get("reason_code") or "")
        if reason:
            lines.append(f"Reason: {reason}")
    elif kind == "close":
        lines.append(item.get("headline") or "Day close with a count difference")
    elif kind in ("cost", "cost_unknown"):
        lines.append(item.get("label") or item.get("headline") or "Bill")
        if kind == "cost_unknown":
            lines.append("Key the amount from the bill photo.")
        if _viewer_sees_money(viewer) and item.get("amount_cents") is not None:
            lines.append(f"Amount: {(item['amount_cents'] / 100):,.0f} KES")
    elif kind == "schedule":
        lines.append("Weekly hours break a team rule.")
    elif kind == "restock":
        lines.append(item.get("headline") or "Restock order")
    else:
        if item.get("headline"):
            lines.append(item["headline"])
    who = item.get("person_name") or item.get("created_by")
    if who:
        lines.append(f"Asked by {who}")
    when = format_relative_nairobi(item.get("created_at"))
    if when:
        lines.append(when)
    return lines


def _actor_role_for_item(item: dict) -> str:
    custom = item.get("actor_staff_role")
    if custom:
        return str(custom)
    return _ACTOR_ROLE.get(item.get("kind") or "", "owner")


def enrich_approval_item(item: dict, viewer: models.User) -> dict:
    kind = item.get("kind") or ""
    actor_role = _actor_role_for_item(item)
    is_actor = viewer_is_actor(viewer, actor_role)
    waiting = _actor_label(actor_role)
    type_label = approval_type_label(kind if kind != "spoilage" else "waste")
    reason = approval_reason_line(item)
    bullets = approval_detail_bullets(item, viewer)
    if is_actor and item.get("status") == "needs_approval":
        card_title = type_label
        card_subtitle = bullets[0] if bullets else (item.get("action") or "")
    elif item.get("status") == "needs_approval":
        card_title = f"Waiting on {waiting}"
        card_subtitle = type_label
    else:
        card_title = ""
        card_subtitle = ""
    out = dict(item)
    if not _viewer_sees_money(viewer):
        for key in money_keys_in(out):
            if key in out:
                out.pop(key, None)
    out["approval_type_label"] = type_label
    out["approval_reason_line"] = reason
    out["approval_needs_you"] = bool(is_actor and item.get("status") == "needs_approval")
    out["approval_card_title"] = card_title
    out["approval_card_subtitle"] = card_subtitle
    out["approval_detail_bullets"] = bullets
    out["approval_viewer_is_actor"] = is_actor
    out["approval_waiting_on"] = waiting if item.get("status") == "needs_approval" else None
    out["approval_when_label"] = format_relative_nairobi(item.get("created_at"))
    return out


def _dispatch_reminder(db: Session, row: models.ApprovalReminder, stage_index: int) -> None:
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == row.restaurant_id).first()
    if not restaurant:
        return
    targets = db.query(models.User).filter(
        models.User.tenant_id == restaurant.tenant_id,
        models.User.is_active.is_(True),
    ).all()
    actor_users = [u for u in targets if viewer_is_actor(u, row.actor_staff_role)]
    plain_kind = row.kind.replace("_", " ")
    if stage_index == 0:
        title = "Needs a decision"
        body = f"A {plain_kind} item is waiting for you."
    else:
        title = "Still needs a decision"
        body = f"A {plain_kind} item is still waiting."
    inbox_url = "/store/requests" if (row.actor_staff_role or "owner") != "owner" else "/eleven/approvals"
    for u in actor_users:
        notify_user(db, u.id, title, body, "approval_reminder", url=inbox_url)


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
    created = row is None
    if row is None:
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
    if created or (row.stage == 0 and row.last_sent_at is None):
        _dispatch_reminder(db, row, 0)
        row.stage = 1
        row.last_sent_at = utcnow()
        db.commit()
    return row


def process_due_reminders(db: Session, restaurant_id: int) -> None:
    now = utcnow()
    pending = db.query(models.ApprovalReminder).filter(
        models.ApprovalReminder.restaurant_id == restaurant_id,
        models.ApprovalReminder.resolved_at.is_(None),
    ).all()
    for row in pending:
        while row.stage < _REMINDER_STAGE_COUNT:
            idx = row.stage
            due = _due_at_for_stage(row.created_at or now, idx)
            if now < due:
                break
            _dispatch_reminder(db, row, idx)
            row.last_sent_at = now
            row.stage = idx + 1
            db.commit()


def process_all_due_reminders(db: Session) -> int:
    """Idempotent sweep for APScheduler — returns rows touched."""
    touched = 0
    for (restaurant_id,) in db.query(models.Restaurant.id).all():
        before = db.query(models.ApprovalReminder).filter(
            models.ApprovalReminder.restaurant_id == restaurant_id,
            models.ApprovalReminder.resolved_at.is_(None),
        ).count()
        process_due_reminders(db, restaurant_id)
        after = db.query(models.ApprovalReminder).filter(
            models.ApprovalReminder.restaurant_id == restaurant_id,
            models.ApprovalReminder.resolved_at.is_(None),
        ).count()
        if before or after:
            touched += 1
    return touched


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