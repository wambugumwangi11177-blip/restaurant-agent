"""
Staff account deactivation (tech-debt D18). Previously there was no way to
revoke a departing employee's access short of changing their password — the
User model had no is_active column and no deactivate endpoint at all. These
tests prove: deactivation blocks both new logins and already-issued tokens,
it's tenant-scoped (IDOR), self-deactivation is blocked, non-admins can't do
it, and reactivation reverses it cleanly.
"""

import auth
import models


def _user_with_role(db_session, role, suffix, tenant_id=None):
    if tenant_id is None:
        tenant = models.Tenant(name=f"T{suffix}")
        db_session.add(tenant)
        db_session.commit()
        tenant_id = tenant.id
    user = models.User(
        tenant_id=tenant_id,
        email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("CorrectHorseBattery1!"),
        role=role,
        token_version=0,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return user, token


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_deactivate_blocks_login_and_existing_token(client, db_session):
    admin, admin_token = _user_with_role(db_session, models.Role.ADMIN, "admin1")
    staff, staff_token = _user_with_role(db_session, models.Role.STAFF, "staff1", tenant_id=admin.tenant_id)

    # Token issued BEFORE deactivation still works right now.
    r = client.get("/api/v1/auth/me", headers=_auth_headers(staff_token))
    assert r.status_code == 200

    r = client.post(f"/api/v1/auth/users/{staff.id}/deactivate", headers=_auth_headers(admin_token))
    assert r.status_code == 200
    assert r.json()["status"] == "deactivated"

    # Same pre-existing token is now rejected — not just future logins.
    r = client.get("/api/v1/auth/me", headers=_auth_headers(staff_token))
    assert r.status_code == 401

    # Fresh login attempt is rejected with a clear reason, not a generic 401.
    r = client.post("/api/v1/auth/login", json={
        "email": staff.email, "password": "CorrectHorseBattery1!",
    })
    assert r.status_code == 403
    assert "deactivated" in r.json()["detail"].lower()


def test_cannot_deactivate_across_tenant(client, db_session):
    admin_a, token_a = _user_with_role(db_session, models.Role.ADMIN, "adminA")
    staff_b, _ = _user_with_role(db_session, models.Role.STAFF, "staffB")  # different tenant

    r = client.post(f"/api/v1/auth/users/{staff_b.id}/deactivate", headers=_auth_headers(token_a))
    assert r.status_code == 404

    db_session.refresh(staff_b)
    assert staff_b.is_active is True


def test_cannot_deactivate_self(client, db_session):
    admin, token = _user_with_role(db_session, models.Role.ADMIN, "adminself")

    r = client.post(f"/api/v1/auth/users/{admin.id}/deactivate", headers=_auth_headers(token))
    assert r.status_code == 400


def test_staff_forbidden_from_deactivating(client, db_session):
    staff, staff_token = _user_with_role(db_session, models.Role.STAFF, "staffnoperm")
    other, _ = _user_with_role(db_session, models.Role.STAFF, "othernoperm", tenant_id=staff.tenant_id)

    r = client.post(f"/api/v1/auth/users/{other.id}/deactivate", headers=_auth_headers(staff_token))
    assert r.status_code == 403


def test_activate_reverses_deactivation(client, db_session):
    admin, admin_token = _user_with_role(db_session, models.Role.ADMIN, "adminreact")
    staff, _ = _user_with_role(db_session, models.Role.STAFF, "staffreact", tenant_id=admin.tenant_id)

    client.post(f"/api/v1/auth/users/{staff.id}/deactivate", headers=_auth_headers(admin_token))
    r = client.post("/api/v1/auth/login", json={
        "email": staff.email, "password": "CorrectHorseBattery1!",
    })
    assert r.status_code == 403

    r = client.post(f"/api/v1/auth/users/{staff.id}/activate", headers=_auth_headers(admin_token))
    assert r.status_code == 200
    assert r.json()["status"] == "activated"

    r = client.post("/api/v1/auth/login", json={
        "email": staff.email, "password": "CorrectHorseBattery1!",
    })
    assert r.status_code == 200
