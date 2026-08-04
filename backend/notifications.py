"""
backend/notifications.py
─────────────────────────
Owner-alert delivery. In-app first, WhatsApp/SMS as an optional forward.

The inversion this module exists to make: every owner alert used to be raised
like this —

    owner_phone = _owner_phone(restaurant)
    if owner_phone:
        send_whatsapp_message(owner_phone, msg, ...)

— so an alert reached the owner only if (a) a phone number was on file *and*
(b) a Twilio account was configured and working. With neither, which is the
normal state of a deployment before a WhatsApp sender is approved, the system
computed a critical stock warning, wrote an audit log, and then dropped it on
the floor with no trace in the product. The dashboard showed nothing, because
nothing in the dashboard had ever been told.

`deliver()` reverses that dependency: it writes a `Notification` row first,
unconditionally, and only then attempts the phone forward. In-app delivery has
no external dependency, so it cannot silently fail; WhatsApp becomes an
enhancement for owners who aren't at a screen.

Callers should use `deliver()` for anything an owner needs to see. Use
`record()` directly only when a phone forward would be wrong (e.g. an alert
that is purely a dashboard affordance).
"""

import logging

import models
from time_utils import utcnow

logger = logging.getLogger("notifications")

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"
SEVERITIES = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL)

# Max characters kept in a stored body. WhatsApp templates are chatty and the
# feed only ever renders a few lines; the message log (AgentMessage) keeps the
# full text for anything that also went out over a wire.
BODY_LIMIT = 2000


def record(
    db,
    restaurant_id: int,
    title: str,
    body: str = "",
    category: str = "general",
    severity: str = SEVERITY_INFO,
    link: str = "",
) -> "models.Notification | None":
    """
    Write one in-app notification. Returns the row, or None if the write failed.

    Never raises. This is called from event handlers and scheduler jobs whose
    real job is something else (recording a stockout, running a briefing); an
    exception escaping here would abort that work to fail at *telling someone
    about* it — strictly worse than a missing bell entry. Failures are logged.
    """
    if severity not in SEVERITIES:
        severity = SEVERITY_INFO
    try:
        note = models.Notification(
            restaurant_id=restaurant_id,
            title=title[:255],
            body=(body or "")[:BODY_LIMIT],
            category=category,
            severity=severity,
            link=link,
            created_at=utcnow(),
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return note
    except Exception as exc:
        logger.warning("[notifications] failed to record '%s': %s", title, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def deliver(
    db,
    restaurant,
    title: str,
    body: str,
    category: str = "general",
    severity: str = SEVERITY_INFO,
    link: str = "",
    whatsapp_body: str | None = None,
    message_type: str | None = None,
) -> None:
    """
    Deliver an owner alert: always in-app, then best-effort to WhatsApp/SMS.

    `whatsapp_body` lets the caller send richer/emoji-formatted text over the
    wire than the feed stores — pass None to reuse `body`. `message_type` is the
    label written to the AgentMessage log; defaults to `category` so the two
    stay aligned without every call site repeating itself.

    The phone forward is imported lazily and wrapped: `ai.whatsapp.brain` pulls
    in a large dependency graph, and its failure must never cost the in-app
    delivery that has already been committed above.
    """
    record(db, restaurant.id, title, body, category=category, severity=severity, link=link)

    try:
        from ai.whatsapp.brain import send_to_owner

        send_to_owner(db, restaurant, whatsapp_body or body,
                      message_type=message_type or category)
    except Exception as exc:
        # Expected and tolerated whenever no transport is configured — the owner
        # still has the alert in the dashboard.
        logger.info("[notifications] phone forward skipped for '%s': %s", title, exc)


# ── read side ────────────────────────────────────────────────────────────────

def list_for(db, restaurant_id: int, limit: int = 50, unread_only: bool = False) -> list:
    """Newest-first feed for one restaurant."""
    query = db.query(models.Notification).filter(
        models.Notification.restaurant_id == restaurant_id
    )
    if unread_only:
        query = query.filter(models.Notification.read_at.is_(None))
    return query.order_by(models.Notification.created_at.desc()).limit(limit).all()


def unread_count(db, restaurant_id: int) -> int:
    return (
        db.query(models.Notification)
        .filter(
            models.Notification.restaurant_id == restaurant_id,
            models.Notification.read_at.is_(None),
        )
        .count()
    )


def mark_read(db, restaurant_id: int, notification_id: int) -> bool:
    """
    Mark one notification read. Returns False if it doesn't exist *or* belongs
    to another restaurant — the restaurant_id filter is the tenant boundary, so
    an id from another tenant is indistinguishable from a missing one and leaks
    nothing about whether it exists.
    """
    note = (
        db.query(models.Notification)
        .filter(
            models.Notification.id == notification_id,
            models.Notification.restaurant_id == restaurant_id,
        )
        .first()
    )
    if not note:
        return False
    if note.read_at is None:
        note.read_at = utcnow()
        db.commit()
    return True


def mark_all_read(db, restaurant_id: int) -> int:
    """Mark every unread notification for this restaurant read; returns how many."""
    now = utcnow()
    updated = (
        db.query(models.Notification)
        .filter(
            models.Notification.restaurant_id == restaurant_id,
            models.Notification.read_at.is_(None),
        )
        .update({models.Notification.read_at: now}, synchronize_session=False)
    )
    db.commit()
    return updated
