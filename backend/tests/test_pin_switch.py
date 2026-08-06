"""
Shared-device PIN quick-switch (tech-debt D16). POS tablets stay logged in
under one device-level JWT for a shift; PIN verify lets staff stamp "who rang
this up" without a full re-login. These tests prove the round-trip works,
lockout kicks in on repeated wrong PINs, the roster/verify are tenant-scoped,
a cross-tenant attribution silently falls back to none rather than leaking,
and — the core design claim — verifying an ADMIN's PIN never changes what the
device's own (possibly STAFF) JWT is actually authorized to do.
"""

from datetime import timedelta

import auth
import models
from time_utils import utcnow


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


def test_lockout_expiry_restores_a_full_set_of_attempts(client, db_session):
    """
    After the lockout window passes, the failed-attempt counter must reset. If
    it stays at MAX, one wrong digit re-trips the lockout instantly and the
    staff member is locked out for the rest of the shift — the counter has to
    go back to zero, not stay primed.
    """
    admin, admin_token = _user_with_role(db_session, models.Role.ADMIN, "lockexp")
    client.post("/api/v1/auth/pin/set", json={"pin": "1111"}, headers=_auth_headers(admin_token))

    for _ in range(5):
        client.post("/api/v1/auth/pin/verify", json={"user_id": admin.id, "pin": "0000"},
                    headers=_auth_headers(admin_token))

    locked = client.post("/api/v1/auth/pin/verify", json={"user_id": admin.id, "pin": "1111"},
                         headers=_auth_headers(admin_token))
    assert locked.status_code == 429

    # Fast-forward past the window.
    db_session.query(models.User).filter(models.User.id == admin.id).update(
        {"pin_locked_until": utcnow() - timedelta(minutes=1)}
    )
    db_session.commit()

    # One wrong attempt must NOT immediately re-lock — the counter is fresh.
    wrong = client.post("/api/v1/auth/pin/verify", json={"user_id": admin.id, "pin": "0000"},
                        headers=_auth_headers(admin_token))
    assert wrong.status_code == 401, "a single wrong PIN after expiry should not re-lock"

    # And the correct PIN still works right after it.
    ok = client.post("/api/v1/auth/pin/verify", json={"user_id": admin.id, "pin": "1111"},
                     headers=_auth_headers(admin_token))
    assert ok.status_code == 200


def test_deactivated_user_cannot_verify_a_pin_or_be_attributed(client, db_session):
    """
    Deactivation must revoke every credential, not just login. A departed
    employee whose PIN still verifies — or who can still be stamped as the
    operator on new orders — leaves a false accountability trail.
    """
    admin, admin_token = _user_with_role(db_session, models.Role.ADMIN, "deacadmin")
    staff, staff_token = _user_with_role(db_session, models.Role.STAFF, "deacstaff", tenant_id=admin.tenant_id)
    client.post("/api/v1/auth/pin/set", json={"pin": "3131"}, headers=_auth_headers(staff_token))

    # Sanity: works while active.
    assert client.post("/api/v1/auth/pin/verify", json={"user_id": staff.id, "pin": "3131"},
                       headers=_auth_headers(admin_token)).status_code == 200

    assert client.post(f"/api/v1/auth/users/{staff.id}/deactivate",
                       headers=_auth_headers(admin_token)).status_code == 200

    # PIN no longer verifies, even posted directly (the roster already hides them).
    after = client.post("/api/v1/auth/pin/verify", json={"user_id": staff.id, "pin": "3131"},
                        headers=_auth_headers(admin_token))
    assert after.status_code == 404

    # And the PIN hash itself is gone, so re-activation is a deliberate opt-in.
    db_session.expire_all()
    refreshed = db_session.query(models.User).filter(models.User.id == staff.id).first()
    assert refreshed.pin_hash is None

    # Attribution to a deactivated user falls back to none.
    restaurant = models.Restaurant(tenant_id=admin.tenant_id, name="RD", address="x")
    db_session.add(restaurant)
    db_session.commit()
    item = models.MenuItem(restaurant_id=restaurant.id, name="x", price=100, is_available=True)
    db_session.add(item)
    db_session.commit()

    resp = client.post("/orders/", json={
        "items": [{"menu_item_id": item.id, "quantity": 1}],
        "payment_method": "cash",
        "attributed_user_id": staff.id,
    }, headers=_auth_headers(admin_token))
    assert resp.status_code == 200
    assert resp.json()["attributed_user_id"] is None


def test_pin_set_does_not_overwrite_an_existing_display_name(client, db_session):
    """Re-setting a PIN shouldn't silently rename someone who already has a
    display name — the docstring promises 'if not already set'."""
    _, token = _user_with_role(db_session, models.Role.ADMIN, "dispname")

    client.post("/api/v1/auth/pin/set", json={"pin": "1212", "display_name": "Amina"},
                headers=_auth_headers(token))
    client.post("/api/v1/auth/pin/set", json={"pin": "3434", "display_name": "Bob"},
                headers=_auth_headers(token))

    r = client.get("/api/v1/auth/pin/roster", headers=_auth_headers(token))
    names = [s["display_name"] for s in r.json()["staff"]]
    assert "Amina" in names
    assert "Bob" not in names


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
