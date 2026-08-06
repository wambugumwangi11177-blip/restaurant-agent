"""
Subscription/billing: plan changes, validation, tenant scoping, admin-gating —
plus, from 2026-08-06, the enforcement that makes any of it mean something.

Before that date a subscription was a string an admin set on themselves: every
tenant was created active-forever, `/billing/plan` wrote the field with no
payment gate, and no code anywhere read the result. The product could collect
M-Pesa payments *for* restaurants and had no way to collect payment *from* them.

Two deliberate behaviour changes are pinned below:

  • New tenants start `trialing` with a 14-day period, not `active` forever, so
    the paid state is the default destination and enforcement is exercised from
    day one rather than switched on later against live restaurants.

  • `/billing/plan` no longer grants access time. Only `/billing/record-payment`
    does. Previously an admin could hand themselves `plan="enterprise"` and an
    active status in a single call, which is exactly why billing meant nothing.
"""

from datetime import timedelta

import auth
import models
from routers import billing
from time_utils import utcnow


def _admin(db, suffix="b"):
    tenant = models.Tenant(name=f"BillCo{suffix}")
    db.add(tenant); db.commit()
    user = models.User(tenant_id=tenant.id, email=f"{suffix}@e.com",
                       hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN)
    db.add(user)
    db.add(models.Restaurant(tenant_id=tenant.id, name="R", address="x"))
    db.commit()
    return user, auth.create_access_token({"sub": user.email, "ver": 0})


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _set_period_end(db, tenant_id, when):
    """
    Force a tenant's period end. Creates the row if absent, since subscriptions
    are provisioned lazily on first billing access — a tenant that has never
    hit a gated route has no row yet.
    """
    sub = db.query(models.Subscription).filter(
        models.Subscription.tenant_id == tenant_id
    ).first()
    if sub is None:
        sub = models.Subscription(
            tenant_id=tenant_id, plan="free",
            status=billing.STATUS_TRIALING, provider="manual",
        )
        db.add(sub)
    sub.current_period_end = when
    db.commit()
    return sub


# ── Plan tier ────────────────────────────────────────────────────────────────

def test_new_tenant_starts_on_a_trial(client, db_session):
    _, token = _admin(db_session)
    got = client.get("/api/v1/billing/", headers=_hdr(token)).json()

    assert got["plan"] == "free"
    assert got["status"] == billing.STATUS_TRIALING
    assert got["provider"] == "manual"
    assert got["is_active"] is True
    assert got["days_remaining"] is not None


def test_plan_change_persists(client, db_session):
    _, token = _admin(db_session)
    up = client.post("/api/v1/billing/plan", headers=_hdr(token), json={"plan": "pro"})
    assert up.status_code == 200 and up.json()["plan"] == "pro"
    assert client.get("/api/v1/billing/", headers=_hdr(token)).json()["plan"] == "pro"


def test_plan_change_does_not_grant_access_time(client, db_session):
    """The self-service loophole: upgrading your tier must not pay your bill."""
    user, token = _admin(db_session, "loop")
    _set_period_end(db_session, user.tenant_id, utcnow() - timedelta(days=99))

    client.post("/api/v1/billing/plan", headers=_hdr(token), json={"plan": "enterprise"})
    got = client.get("/api/v1/billing/", headers=_hdr(token)).json()

    assert got["plan"] == "enterprise"
    assert got["status"] == billing.STATUS_PAST_DUE
    assert got["is_active"] is False


def test_rejects_invalid_plan(client, db_session):
    _, token = _admin(db_session)
    r = client.post("/api/v1/billing/plan", headers=_hdr(token), json={"plan": "unlimited_gold"})
    assert r.status_code == 400


def test_billing_is_admin_only(client, db_session):
    tenant = models.Tenant(name="StaffBill")
    db_session.add(tenant); db_session.commit()
    staff = models.User(tenant_id=tenant.id, email="s@e.com",
                        hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF)
    db_session.add(staff); db_session.commit()
    token = auth.create_access_token({"sub": staff.email, "ver": 0})
    assert client.get("/api/v1/billing/", headers=_hdr(token)).status_code == 403


def test_subscription_is_tenant_scoped(client, db_session):
    _, atoken = _admin(db_session, "A")
    _, btoken = _admin(db_session, "B")
    client.post("/api/v1/billing/plan", headers=_hdr(atoken), json={"plan": "enterprise"})
    assert client.get("/api/v1/billing/", headers=_hdr(btoken)).json()["plan"] == "free"


# ── Period state machine ─────────────────────────────────────────────────────

def test_recording_a_payment_extends_the_period(client, db_session):
    user, token = _admin(db_session, "pay")
    _set_period_end(db_session, user.tenant_id, utcnow() - timedelta(days=10))

    got = client.post("/api/v1/billing/record-payment", headers=_hdr(token),
                      json={"days": 30}).json()
    assert got["status"] == billing.STATUS_ACTIVE
    assert got["is_active"] is True
    assert got["days_remaining"] >= 29


def test_paying_early_adds_time_rather_than_discarding_it(client, db_session):
    user, token = _admin(db_session, "early")
    _set_period_end(db_session, user.tenant_id, utcnow() + timedelta(days=20))

    got = client.post("/api/v1/billing/record-payment", headers=_hdr(token),
                      json={"days": 30}).json()
    assert got["days_remaining"] >= 49


