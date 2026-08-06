"""
`GET /health/config` — post-deploy configuration readiness.

`startup_checks.enforce_startup_checks()` runs once at boot and writes to the
log. On Railway that means the answer to "did my env vars actually take effect?"
lives in a line that has scrolled away by the time anyone asks — and a soft
warning (CORS_ORIGINS, Sentry) doesn't block the boot at all, so a degraded
deploy looks identical to a healthy one from outside.

The security property pinned here matters as much as the feature: this endpoint
must never be reachable without admin auth, and must never echo a value. An
unauthenticated endpoint announcing "MPESA_CALLBACK_TOKEN is not set" would tell
an attacker the payment callback is forgeable — precisely what the token exists
to prevent.
"""

import auth
import models


def _token(db, role=models.Role.ADMIN, suffix="h"):
    tenant = models.Tenant(name=f"HC{suffix}")
    db.add(tenant); db.commit()
    user = models.User(tenant_id=tenant.id, email=f"hc{suffix}@e.com",
                       hashed_password=auth.get_password_hash("x"),
                       role=role, token_version=0)
    db.add(user); db.commit()
    return auth.create_access_token({"sub": user.email, "ver": 0})


def test_requires_authentication(client, db_session):
    assert client.get("/health/config").status_code == 401


def test_staff_cannot_read_config(client, db_session):
    token = _token(db_session, models.Role.STAFF, "staff")
    r = client.get("/health/config", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_gets_a_readiness_report(client, db_session):
    token = _token(db_session, models.Role.ADMIN, "admin")
    r = client.get("/health/config", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    body = r.json()
    assert body["status"] in {"ready", "degraded", "blocked"}
    assert isinstance(body["blocking_problems"], list)
    assert isinstance(body["warnings"], list)
    assert set(body["integrations"]) >= {
        "database", "mpesa", "mpesa_callback_token", "twilio", "llm", "sentry",
    }
    # Presence booleans only — never a value.
    assert all(isinstance(v, bool) for v in body["integrations"].values())


def test_reports_blocked_when_mpesa_is_configured_without_a_callback_token(
    client, db_session, monkeypatch
):
    """
    The forgeable-payment gap: with Daraja credentials set and no callback
    token, anyone who can guess a CheckoutRequestID can forge a settlement.
    """
    for key in ("MPESA_CONSUMER_KEY", "MPESA_CONSUMER_SECRET",
                "MPESA_SHORTCODE", "MPESA_PASSKEY"):
        monkeypatch.setenv(key, "set")
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)
    monkeypatch.setenv("MPESA_ENV", "production")

    token = _token(db_session, models.Role.ADMIN, "blocked")
    body = client.get("/health/config",
                      headers={"Authorization": f"Bearer {token}"}).json()

    assert body["status"] == "blocked"
    assert body["is_production"] is True
    assert any("MPESA_CALLBACK_TOKEN" in p for p in body["blocking_problems"])
    assert body["integrations"]["mpesa_callback_token"] is False


def test_secret_values_never_appear_in_the_response(client, db_session, monkeypatch):
    sentinel = "super-secret-token-value-do-not-leak"
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", sentinel)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", sentinel)

    token = _token(db_session, models.Role.ADMIN, "leak")
    raw = client.get("/health/config",
                     headers={"Authorization": f"Bearer {token}"}).text
    assert sentinel not in raw
