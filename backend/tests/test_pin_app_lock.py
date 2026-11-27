"""App-lock PIN unlock and password re-auth window."""
from datetime import timedelta

import auth
import models
from time_utils import utcnow


def _tenant(db, name="Eleven", owner_email="owner-pin@eleven.leviii"):
    tenant = models.Tenant(name=name)
    db.add(tenant)
    db.flush()
    owner = models.User(
        email=owner_email,
        hashed_password=auth.get_password_hash("OwnerPass1"),
        role=models.Role.ADMIN,
        staff_role=models.StaffRole.OWNER,
        tenant_id=tenant.id,
        token_version=0,
        password_authenticated_at=utcnow(),
    )
    db.add(owner)
    db.flush()
    restaurant = models.Restaurant(name=name, tenant_id=tenant.id)
    db.add(restaurant)
    db.commit()
    return tenant, owner, restaurant


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _token(user: models.User) -> str:
    return auth.create_access_token(data={"sub": user.email, "ver": user.token_version or 0})


def test_pin_unlock_happy_path(client, db_session):
    _, owner, restaurant = _tenant(db_session)
    db_session.add(models.StaffMember(name="Wambugu", user_id=owner.id, restaurant_id=restaurant.id))
    owner.hashed_pin = auth.get_pin_hash("4321")
    db_session.commit()
    token = _token(owner)
    ok = client.post("/api/v1/auth/pin/unlock", headers=_auth(token), json={"pin": "4321"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "unlocked"
    assert ok.json()["display_name"] == "Wambugu"
    me = client.get("/api/v1/auth/me", headers=_auth(token))
    assert me.json()["password_auth_valid"] is True


def test_pin_unlock_lockout_revokes_session(client, db_session):
    _, owner, _ = _tenant(db_session, owner_email="lockout@eleven.leviii")
    owner.hashed_pin = auth.get_pin_hash("9999")
    db_session.commit()
    token = _token(owner)
    headers = _auth(token)
    for _ in range(5):
        bad = client.post("/api/v1/auth/pin/unlock", headers=headers, json={"pin": "0000"})
        assert bad.status_code == 401
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 401
    audit = (
        db_session.query(models.StaffEntryAudit)
        .filter_by(user_id=owner.id, action="pin_lockout")
        .one()
    )
    assert "4321" not in (audit.summary or "")


def test_password_auth_expires_after_30_days(client, db_session):
    _, owner, _ = _tenant(db_session, owner_email="stale@eleven.leviii")
    owner.hashed_pin = auth.get_pin_hash("1234")
    owner.password_authenticated_at = utcnow() - timedelta(days=31)
    db_session.commit()
    token = _token(owner)
    blocked = client.post("/api/v1/auth/pin/unlock", headers=_auth(token), json={"pin": "1234"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "PASSWORD_REQUIRED"