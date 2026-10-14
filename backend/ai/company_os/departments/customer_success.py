"""Customer success: onboarding to activation, then keeping health green."""
from datetime import timedelta

import models
from time_utils import utcnow
from ai.continuity.scorecard import platform_scorecard
from .. import kernel, tools  # noqa: F401

NAME = "customer_success"
ACTIVATION_DAYS = 14
ACTIVATION_ORDERS = 20
CHECKIN_COOLDOWN_DAYS = 7


def _recent(db, tool, restaurant_id):
    since = utcnow() - timedelta(days=CHECKIN_COOLDOWN_DAYS)
    return db.query(models.CompanyProposal).filter(
        models.CompanyProposal.tool == tool,
        models.CompanyProposal.restaurant_id == restaurant_id,
        models.CompanyProposal.status.in_(["pending", "executed"]),
        models.CompanyProposal.created_at >= since).first() is not None


def health_agent(db):
    out = []
    for r in platform_scorecard(db)["restaurants"]:
        if r["status"] != "red" or _recent(db, "client_checkin", r["restaurant_id"]):
            continue
        reasons = "; ".join(r["reasons"]) or "activity looks low"
        out.append(kernel.propose(
            db, "customer_success.health_agent", "client_checkin",
            {"restaurant_id": r["restaurant_id"], "message": (
                f"Hi, we noticed {reasons} at {r['name']}. "
                "Is anything blocking you? Reply here and we'll help get you back on track.")},
            f"Check in with {r['name']} (health {r['score']})", restaurant_id=r["restaurant_id"]))
    return out


def onboarding_agent(db):
    """Report's activation metric: first 20 orders within 14 days of signup."""
    out, now = [], utcnow()
    for r in db.query(models.Restaurant).all():
        tenant = db.get(models.Tenant, r.tenant_id)
        if not tenant or not tenant.created_at:
            continue
        age = (now - tenant.created_at).days
        if age < ACTIVATION_DAYS or age > 60:
            continue
        orders = db.query(models.Order).filter(models.Order.restaurant_id == r.id).count()
        if orders >= ACTIVATION_ORDERS or _recent(db, "activation_nudge", r.id):
            continue
        out.append(kernel.propose(
            db, "customer_success.onboarding_agent", "activation_nudge",
            {"restaurant_id": r.id, "message": (
                f"Welcome to Leviii AI! {r.name} has {orders} orders so far. Restaurants that reach "
                f"{ACTIVATION_ORDERS} orders in the first {ACTIVATION_DAYS} days see the most value. "
                "Want a hand with your menu or setup?")},
            f"Activation nudge for {r.name} ({orders}/{ACTIVATION_ORDERS} orders, day {age})",
            restaurant_id=r.id))
    return out


def run(db, today=None):
    return onboarding_agent(db) + health_agent(db)