def test_payment_after_a_lapse_is_not_backdated(client, db_session):
    user, token = _admin(db_session, "lapsed")
    _set_period_end(db_session, user.tenant_id, utcnow() - timedelta(days=200))

    got = client.post("/api/v1/billing/record-payment", headers=_hdr(token),
                      json={"days": 30}).json()
    assert got["days_remaining"] >= 29


def test_rejects_absurd_period_lengths(client, db_session):
    _, token = _admin(db_session, "absurd")
    for days in (0, -5, 5000):
        r = client.post("/api/v1/billing/record-payment", headers=_hdr(token),
                        json={"days": days})
        assert r.status_code == 400


def test_grace_period_covers_a_late_payment(client, db_session):
    """
    M-Pesa payments from an owner arrive when the owner remembers, not on a
    schedule. Cutting off at midnight on day 30 over money that lands on day 31
    buys nothing.
    """
    user, token = _admin(db_session, "grace")
    _set_period_end(db_session, user.tenant_id, utcnow() - timedelta(days=1))

    got = client.get("/api/v1/billing/", headers=_hdr(token)).json()
    assert got["is_active"] is True
    assert got["in_grace_period"] is True


def test_lapse_past_grace_is_past_due(client, db_session):
    user, token = _admin(db_session, "expired")
    _set_period_end(db_session, user.tenant_id,
                    utcnow() - timedelta(days=billing.GRACE_DAYS + 2))

    got = client.get("/api/v1/billing/", headers=_hdr(token)).json()
    assert got["status"] == billing.STATUS_PAST_DUE
    assert got["is_active"] is False


def test_lapse_is_computed_on_read_not_by_a_job(client, db_session):
    """
    The stored column still says `active`; only the clock has moved. Computing
    the effective state on read means enforcement can't silently fail because a
    scheduler didn't run — and main.py's APScheduler is single-worker and exactly
    the kind of thing that stops quietly.
    """
    user, token = _admin(db_session, "noJob")
    sub = _set_period_end(db_session, user.tenant_id,
                          utcnow() - timedelta(days=billing.GRACE_DAYS + 2))
    sub.status = billing.STATUS_ACTIVE
    db_session.commit()

    got = client.get("/api/v1/billing/", headers=_hdr(token)).json()
    assert got["stored_status"] == billing.STATUS_ACTIVE
    assert got["status"] == billing.STATUS_PAST_DUE


def test_cancel_revokes_access_but_keeps_the_period_on_record(client, db_session):
    user, token = _admin(db_session, "cancel")
    client.post("/api/v1/billing/record-payment", headers=_hdr(token), json={"days": 30})

    got = client.post("/api/v1/billing/cancel", headers=_hdr(token)).json()
    assert got["status"] == billing.STATUS_CANCELED
    assert got["is_active"] is False
    assert got["current_period_end"] is not None


def test_null_period_end_is_open_ended(client, db_session):
    """What an enterprise tenant on an offline contract looks like."""
    user, token = _admin(db_session, "openEnded")
    _set_period_end(db_session, user.tenant_id, None)

    got = client.get("/api/v1/billing/", headers=_hdr(token)).json()
    assert got["is_active"] is True
    assert got["days_remaining"] is None


# ── Enforcement: what is gated, and what must never be ───────────────────────

def _expire(db, tenant_id):
    _set_period_end(db, tenant_id, utcnow() - timedelta(days=billing.GRACE_DAYS + 5))


def test_intelligence_is_gated_when_unpaid(client, db_session):
    user, token = _admin(db_session, "gated")
    assert client.get("/api/v1/ai/profit", headers=_hdr(token)).status_code == 200

    _expire(db_session, user.tenant_id)
    r = client.get("/api/v1/ai/profit", headers=_hdr(token))
    # 402, not 403: correctly authenticated and authorised — the account owes
    # money. A client can show a renewal prompt rather than an access error.
    assert r.status_code == 402


def test_paying_restores_intelligence(client, db_session):
    user, token = _admin(db_session, "restore")
    _expire(db_session, user.tenant_id)
    assert client.get("/api/v1/ai/profit", headers=_hdr(token)).status_code == 402

    client.post("/api/v1/billing/record-payment", headers=_hdr(token), json={"days": 30})
    assert client.get("/api/v1/ai/profit", headers=_hdr(token)).status_code == 200


def test_an_unpaid_restaurant_can_still_trade(client, db_session):
    """
    The line that must not move. Locking the till over a billing state would
    strand a dining room mid-service, and any owner it happened to once would
    tear the system out the next morning — correctly. Non-payment costs you the
    analysis, never the ability to trade or to see your own numbers.
    """
    user, token = _admin(db_session, "trading")
    _expire(db_session, user.tenant_id)
    hdr = _hdr(token)

    item = client.post("/api/v1/menu/", headers=hdr, json={
        "name": "Ugali", "price": 200, "category": "main",
    })
    assert item.status_code == 200

    order = client.post("/api/v1/orders/", headers=hdr, json={
        "items": [{"menu_item_id": item.json()["id"], "quantity": 1}]
    })
    assert order.status_code == 200

    # Kitchen, order history and their own dashboard all keep working.
    assert client.get("/api/v1/orders/active", headers=hdr).status_code == 200
    assert client.patch(f"/api/v1/orders/{order.json()['id']}/status",
                        headers=hdr, json={"status": "prep"}).status_code == 200
    assert client.get("/api/v1/inventory/", headers=hdr).status_code == 200
    assert client.get("/api/v1/ai/dashboard", headers=hdr).status_code == 200
