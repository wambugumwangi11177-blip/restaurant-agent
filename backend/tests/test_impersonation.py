"""
Owner "view as" — real impersonation (directive 015 follow-up).

Covers the pieces that are easy to get subtly wrong: the impersonation token
resolving to the TARGET (not the Owner) everywhere, the live-session table
being the actual source of truth for "is this still valid" (not just JWT
exp), the Owner/Admin-can-never-be-a-target boundary, cross-tenant isolation,
and that ending a session invalidates the very next request with that token.
"""

from datetime import timedelta

import auth
import models
from time_utils import utcnow


def _user_with_staff_role(db_session, suffix, role=models.Role.STAFF, staff_role=None, is_active=True, tenant=None):
    if tenant is None:
        tenant = models.Tenant(name=f"T{suffix}")
        db_session.add(tenant)
        db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=role,
        staff_role=staff_role,
        is_active=is_active,
        token_version=0,
    )
    db_session.add(user)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token, user, tenant


def _owner_with_staff(db_session, staff_suffix, staff_role, staff_user_kwargs=None):
    """An Owner (Role.ADMIN) plus one StaffMember+User of the given tier, both
    in the same tenant/restaurant, plus the Owner's bearer token."""
    tenant = models.Tenant(name=f"T{staff_suffix}")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{staff_suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()

    owner = models.User(
        tenant_id=tenant.id, email=f"owner{staff_suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER, token_version=0,
    )
    db_session.add(owner)
    db_session.commit()
    owner_token = auth.create_access_token({"sub": owner.email, "ver": 0})

    staff_token, staff_user, _ = _user_with_staff_role(
        db_session, staff_suffix, staff_role=staff_role, tenant=tenant, **(staff_user_kwargs or {})
    )
    member = models.StaffMember(restaurant_id=restaurant.id, user_id=staff_user.id, name=f"Staff {staff_suffix}")
    db_session.add(member)
    db_session.commit()

    return owner_token, owner, staff_user, member, restaurant, tenant


# ── Impersonation grants exactly the target's own access, correctly attributed ──

def test_impersonated_token_behaves_as_the_target_tier(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "waiter1", models.StaffRole.WAITER
    )
    r = client.post(f"/staff/{member.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    assert r.status_code == 200, r.text
    imp_token = r.json()["access_token"]

    # Waiter is in orders._CAN_READ (directive 015) — should succeed.
    r2 = client.get("/orders/", headers={"Authorization": f"Bearer {imp_token}"})
    assert r2.status_code == 200, r2.text


def test_me_under_impersonation_shows_target_identity_and_impersonator(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "waiter2", models.StaffRole.WAITER
    )
    r = client.post(f"/staff/{member.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    imp_token = r.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {imp_token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == staff_user.email
    assert body["staff_role"] == "waiter"
    assert body["impersonation"] is not None
    assert body["impersonation"]["impersonator_email"] == owner.email


# ── Boundaries: no login, no Owner/Admin target, cross-tenant ──────────────────

def test_cannot_impersonate_staff_member_with_no_login(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "nologin", models.StaffRole.WAITER
    )
    orphan = models.StaffMember(restaurant_id=restaurant.id, user_id=None, name="No Login")
    db_session.add(orphan)
    db_session.commit()

    r = client.post(f"/staff/{orphan.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    assert r.status_code == 400


def test_cannot_impersonate_an_owner_or_admin(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "peer", models.StaffRole.WAITER
    )
    other_owner = models.User(
        tenant_id=tenant.id, email="otherowner@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER, token_version=0,
    )
    db_session.add(other_owner)
    db_session.commit()
    other_member = models.StaffMember(restaurant_id=restaurant.id, user_id=other_owner.id, name="Other Owner")
    db_session.add(other_member)
    db_session.commit()

    r = client.post(f"/staff/{other_member.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    assert r.status_code == 403


def test_cannot_impersonate_staff_member_in_another_tenant(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "tenantA", models.StaffRole.WAITER
    )
    _, _, other_staff_user, other_member, _, _ = _owner_with_staff(
        db_session, "tenantB", models.StaffRole.WAITER
    )

    r = client.post(f"/staff/{other_member.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    assert r.status_code == 404


# ── Ending a session, and non-owner/non-impersonation edge cases ───────────────

def test_end_impersonation_invalidates_the_token(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "waiter3", models.StaffRole.WAITER
    )
    r = client.post(f"/staff/{member.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    imp_token = r.json()["access_token"]

    end = client.post("/staff/end-impersonation", headers={"Authorization": f"Bearer {imp_token}"})
    assert end.status_code == 200

    after = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {imp_token}"})
    assert after.status_code == 401


def test_end_impersonation_with_normal_token_is_400(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "waiter4", models.StaffRole.WAITER
    )
    r = client.post("/staff/end-impersonation", headers={"Authorization": f"Bearer {owner_token}"})
    assert r.status_code == 400


def test_expired_impersonation_session_is_401(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "waiter5", models.StaffRole.WAITER
    )
    session = models.ImpersonationSession(
        tenant_id=tenant.id, restaurant_id=restaurant.id,
        impersonator_user_id=owner.id, target_user_id=staff_user.id,
        expires_at=utcnow() - timedelta(minutes=1),
    )
    db_session.add(session)
    db_session.commit()

    token = auth.create_access_token(
        data={"sub": staff_user.email, "ver": 0, "imp_session_id": session.id, "imp_by": owner.id}
    )
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_target_deactivated_mid_session_is_401(client, db_session):
    """Falls through the pre-existing `ver` check in get_current_user — proves
    impersonation doesn't accidentally bypass an existing revocation path."""
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "waiter6", models.StaffRole.WAITER
    )
    r = client.post(f"/staff/{member.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    imp_token = r.json()["access_token"]

    deact = client.put(
        f"/staff/{member.id}", json={"is_active": False},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert deact.status_code == 200

    after = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {imp_token}"})
    assert after.status_code == 401


def test_impersonator_deactivated_mid_session_is_401(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "waiter7", models.StaffRole.WAITER
    )
    r = client.post(f"/staff/{member.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    imp_token = r.json()["access_token"]

    owner.is_active = False
    db_session.commit()

    after = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {imp_token}"})
    assert after.status_code == 401


def test_impersonation_token_cannot_itself_impersonate(client, db_session):
    """Nested impersonation is blocked as a side effect of /impersonate
    requiring Role.ADMIN — an impersonated session's role is always STAFF."""
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "waiter8", models.StaffRole.WAITER
    )
    other_staff_token, other_staff_user, _ = _user_with_staff_role(
        db_session, "waiter8b", staff_role=models.StaffRole.WAITER, tenant=tenant
    )
    other_member = models.StaffMember(restaurant_id=restaurant.id, user_id=other_staff_user.id, name="Other Waiter")
    db_session.add(other_member)
    db_session.commit()

    r = client.post(f"/staff/{member.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    imp_token = r.json()["access_token"]

    r2 = client.post(f"/staff/{other_member.id}/impersonate", headers={"Authorization": f"Bearer {imp_token}"})
    assert r2.status_code == 403


# ── Audit trail read surface ────────────────────────────────────────────────────

def test_impersonation_log_shows_status_transitions(client, db_session):
    owner_token, owner, staff_user, member, restaurant, tenant = _owner_with_staff(
        db_session, "waiter9", models.StaffRole.WAITER
    )
    r = client.post(f"/staff/{member.id}/impersonate", headers={"Authorization": f"Bearer {owner_token}"})
    imp_token = r.json()["access_token"]

    log_active = client.get("/staff/impersonation-log", headers={"Authorization": f"Bearer {owner_token}"})
    assert log_active.status_code == 200
    entry = log_active.json()[0]
    assert entry["status"] == "active"
    assert entry["target_email"] == staff_user.email
    assert entry["impersonator_email"] == owner.email

    client.post("/staff/end-impersonation", headers={"Authorization": f"Bearer {imp_token}"})

    log_ended = client.get("/staff/impersonation-log", headers={"Authorization": f"Bearer {owner_token}"})
    assert log_ended.json()[0]["status"] == "ended"


# ── orders.py / reservations.py newly-gated RBAC (directive 015 gap closure) ───

def test_controller_can_read_but_not_write_orders(client, db_session):
    token, _, _ = _user_with_staff_role(db_session, "ctrl_orders", staff_role=models.StaffRole.CONTROLLER)
    r_read = client.get("/orders/", headers={"Authorization": f"Bearer {token}"})
    assert r_read.status_code == 200
    r_write = client.post(
        "/orders/", json={"items": [], "order_type": "dine_in", "delivery_channel": "walk_in", "payment_method": "cash"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_write.status_code == 403


def test_stockkeeper_forbidden_on_orders_read_and_write(client, db_session):
    """Matrix says '-' for Stockkeeper on `orders` — no read, no write."""
    token, _, _ = _user_with_staff_role(db_session, "sk_orders", staff_role=models.StaffRole.STOCKKEEPER)
    r_read = client.get("/orders/", headers={"Authorization": f"Bearer {token}"})
    assert r_read.status_code == 403
    r_write = client.post(
        "/orders/", json={"items": [], "order_type": "dine_in", "delivery_channel": "walk_in", "payment_method": "cash"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_write.status_code == 403


def test_kitchen_can_advance_order_status(client, db_session):
    """Kitchen is R-only on the `orders` route per the matrix, but must still
    be able to write PATCH /orders/{id}/status — that's the KDS action, which
    the `kitchen` page/route grants Kitchen RW on (see orders.py's
    _CAN_UPDATE_STATUS comment)."""
    token, user, tenant = _user_with_staff_role(db_session, "kitchen_status", staff_role=models.StaffRole.KITCHEN)
    restaurant = models.Restaurant(tenant_id=tenant.id, name="RK", address="x")
    db_session.add(restaurant)
    db_session.commit()
    order = models.Order(restaurant_id=restaurant.id, status=models.OrderStatus.PENDING, total=0)
    db_session.add(order)
    db_session.commit()

    r = client.post(
        f"/orders/{order.id}/status", json={"status": "prep"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text


def test_owner_bypass_still_works_on_orders_and_reservations(client, db_session):
    token, _, _ = _user_with_staff_role(db_session, "owner_bypass", role=models.Role.ADMIN, staff_role=None)
    assert client.get("/orders/", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/reservations/", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_kitchen_forbidden_on_reservations(client, db_session):
    """Matrix has no read-only tier for `reservations` — Kitchen gets nothing."""
    token, _, _ = _user_with_staff_role(db_session, "kitchen_res", staff_role=models.StaffRole.KITCHEN)
    r = client.get("/reservations/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
