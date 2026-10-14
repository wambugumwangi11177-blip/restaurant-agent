"""Governed tools. Each is deterministic; no tool calls an LLM or moves money."""
import models
from ai.notify import notify_users
from routers.deps import get_staff_users_for_restaurant
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
