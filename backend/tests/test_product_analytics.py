"""
Product analytics (Phase 8, 2026-07-12): track events and summarise usage,
tenant-scoped, with the summary admin-gated.
"""

import auth
import models


def _admin(db):
    tenant = models.Tenant(name="AnalyticsCo")
    db.add(tenant); db.commit()
    user = models.User(tenant_id=tenant.id, email="a@e.com",
                       hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN)
    db.add(user)
    db.add(models.Restaurant(tenant_id=tenant.id, name="R", address="x"))
    db.commit()
    return user, auth.create_access_token({"sub": user.email, "ver": 0})


def _staff(db, suffix="s"):
    tenant = models.Tenant(name=f"T{suffix}")
    db.add(tenant); db.commit()
    user = models.User(tenant_id=tenant.id, email=f"{suffix}@e.com",
                       hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF)
    db.add(user); db.commit()
    return user, auth.create_access_token({"sub": user.email, "ver": 0})


def test_track_and_summary(client, db_session):
    _, token = _admin(db_session)
    hdr = {"Authorization": f"Bearer {token}"}

    for name in ["viewed_dashboard", "viewed_dashboard", "approved_pricing"]:
        r = client.post("/api/v1/events/track", headers=hdr,
                        json={"event_name": name, "properties": {"src": "test"}})
        assert r.status_code == 200 and r.json()["tracked"] is True

    s = client.get("/api/v1/events/summary", headers=hdr).json()
    assert s["total_events"] == 3
    assert s["active_users"] == 1
    assert s["events_by_name"]["viewed_dashboard"] == 2
    assert s["events_by_name"]["approved_pricing"] == 1


def test_track_requires_event_name(client, db_session):
    _, token = _admin(db_session)
    r = client.post("/api/v1/events/track", headers={"Authorization": f"Bearer {token}"},
                    json={"properties": {}})
    assert r.status_code == 200 and r.json()["tracked"] is False


def test_summary_is_admin_only(client, db_session):
    _, stoken = _staff(db_session)
    r = client.get("/api/v1/events/summary", headers={"Authorization": f"Bearer {stoken}"})
    assert r.status_code == 403


def test_summary_is_tenant_scoped(client, db_session):
    # Tenant A logs an event; tenant B's summary must not see it.
    _, atoken = _admin(db_session)
    client.post("/api/v1/events/track", headers={"Authorization": f"Bearer {atoken}"},
                json={"event_name": "secret_action"})

    tenant_b = models.Tenant(name="OtherCo")
    db_session.add(tenant_b); db_session.commit()
    userb = models.User(tenant_id=tenant_b.id, email="b@e.com",
                        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN)
    db_session.add(userb); db_session.commit()
    btoken = auth.create_access_token({"sub": userb.email, "ver": 0})
    s = client.get("/api/v1/events/summary", headers={"Authorization": f"Bearer {btoken}"}).json()
    assert s["total_events"] == 0
