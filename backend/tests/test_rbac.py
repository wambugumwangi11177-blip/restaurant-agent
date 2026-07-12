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


# ── RBAC enforcement (admin-only route: data export) ──────────────────────────

def test_staff_forbidden_on_admin_route(client, db_session):
    token = _user_with_role(db_session, models.Role.STAFF, "staff")
    r = client.get("/data/export/orders.csv", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_allowed_on_admin_route(client, db_session):
    token = _user_with_role(db_session, models.Role.ADMIN, "admin")
    r = client.get("/data/export/orders.csv", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_superadmin_allowed_on_admin_route(client, db_session):
    token = _user_with_role(db_session, models.Role.SUPERADMIN, "super")
    r = client.get("/data/export/orders.csv", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


# ── RBAC coverage on the AI / management routes (P2, 2026-07-11) ──────────────
# Before this pass, every /ai/* route and menu/inventory writes used only
# get_current_user, so any authenticated STAFF token could approve price changes
# (mutates menu prices) and trigger real customer marketing sends. These prove
# the money-moving and management routes are now ADMIN-gated, while owners
# (who register as ADMIN) are not locked out.

def test_staff_forbidden_approving_pricing(client, db_session):
    """The most severe pre-fix gap: STAFF could approve a price change."""
    token = _user_with_role(db_session, models.Role.STAFF, "staffprice")
    r = client.post("/ai/pricing/1/approve", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_not_forbidden_approving_pricing(client, db_session):
    """Owners (ADMIN) still reach the route — a missing rec is a 4xx that is NOT 403."""
    token = _user_with_role(db_session, models.Role.ADMIN, "adminprice")
    r = client.post("/ai/pricing/999999/approve", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code != 403


def test_staff_forbidden_sending_promo(client, db_session):
    """STAFF could previously trigger a real customer marketing broadcast."""
    token = _user_with_role(db_session, models.Role.STAFF, "staffpromo")
    r = client.post(
        "/ai/marketing/promo",
        json={"offer_text": "15% off"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_staff_forbidden_creating_menu_item(client, db_session):
    """Menu definition (price-bearing) is management, not a POS action."""
    token = _user_with_role(db_session, models.Role.STAFF, "staffmenu")
    r = client.post(
        "/menu/",
        json={"name": "Ugali", "price": 200, "category": "mains"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_staff_forbidden_on_ai_usage(client, db_session):
    """AIOps cost data is ADMIN-only (corrects a stale 'owners are STAFF' comment)."""
    token = _user_with_role(db_session, models.Role.STAFF, "staffusage")
    r = client.get("/ai/usage", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# ── Password policy at registration ───────────────────────────────────────────

def test_register_rejects_weak_passwords(client, db_session):
    # too short, no digit, no letter — each must be rejected with 400.
    for pw in ["short1", "alllettershere", "12345678"]:
        r = client.post(
            "/api/v1/auth/register",
            json={"email": f"{pw}@e.com", "password": pw, "tenant_name": "X"},
        )
        assert r.status_code == 400, (pw, r.status_code, r.text)


def test_register_accepts_strong_password(client, db_session):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "strong@e.com", "password": "GoodPass1", "tenant_name": "X"},
    )
    assert r.status_code == 200
    assert "access_token" in r.json()
