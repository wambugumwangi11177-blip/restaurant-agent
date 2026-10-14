"""Governed tools. Each is deterministic; no tool calls an LLM or moves money."""
import models
from ai.notify import notify_users
from routers.deps import get_staff_users_for_restaurant
from time_utils import utcnow
from . import kernel


@kernel.register("scorecard_digest", kernel.INTERNAL,
                 "Send the operator the platform health scorecard (in-app).")
def scorecard_digest(db, payload):
    from ai.continuity.scorecard import platform_scorecard
    card = platform_scorecard(db)
    s = card["summary"]
    operators = db.query(models.User).filter(
        models.User.role == models.Role.SUPERADMIN, models.User.is_active == True).all()  # noqa: E712
    worst = ", ".join(f"{r['name']} ({r['score']})" for r in card["restaurants"][:3]) or "none"
    notify_users(
        db, [u.id for u in operators],
        f"Company scorecard: {s['red']} red / {s['amber']} amber / {s['green']} green",
        f"Weakest: {worst}. " + ("Human call needed." if s["needs_human_call"] else "No call needed."),
        "company_scorecard", url="/dashboard/continuity",
    )
    return {"notified": len(operators), "summary": s}


@kernel.register("client_checkin", kernel.EXTERNAL,
                 "In-app check-in message to a restaurant's owner/managers.")
def client_checkin(db, payload):
    restaurant = db.get(models.Restaurant, payload["restaurant_id"])
    if restaurant is None:
        raise LookupError("restaurant not found")
    message = str(payload["message"]).strip()
    if not message:
        raise ValueError("empty message")
    users = get_staff_users_for_restaurant(
        db, restaurant, [models.StaffRole.OWNER, models.StaffRole.MANAGER])
    notify_users(db, [u.id for u in users], "A note from your Leviii AI team", message,
                 "company_checkin")
    return {"recipients": len(users)}


def operators(db):
    return db.query(models.User).filter(
        models.User.role == models.Role.SUPERADMIN, models.User.is_active == True).all()  # noqa: E712


@kernel.register("operator_alert", kernel.INTERNAL,
                 "Tell the platform operator something a department noticed (in-app).")
def operator_alert(db, payload):
    ops = operators(db)
    notify_users(db, [u.id for u in ops], str(payload["title"])[:120], str(payload["body"])[:1000],
                 str(payload.get("event_type", "company_alert")), severity=payload.get("severity"))
    return {"notified": len(ops)}


@kernel.register("ticket_reply", kernel.EXTERNAL,
                 "Post a staff reply on a customer's support ticket and notify them.")
def ticket_reply(db, payload):
    ticket = db.get(models.SupportTicket, payload["ticket_id"])
    if ticket is None:
        raise LookupError("ticket not found")
    ops = operators(db)
    if not ops:
        raise RuntimeError("no active operator to post as")
    body = str(payload["message"]).strip()
    if not body:
        raise ValueError("empty message")
    db.add(models.SupportTicketMessage(ticket_id=ticket.id, sender_id=ops[0].id, body=body))
    ticket.updated_at = utcnow()
    notify_users(db, [ticket.created_by_id], f"Update on your ticket: {ticket.subject}"[:120],
                 body, "support_reply")
    return {"ticket_id": ticket.id}


@kernel.register("billing_reminder", kernel.EXTERNAL,
                 "Remind a tenant's owner their subscription is past due or expired.")
def billing_reminder(db, payload):
    users = db.query(models.User).filter(
        models.User.tenant_id == payload["tenant_id"],
        models.User.role == models.Role.ADMIN, models.User.is_active == True).all()  # noqa: E712
    if not users:
        raise LookupError("no owner to remind")
    notify_users(db, [u.id for u in users], "Your Leviii AI subscription needs attention",
                 str(payload["message"]), "billing_reminder", url="/dashboard/billing")
    return {"recipients": len(users)}


@kernel.register("activation_nudge", kernel.EXTERNAL,
                 "Help a new restaurant reach its first 20 orders.")
def activation_nudge(db, payload):
    return client_checkin(db, payload)


@kernel.register("chief_of_staff_brief", kernel.INTERNAL,
                 "Daily brief to the operator: what needs a human, department by department.")
def chief_of_staff_brief(db, payload):
    ops = operators(db)
    notify_users(db, [u.id for u in ops], str(payload["title"])[:120], str(payload["body"])[:1500],
                 "company_brief", url="/dashboard/continuity")
    return {"notified": len(ops)}
