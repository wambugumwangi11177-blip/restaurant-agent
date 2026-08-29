"""
backend/ai/escalation/engine.py
──────────────────────────────────
Manager escalation (Sprint 2). Turns a fire-and-forget alert into an active
paging system: a severity-tagged Notification that goes unacknowledged past
its timeout re-notifies a wider audience, and (for critical alerts only) a
further timeout places an automated voice call.

EVENT_SEVERITY is the single source of truth for which events escalate —
ai/orchestrator/push_notifier.py's _fan_out() looks up severity_for() and
stamps it on every Notification it writes, so a new event opts into
escalation just by being added to this table, no new call site needed.

Escalation ladder, keyed off Notification.created_at (monotonic — no extra
"first escalated at" column needed, the level transitions are strictly
ordered and each only fires once per notification):

  Level 0 -> 1  (critical: 15 min, high: 30 min unacknowledged)
      Page every active MANAGER for the restaurant: in-app/push + WhatsApp/SMS.
  Level 1 -> 2  (critical only: +30 more minutes, i.e. 45 min total)
      Place an automated voice call to the owner reading the alert.
      High-severity alerts have no level 2 — they stop at "every manager knows".

run_escalation_sweep() is the APScheduler job (every 5 min, main.py) that
walks unacknowledged severe notifications and advances the ladder for each.
Acknowledging (routers/notifications.py POST /{id}/acknowledge) stops the
clock — the sweep only ever looks at acknowledged_at IS NULL rows.
"""

import logging

from sqlalchemy.orm import Session

import models
from time_utils import utcnow
from ai.notify import notify_users
from routers.deps import get_staff_users_for_restaurant

logger = logging.getLogger("ai.escalation")

# EventType.value -> severity. Anything not listed here is not escalated —
# most events are operational, not exceptions (see push_notifier.py's own
# "alert fatigue" reasoning for the same posture: escalation is for the
# events an owner would want to be woken up for, not a running commentary).
EVENT_SEVERITY: dict[str, str] = {
    "stock.critical": "critical",
    "stock.variance_flagged": "high",
    "fraud.suspicious_transaction_flagged": "critical",
    "cash.reconciliation_flagged": "high",
}

# Minutes unacknowledged before each ladder step fires. A severity absent
# from a given tier's dict simply never reaches that tier (e.g. "high" has
# no LEVEL_2 entry, so it stops after paging managers).
LEVEL_1_TIMEOUT_MINUTES: dict[str, int] = {"critical": 15, "high": 30}
LEVEL_2_TIMEOUT_MINUTES: dict[str, int] = {"critical": 45}


def severity_for(event_type: str) -> str | None:
    return EVENT_SEVERITY.get(event_type)


def run_escalation_sweep(db: Session) -> dict:
    """
    Scan every unacknowledged severity-tagged Notification and advance its
    escalation level if it's past the relevant timeout. Never raises — one
    bad row must not stop the sweep for the rest (mirrors every other
    scheduled job's per-item try/except contract, e.g. main.py's variance
    check looping per-restaurant).
    """
    now = utcnow()
    escalated_to_managers = 0
    escalated_to_call = 0

    pending = db.query(models.Notification).filter(
        models.Notification.severity.isnot(None),
        models.Notification.acknowledged_at.is_(None),
    ).all()

    for notif in pending:
        severity = notif.severity
        if notif.created_at is None:
            continue
        age_minutes = (now - notif.created_at).total_seconds() / 60.0

        try:
            if notif.escalation_level == 0:
                timeout = LEVEL_1_TIMEOUT_MINUTES.get(severity)
                if timeout is not None and age_minutes >= timeout:
                    _page_managers(db, notif)
                    notif.escalation_level = 1
                    db.commit()
                    escalated_to_managers += 1
            elif notif.escalation_level == 1:
                timeout = LEVEL_2_TIMEOUT_MINUTES.get(severity)
                if timeout is not None and age_minutes >= timeout:
                    _call_owner(db, notif)
                    notif.escalation_level = 2
                    db.commit()
                    escalated_to_call += 1
        except Exception as exc:
            db.rollback()
            logger.error(f"[Escalation] Failed to escalate notification {notif.id}: {exc}")

    return {"escalated_to_managers": escalated_to_managers, "escalated_to_call": escalated_to_call}


def _restaurant_for_notification(db: Session, notif: "models.Notification"):
    """Notification only carries user_id — resolve the restaurant via that
    user's tenant (one restaurant per tenant; same assumption
    routers/deps.py::get_or_create_restaurant makes)."""
    user = db.query(models.User).filter(models.User.id == notif.user_id).first()
    if not user:
        return None
    return db.query(models.Restaurant).filter(models.Restaurant.tenant_id == user.tenant_id).first()


def _page_managers(db: Session, notif: "models.Notification") -> None:
    restaurant = _restaurant_for_notification(db, notif)
    if not restaurant:
        logger.warning(f"[Escalation] No restaurant resolved for notification {notif.id}")
        return

    managers = get_staff_users_for_restaurant(db, restaurant, [models.StaffRole.MANAGER])
    manager_ids = [m.id for m in managers]
    timeout = LEVEL_1_TIMEOUT_MINUTES.get(notif.severity, 15)
    escalated_body = (
        f"UNACKNOWLEDGED {notif.severity.upper()} ALERT "
        f"(no response in {timeout} min):\n\n{notif.body}"
    )

    if not manager_ids:
        logger.warning(
            f"[Escalation] Notification {notif.id} escalated to level 1 but "
            f"restaurant {restaurant.id} has no active MANAGER to page."
        )
        return

    notify_users(db, manager_ids, f"[ESCALATED] {notif.title}", escalated_body,
                 notif.event_type, notif.url, severity=notif.severity)

    # WhatsApp/SMS to every manager with a phone on file. StaffMember.phone is
    # the reachable-number field (models.py's own docstring); join via
    # user_id since that's how a roster entry links to a dashboard login.
    staff_rows = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant.id,
        models.StaffMember.user_id.in_(manager_ids),
        models.StaffMember.phone.isnot(None),
        models.StaffMember.is_active == True,  # noqa: E712
    ).all()

    from ai.whatsapp.brain import send_whatsapp_message
    for staff in staff_rows:
        send_whatsapp_message(
            staff.phone, escalated_body, db=db, restaurant_id=restaurant.id,
            message_type="escalation", channel="whatsapp", fallback_sms=True,
        )


def _call_owner(db: Session, notif: "models.Notification") -> None:
    restaurant = _restaurant_for_notification(db, notif)
    if not restaurant:
        return

    from ai.whatsapp.brain import owner_phone_for
    phone = owner_phone_for(restaurant)
    if not phone:
        logger.warning(f"[Escalation] No owner phone to call for restaurant {restaurant.id}")
        return

    from ai.whatsapp.twilio_client import call
    call(phone, f"Urgent alert from Leviii. {notif.title}. Please check your dashboard immediately.")