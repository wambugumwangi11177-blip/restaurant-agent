"""
Role-based access control + registration password policy.

Security pass (2026-07-11): the Role enum (SUPERADMIN/ADMIN/STAFF) existed but
nothing enforced it, and registration accepted any non-empty password. These
tests prove the new `require_role` dependency actually gates admin-only routes
(403 for STAFF, allowed for ADMIN/SUPERADMIN) and that weak passwords are
rejected at registration.
"""

import auth
import models


def _user_with_role(db_session, role, suffix):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=role,
        token_version=0,
    )
    db_session.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token


# ── RBAC enforcement (platform admin list Eleven logins) ─────────────────────

def test_staff_forbidden_on_admin_route(client, db_session):
    token = _user_with_role(db_session, models.Role.STAFF, "staff")
    r = client.get("/api/v1/eleven/logins/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_forbidden_on_superadmin_route(client, db_session):
    token = _user_with_role(db_session, models.Role.ADMIN, "admin")
    r = client.get("/api/v1/eleven/logins/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_superadmin_allowed_on_admin_route(client, db_session):
    token = _user_with_role(db_session, models.Role.SUPERADMIN, "super")
    r = client.get("/api/v1/eleven/logins/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_legacy_chakula_routes_not_mounted(client):
    for path in ("/menu/", "/orders/", "/api/v1/menu/", "/api/v1/demo/home"):
        assert client.get(path).status_code == 404


def test_public_register_endpoint_removed(client):
    assert client.post(
        "/api/v1/auth/register",
        json={"email": "strong@e.com", "password": "GoodPass1", "tenant_name": "X"},
    ).status_code == 404


def test_weak_password_rejected_on_set_initial_password(client, db_session):
    from tests.factories import seed_owner
    user, _, _ = seed_owner(
        db_session,
        email="jack@weak.example",
        password=None,
        tenant_name="Eleven",
    )
    user.must_change_password = True
    user.role = models.Role.STAFF
    user.staff_role = models.StaffRole.STOCKKEEPER
    db_session.commit()
    r = client.post("/api/v1/auth/set-initial-password", json={"email": user.email, "new_password": "weak"})
    assert r.status_code == 400
