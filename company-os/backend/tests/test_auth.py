import pytest

from app.config import ConfigError, Settings, check_startup
from app.security import totp_now
from tests.conftest import STRONG_PASSWORD


def test_login_and_me(client, make_workspace):
    w = make_workspace("acme")
    r = client.get("/api/v1/auth/me", headers=w["h"])
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "founder"
    assert body["workspace"]["slug"] == "acme"
    assert "approvals.decide" in body["permissions"]


def test_wrong_password_is_generic_and_locks_out(client, make_workspace):
    make_workspace("acme")
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"email": "founder@acme.example.com", "password": "nope-Nope-123"})
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid email or password"
    r = client.post("/api/v1/auth/login", json={"email": "founder@acme.example.com", "password": STRONG_PASSWORD})
    assert r.status_code == 423


def test_unknown_email_is_indistinguishable(client, make_workspace):
    make_workspace("acme")
    r = client.post("/api/v1/auth/login", json={"email": "nobody@acme.example.com", "password": STRONG_PASSWORD})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


def test_no_token_or_bad_token_rejected(client, make_workspace):
    make_workspace("acme")
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401


def test_mfa_enrolment_and_login(client, make_workspace):
    w = make_workspace("acme")
    setup = client.post("/api/v1/auth/mfa/setup", headers=w["h"]).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert client.post("/api/v1/auth/mfa/enable", headers=w["h"], json={"code": "000000"}).status_code == 400
    assert client.post("/api/v1/auth/mfa/enable", headers=w["h"], json={"code": totp_now(setup["secret"])}).status_code == 200

    r = client.post("/api/v1/auth/login", json={"email": "founder@acme.example.com", "password": STRONG_PASSWORD})
    assert r.status_code == 401 and r.json()["detail"] == "mfa_required"
    r = client.post("/api/v1/auth/login", json={"email": "founder@acme.example.com", "password": STRONG_PASSWORD,
                                                "totp_code": totp_now(setup["secret"])})
    assert r.status_code == 200


def test_logout_all_revokes_existing_tokens(client, make_workspace):
    w = make_workspace("acme")
    assert client.post("/api/v1/auth/logout-all", headers=w["h"]).status_code == 200
    assert client.get("/api/v1/auth/me", headers=w["h"]).status_code == 401


def test_password_change_policy_and_revocation(client, make_workspace):
    w = make_workspace("acme")
    weak = client.post("/api/v1/auth/password", headers=w["h"],
                       json={"current_password": STRONG_PASSWORD, "new_password": "short"})
    assert weak.status_code == 422
    ok = client.post("/api/v1/auth/password", headers=w["h"],
                     json={"current_password": STRONG_PASSWORD, "new_password": "Another-Strong-Pass-42"})
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me", headers=w["h"]).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"}).status_code == 200


def test_removed_member_loses_access_immediately(client, make_workspace, add_member):
    w = make_workspace("acme")
    staff_h = add_member(w["h"], "staff", "staff@acme.example.com")
    assert client.get("/api/v1/auth/me", headers=staff_h).status_code == 200
    members = client.get("/api/v1/members", headers=w["h"]).json()
    staff_id = next(m["user_id"] for m in members if m["email"] == "staff@acme.example.com")
    assert client.delete(f"/api/v1/members/{staff_id}", headers=w["h"]).status_code == 204
    assert client.get("/api/v1/auth/me", headers=staff_h).status_code == 401


def test_last_founder_cannot_be_demoted_or_removed(client, make_workspace):
    w = make_workspace("acme")
    uid = w["user"].id
    assert client.patch(f"/api/v1/members/{uid}", headers=w["h"], json={"role": "staff"}).status_code == 409
    assert client.delete(f"/api/v1/members/{uid}", headers=w["h"]).status_code == 409


def test_new_member_requires_strong_password(client, make_workspace):
    w = make_workspace("acme")
    r = client.post("/api/v1/members", headers=w["h"], json={
        "email": "x@acme.example.com", "full_name": "X", "role": "staff", "password": "weakpass"})
    assert r.status_code == 422


def test_production_config_guard():
    with pytest.raises(ConfigError) as e:
        check_startup(Settings(env="production"))
    msg = str(e.value)
    assert "JWT_SECRET" in msg and "DATABASE_URL" in msg and "PUBLIC_BASE_URL" in msg
    ok = Settings(env="production", jwt_secret="x" * 40, database_url="postgresql://u:p@db.internal/os",
                  public_base_url="https://os.example.com", cors_origins=["https://app.example.com"])
    warnings = check_startup(ok)
    assert any("LLM" in w for w in warnings)
