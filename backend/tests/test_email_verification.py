"""
Email verification (security audit 2026-07-17: signup never verified the
email address at all).

Covers: registration sends a verification email and defaults unverified,
a valid token marks the account verified, tokens are single-use, garbage
tokens are rejected, resend re-sends and is blocked once already verified,
and login/access is NOT blocked by an unverified email (deliberate — see
models.User.is_email_verified docstring: existing/invited staff must not be
locked out of an account they can't yet self-verify).
"""

import re

import models


def _capture_sent_email(monkeypatch):
    sent = []

    def _fake_send(to, subject, body):
        sent.append((to, subject, body))
        return True

    import routers.auth as auth_router
    monkeypatch.setattr(auth_router.email_utils, "send_email", _fake_send)
    return sent


def _extract_token(body: str) -> str:
    match = re.search(r"[?&]token=([^\s&]+)", body)
    assert match, f"no token found in email body: {body!r}"
    return match.group(1)


def test_register_sends_verification_email_and_defaults_unverified(client, db_session, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    resp = client.post("/api/v1/auth/register",
                        json={"email": "verify1@e.com", "password": "GoodPass1", "tenant_name": "T"})
    assert resp.status_code == 201
    assert len(sent) == 1
    assert "verify" in sent[0][1].lower()

    token = resp.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["is_email_verified"] is False


def test_verify_email_with_valid_token(client, db_session, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    resp = client.post("/api/v1/auth/register",
                        json={"email": "verify2@e.com", "password": "GoodPass1", "tenant_name": "T"})
    token = resp.json()["access_token"]
    raw = _extract_token(sent[0][2])

    verify = client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert verify.status_code == 200

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["is_email_verified"] is True


def test_verify_email_token_is_single_use(client, db_session, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    client.post("/api/v1/auth/register",
                json={"email": "verify3@e.com", "password": "GoodPass1", "tenant_name": "T"})
    raw = _extract_token(sent[0][2])

    first = client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert second.status_code == 400


def test_garbage_verify_token_rejected(client, db_session):
    resp = client.post("/api/v1/auth/verify-email", json={"token": "garbage"})
    assert resp.status_code == 400


def test_resend_verification_then_blocked_once_verified(client, db_session, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    resp = client.post("/api/v1/auth/register",
                        json={"email": "verify4@e.com", "password": "GoodPass1", "tenant_name": "T"})
    token = resp.json()["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}

    sent.clear()
    resend = client.post("/api/v1/auth/resend-verification", headers=hdr)
    assert resend.status_code == 200
    assert len(sent) == 1

    raw = _extract_token(sent[0][2])
    client.post("/api/v1/auth/verify-email", json={"token": raw})

    blocked = client.post("/api/v1/auth/resend-verification", headers=hdr)
    assert blocked.status_code == 400


def test_unverified_account_can_still_login_and_use_the_app(client, db_session, monkeypatch):
    """Deliberate: verification is informational, not a login gate (see
    models.User.is_email_verified docstring)."""
    _capture_sent_email(monkeypatch)
    client.post("/api/v1/auth/register",
                json={"email": "verify5@e.com", "password": "GoodPass1", "tenant_name": "T"})

    login = client.post("/api/v1/auth/login",
                         json={"email": "verify5@e.com", "password": "GoodPass1"})
    assert login.status_code == 200
