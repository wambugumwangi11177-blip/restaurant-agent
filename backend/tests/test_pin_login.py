"""
Shared-device quick-switch PIN — audit remediation, Tier 5 item 12.

No PIN/badge login existed at all before this — every staff account needed a
full email+password re-auth, friction on a POS/KDS tablet passed between
waiters mid-shift. These tests prove: a user can opt in with a valid PIN,
appears on a teammate's roster only after doing so, a teammate can switch to
them with the correct PIN and gets a real working token, a wrong PIN fails
and eventually locks out (reusing the exact mechanism /login already has —
not a separate, weaker one), and the whole thing stays tenant-scoped.
"""

import auth
import models


def _tenant_user_and_staff(db_session, suffix, tenant=None):
    if tenant is None:
        tenant = models.Tenant(name=f"PinTenant{suffix}")
        db_session.add(tenant)
        db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF,
        staff_role=models.StaffRole.WAITER,
        is_active=True,
        token_version=0,
    )
    db_session.add(user)
    db_session.commit()
    restaurant = db_session.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == tenant.id
    ).first()
    if not restaurant:
        restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}")
        db_session.add(restaurant)
        db_session.commit()
    member = models.StaffMember(
        restaurant_id=restaurant.id, user_id=user.id, name=f"Staffer {suffix}",
        role_title="Waiter",
    )
    db_session.add(member)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return tenant, user, token


def test_pin_set_rejects_invalid_formats(client, db_session):
    _, _, token = _tenant_user_and_staff(db_session, "fmt")
    headers = {"Authorization": f"Bearer {token}"}
    for bad_pin in ["123", "1234567", "abcd", "12 34"]:
        r = client.post("/api/v1/auth/pin/set", json={"pin": bad_pin}, headers=headers)
        assert r.status_code == 400, bad_pin


def test_pin_set_accepts_valid_formats(client, db_session):
    _, _, token = _tenant_user_and_staff(db_session, "validfmt")
    headers = {"Authorization": f"Bearer {token}"}
    for good_pin in ["1234", "123456"]:
        r = client.post("/api/v1/auth/pin/set", json={"pin": good_pin}, headers=headers)
        assert r.status_code == 200, good_pin


def test_roster_excludes_self_and_users_without_a_pin(client, db_session):
    tenant, caller, caller_token = _tenant_user_and_staff(db_session, "roster_caller")
    _, with_pin, with_pin_token = _tenant_user_and_staff(db_session, "roster_with_pin", tenant)
    _, without_pin, _ = _tenant_user_and_staff(db_session, "roster_without_pin", tenant)

    client.post("/api/v1/auth/pin/set", json={"pin": "1234"},
                headers={"Authorization": f"Bearer {with_pin_token}"})

    resp = client.get("/api/v1/auth/quick-switch/roster", headers={"Authorization": f"Bearer {caller_token}"})
    assert resp.status_code == 200
    names = {r["name"] for r in resp.json()}
    assert "Staffer roster_with_pin" in names
    assert "Staffer roster_without_pin" not in names   # no PIN set
    assert "Staffer roster_caller" not in names          # excludes the caller themself


def test_quick_switch_with_correct_pin_issues_a_working_token(client, db_session):
    tenant, caller, caller_token = _tenant_user_and_staff(db_session, "qs_caller")
    _, target, target_token = _tenant_user_and_staff(db_session, "qs_target", tenant)
    client.post("/api/v1/auth/pin/set", json={"pin": "5678"},
                headers={"Authorization": f"Bearer {target_token}"})

    resp = client.post(
        "/api/v1/auth/quick-switch",
        json={"user_id": target.id, "pin": "5678"},
        headers={"Authorization": f"Bearer {caller_token}"},
    )
    assert resp.status_code == 200
    new_token = resp.json()["access_token"]

    # The new token really works and really is the target, not the caller.
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == target.email


def test_quick_switch_with_wrong_pin_fails_and_eventually_locks(client, db_session):
    tenant, caller, caller_token = _tenant_user_and_staff(db_session, "wrongpin_caller")
    _, target, target_token = _tenant_user_and_staff(db_session, "wrongpin_target", tenant)
    client.post("/api/v1/auth/pin/set", json={"pin": "9999"},
                headers={"Authorization": f"Bearer {target_token}"})
    headers = {"Authorization": f"Bearer {caller_token}"}

    for _ in range(4):
        r = client.post("/api/v1/auth/quick-switch", json={"user_id": target.id, "pin": "0000"}, headers=headers)
        assert r.status_code == 401

    # 5th wrong attempt (MAX_FAILED_ATTEMPTS) trips the lock.
    r5 = client.post("/api/v1/auth/quick-switch", json={"user_id": target.id, "pin": "0000"}, headers=headers)
    assert r5.status_code == 401

    # Locked now — even the CORRECT pin is rejected until the lock expires.
    r_locked = client.post("/api/v1/auth/quick-switch", json={"user_id": target.id, "pin": "9999"}, headers=headers)
    assert r_locked.status_code == 429


def test_quick_switch_rejects_cross_tenant_target(client, db_session):
    _, caller, caller_token = _tenant_user_and_staff(db_session, "xtenant_caller")
    _, other_tenant_user, other_token = _tenant_user_and_staff(db_session, "xtenant_target")
    client.post("/api/v1/auth/pin/set", json={"pin": "1111"},
                headers={"Authorization": f"Bearer {other_token}"})

    resp = client.post(
        "/api/v1/auth/quick-switch",
        json={"user_id": other_tenant_user.id, "pin": "1111"},
        headers={"Authorization": f"Bearer {caller_token}"},
    )
    assert resp.status_code == 404


def test_pin_clear_removes_from_roster_and_blocks_switch(client, db_session):
    tenant, caller, caller_token = _tenant_user_and_staff(db_session, "clear_caller")
    _, target, target_token = _tenant_user_and_staff(db_session, "clear_target", tenant)
    target_headers = {"Authorization": f"Bearer {target_token}"}
    client.post("/api/v1/auth/pin/set", json={"pin": "2222"}, headers=target_headers)

    client.post("/api/v1/auth/pin/clear", headers=target_headers)

    roster = client.get("/api/v1/auth/quick-switch/roster", headers={"Authorization": f"Bearer {caller_token}"})
    assert "Staffer clear_target" not in {r["name"] for r in roster.json()}

    resp = client.post(
        "/api/v1/auth/quick-switch",
        json={"user_id": target.id, "pin": "2222"},
        headers={"Authorization": f"Bearer {caller_token}"},
    )
    assert resp.status_code == 404
