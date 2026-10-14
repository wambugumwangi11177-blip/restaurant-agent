"""Support: no customer ticket sits unanswered; stale ones reach the operator."""
from datetime import timedelta

import models
from time_utils import utcnow
from .. import kernel, tools  # noqa: F401

NAME = "support"
ACK_AFTER = timedelta(hours=24)
STALE_AFTER = timedelta(hours=72)


def run(db, today=None):
    out, now = [], utcnow()
    open_ = db.query(models.SupportTicket).filter(models.SupportTicket.status.in_(
        [models.SupportTicketStatus.OPEN, models.SupportTicketStatus.IN_PROGRESS])).all()
    for t in open_:
        msgs = db.query(models.SupportTicketMessage).filter_by(ticket_id=t.id).all()
        replied = any(m.sender_id != t.created_by_id for m in msgs)
        age = now - (t.created_at or now)
        if not replied and age >= ACK_AFTER:
            summary = f"Acknowledge support ticket #{t.id}: {t.subject}"
            if not kernel.already_proposed(db, "ticket_reply", summary, 30):
                out.append(kernel.propose(
                    db, "support.ack_agent", "ticket_reply",
                    {"ticket_id": t.id, "message": (
                        "Thanks for reaching out - we've received your ticket and a team member "
                        "is looking into it. We'll update you here as soon as we have an answer.")},
                    summary, restaurant_id=t.restaurant_id))
        if age >= STALE_AFTER:
            summary = f"Stale ticket #{t.id} open {age.days} days: {t.subject}"
            if not kernel.already_proposed(db, "operator_alert", summary, 3):
                out.append(kernel.propose(
                    db, "support.escalation_agent", "operator_alert",
                    {"title": f"Ticket #{t.id} open {age.days} days", "body": t.subject,
                     "severity": "high"}, summary, restaurant_id=t.restaurant_id))
    return out
