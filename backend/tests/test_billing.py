"""
Subscription/billing (Phase 10): default free plan, plan changes, validation,
tenant scoping, admin-gating.
"""

import auth
import models


def _admin(db, suffix="b"):
    tenant = models.Tenant(name=f"BillCo{suffix}")
    db.add(tenant); db.commit()
    user = models.User(tenant_id=tenant.id, email=f"{suffix}@e.com",
                       hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN)
    db.add(user)
    db.add(models.Restaurant(tenant_id=tenant.id, name="R", address="x"))
    db.commit()
    return user, auth.create_access_token({"sub": user.email, "ver": 0})


def test_defaults_to_free_then_upgrades(client, db_session):
    _, token = _admin(db_session)
    hdr = {"Authorization": f"Bearer {token}"}

    got = client.get("/api/v1/billing/", headers=hdr).json()
    assert got["plan"] == "free" and got["status"] == "active" and got["provider"] == "manual"

    up = client.post("/api/v1/billing/plan", headers=hdr, json={"plan": "pro"})
    assert up.status_code == 200 and up.json()["plan"] == "pro"
    # Persisted.
    assert client.get("/api/v1/billing/", headers=hdr).json()["plan"] == "pro"


def test_rejects_invalid_plan(client, db_session):
    _, token = _admin(db_session)
    r = client.post("/api/v1/billing/plan", headers={"Authorization": f"Bearer {token}"},
                    json={"plan": "unlimited_gold"})
    assert r.status_code == 400


def test_billing_is_admin_only(client, db_session):
    tenant = models.Tenant(name="StaffBill")
    db_session.add(tenant); db_session.commit()
    staff = models.User(tenant_id=tenant.id, email="s@e.com",
                        hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF)
    db_session.add(staff); db_session.commit()
    token = auth.create_access_token({"sub": staff.email, "ver": 0})
    assert client.get("/api/v1/billing/", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_subscription_is_tenant_scoped(client, db_session):
    _, atoken = _admin(db_session, "A")
    _, btoken = _admin(db_session, "B")
    client.post("/api/v1/billing/plan", headers={"Authorization": f"Bearer {atoken}"}, json={"plan": "enterprise"})
    # B is unaffected — still its own default free.
    assert client.get("/api/v1/billing/", headers={"Authorization": f"Bearer {btoken}"}).json()["plan"] == "free"
