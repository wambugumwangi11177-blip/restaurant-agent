"""Sign-in handover: reset, code, first password, permissions."""

import auth
import handover
import models
from datetime import timedelta
from time_utils import utcnow


def _eleven_stack(db_session):
    tenant = models.Tenant(name="HandEleven")
    db_session.add(tenant)
    db_session.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="HandEleven")
    db_session.add(restaurant)
    db_session.flush()
    owner = models.User(
        email="owner@hand.eleven",
        hashed_password=auth.get_password_hash("OwnerOld12"),
        role=models.Role.ADMIN,
        staff_role=models.StaffRole.OWNER,
        tenant_id=tenant.id,
        is_active=True,
        active_restaurant_id=restaurant.id,
    )
    jack = models.User(
        email="jack@hand.eleven",
        hashed_password=auth.get_password_hash("JackOld12"),
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        tenant_id=tenant.id,
        is_active=True,
    )
    db_session.add_all([owner, jack])
    db_session.commit()
    return tenant, restaurant, owner, jack


def test_handover_reset_flow(client, db_session):
    _, restaurant, owner, jack = _eleven_stack(db_session)
    owner_headers = {"Authorization": f"Bearer {auth.create_access_token(data={'sub': owner.email, 'ver': owner.token_version or 0})}"}

    reset = client.post(
        f"/api/v1/eleven/logins/{jack.id}/reset-sign-in",
        headers=owner_headers,
    )
    assert reset.status_code == 200, reset.text
    code = reset.json()["handover_code"]
    assert len(code) == 6

    db_session.refresh(jack)
    assert jack.hashed_password is None
    assert jack.password_reset_required is True
    old_tv = jack.token_version or 0

    bad_login = client.post("/api/v1/auth/login", json={"email": jack.email, "password": "JackOld12"})
    assert bad_login.status_code == 403
    assert bad_login.json()["detail"]["code"] == "FIRST_PASSWORD_REQUIRED"

    need_pw = client.post("/api/v1/auth/login", json={"email": jack.email, "password": "x"})
    assert need_pw.status_code == 403
    assert need_pw.json()["detail"]["code"] == "FIRST_PASSWORD_REQUIRED"
    assert need_pw.json()["detail"]["handover_code_required"] is True

    wrong = client.post(
        "/api/v1/auth/set-initial-password",
        json={"email": jack.email, "new_password": "JackNew12", "handover_code": "000000"},
    )
    assert wrong.status_code == 400

    ok = client.post(
        "/api/v1/auth/set-initial-password",
        json={"email": jack.email, "new_password": "JackNew12", "handover_code": code},
    )
    assert ok.status_code == 200, ok.text

    db_session.refresh(jack)
    assert jack.password_reset_required is False
    assert auth.verify_password("JackNew12", jack.hashed_password)
    assert (jack.token_version or 0) >= old_tv

    signed = client.post("/api/v1/auth/login", json={"email": jack.email, "password": "JackNew12"})
    assert signed.status_code == 200

    audits = (
        db_session.query(models.StaffEntryAudit)
        .filter(models.StaffEntryAudit.restaurant_id == restaurant.id)
        .all()
    )
    actions = {a.action for a in audits}
    assert handover.HANDOVER_AUDIT_RESET in actions
    assert handover.HANDOVER_AUDIT_PASSWORD_SET in actions


def test_staff_cannot_reset_others(client, db_session):
    _, _, owner, jack = _eleven_stack(db_session)
    jack_headers = {"Authorization": f"Bearer {auth.create_access_token(data={'sub': jack.email, 'ver': jack.token_version or 0})}"}
    denied = client.post(
        f"/api/v1/eleven/logins/{owner.id}/reset-sign-in",
        headers=jack_headers,
    )
    assert denied.status_code in (403, 401)


def test_session_revoked_after_reset(client, db_session):
    _, _, owner, jack = _eleven_stack(db_session)
    token = auth.create_access_token(data={"sub": jack.email, "ver": jack.token_version or 0})
    owner_headers = {"Authorization": f"Bearer {auth.create_access_token(data={'sub': owner.email, 'ver': owner.token_version or 0})}"}
    client.post(f"/api/v1/eleven/logins/{jack.id}/reset-sign-in", headers=owner_headers)
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401