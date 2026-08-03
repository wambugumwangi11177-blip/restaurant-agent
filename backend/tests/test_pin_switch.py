"""
Shared-device PIN quick-switch (tech-debt D16). POS tablets stay logged in
under one device-level JWT for a shift; PIN verify lets staff stamp "who rang
this up" without a full re-login. These tests prove the round-trip works,
lockout kicks in on repeated wrong PINs, the roster/verify are tenant-scoped,
a cross-tenant attribution silently falls back to none rather than leaking,
and — the core design claim — verifying an ADMIN's PIN never changes what the
device's own (possibly STAFF) JWT is actually authorized to do.
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


def test_set_and_verify_round_trip(client, db_session):
    admin, admin_token = _user_with_role(db_session, models.Role.ADMIN, "admin1")
    staff, staff_token = _user_with_role(db_session, models.Role.STAFF, "staff1", tenant_id=admin.tenant_id)

    r = client.post("/api/v1/auth/pin/set", json={"pin": "4242", "display_name": "Amina"},
                     headers=_auth_headers(staff_token))
    assert r.status_code == 200

    # A different authenticated device session (the admin's, standing in for
    # the shared POS tablet's own login) verifies staff's PIN.
    r = client.post("/api/v1/auth/pin/verify", json={"user_id": staff.id, "pin": "4242"},
                     headers=_auth_headers(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == staff.id
    assert body["display_name"] == "Amina"
    assert body["role"] == "staff"


def test_wrong_pin_locks_out_after_max_attempts(client, db_session):
    admin, admin_token = _user_with_role(db_session, models.Role.ADMIN, "admin2")
    staff, _ = _user_with_role(db_session, models.Role.STAFF, "staff2", tenant_id=admin.tenant_id)
    client.post("/api/v1/auth/pin/set", json={"pin": "1111"}, headers=_auth_headers(admin_token))

    for _ in range(5):
        r = client.post("/api/v1/auth/pin/verify", json={"user_id": admin.id, "pin": "0000"},
                         headers=_auth_headers(admin_token))
        assert r.status_code == 401

    r = client.post("/api/v1/auth/pin/verify", json={"user_id": admin.id, "pin": "1111"},
                     headers=_auth_headers(admin_token))
    assert r.status_code == 429
    assert "locked" in r.json()["detail"].lower()


def test_roster_is_tenant_scoped_and_excludes_users_without_a_pin(client, db_session):
    admin_a, token_a = _user_with_role(db_session, models.Role.ADMIN, "adminA")
    staff_a, _ = _user_with_role(db_session, models.Role.STAFF, "staffA", tenant_id=admin_a.tenant_id)
    admin_b, token_b = _user_with_role(db_session, models.Role.ADMIN, "adminB")  # different tenant

    client.post("/api/v1/auth/pin/set", json={"pin": "5555"}, headers=_auth_headers(token_a))
    # staff_a never sets a PIN; admin_b (other tenant) does.
    client.post("/api/v1/auth/pin/set", json={"pin": "6666"}, headers=_auth_headers(token_b))

    r = client.get("/api/v1/auth/pin/roster", headers=_auth_headers(token_a))
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()["staff"]]
    assert admin_a.id in ids
    assert staff_a.id not in ids   # no PIN set
    assert admin_b.id not in ids   # different tenant


def test_cross_tenant_attribution_falls_back_to_none(client, db_session):
    admin_a, token_a = _user_with_role(db_session, models.Role.ADMIN, "attrA")
    restaurant_a = models.Restaurant(tenant_id=admin_a.tenant_id, name="RA", address="x")
    db_session.add(restaurant_a)
    db_session.commit()
    item = models.MenuItem(restaurant_id=restaurant_a.id, name="x", price=100, is_available=True)
    db_session.add(item)
    db_session.commit()

    admin_b, _ = _user_with_role(db_session, models.Role.ADMIN, "attrB")  # different tenant

    resp = client.post("/orders/", json={
        "items": [{"menu_item_id": item.id, "quantity": 1}],
        "payment_method": "cash",
        "attributed_user_id": admin_b.id,   # belongs to a DIFFERENT tenant
    }, headers=_auth_headers(token_a))
    assert resp.status_code == 200
    assert resp.json()["attributed_user_id"] is None

    order = db_session.query(models.Order).filter(models.Order.id == resp.json()["id"]).first()
    assert order.attributed_user_id is None


def test_pin_switch_does_not_elevate_the_devices_own_authorization(client, db_session):
    """
    The core design claim: PIN-verifying as an ADMIN must NOT change what a
    STAFF-role device session's own JWT can actually do. The verify response
    is display-only attribution data, never a new grant of privilege.
    """
    admin, _ = _user_with_role(db_session, models.Role.ADMIN, "elevadmin")
    staff, staff_token = _user_with_role(db_session, models.Role.STAFF, "elevstaff", tenant_id=admin.tenant_id)
    client.post("/api/v1/auth/pin/set", json={"pin": "9999"}, headers=_auth_headers(staff_token))
    # Re-set as admin's own PIN too (staff device verifies the admin's PIN below).
    admin_token = auth.create_access_token({"sub": admin.email, "ver": 0})
    client.post("/api/v1/auth/pin/set", json={"pin": "7777"}, headers=_auth_headers(admin_token))

    # The STAFF-tier device session verifies the ADMIN's PIN.
    r = client.post("/api/v1/auth/pin/verify", json={"user_id": admin.id, "pin": "7777"},
                     headers=_auth_headers(staff_token))
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

    # But the device's own JWT is still STAFF — an admin-only route must
    # still 403, exactly as before the PIN switch.
    r = client.get("/data/export/orders.csv", headers=_auth_headers(staff_token))
    assert r.status_code == 403
