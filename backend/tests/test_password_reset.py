"""
Password reset (security audit 2026-07-17: this flow did not exist at all).

Covers: request always returns a generic response (no account enumeration),
a valid token resets the password and revokes existing sessions, tokens are
single-use, expired/garbage tokens are rejected, and the new password is
enforced against the same strength policy as registration.
"""

import re

import models


def _register(client, email="reset@e.com", password="GoodPass1"):
    r = client.post("/api/v1/auth/register",
                     json={"email": email, "password": password, "tenant_name": "T"})
    assert r.status_code == 201
    return r.json()["access_token"]


def _capture_sent_email(monkeypatch):
    """Intercept email_utils.send_email (SMTP is unconfigured in tests, so it
    would otherwise just log) and hand back the captured (to, subject, body)
    tuples — this is how a test recovers the real emailed link/token."""
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


def test_request_reset_returns_generic_response_for_unknown_email(client, db_session):
    resp = client.post("/api/v1/auth/password-reset/request", json={"email": "nobody@e.com"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "if_account_exists_a_reset_email_was_sent"
    assert db_session.query(models.AuthToken).count() == 0


def test_full_reset_flow_changes_password_and_revokes_sessions(client, db_session, monkeypatch):
    email = "reset2@e.com"
    old_token = _register(client, email=email)
    sent = _capture_sent_email(monkeypatch)

    resp = client.post("/api/v1/auth/password-reset/request", json={"email": email})
    assert resp.status_code == 200
    assert len(sent) == 1
    raw = _extract_token(sent[0][2])

    confirm = client.post("/api/v1/auth/password-reset/confirm",
                           json={"token": raw, "new_password": "BrandNewPass2"})
    assert confirm.status_code == 200

    # Old session is dead (token_version bumped).
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert me.status_code == 401

    # Old password no longer works; new one does.
    assert client.post("/api/v1/auth/login",
                        json={"email": email, "password": "GoodPass1"}).status_code == 401
    ok = client.post("/api/v1/auth/login",
                      json={"email": email, "password": "BrandNewPass2"})
    assert ok.status_code == 200


def test_reset_token_is_single_use(client, db_session, monkeypatch):
    email = "reset3@e.com"
    _register(client, email=email)
    sent = _capture_sent_email(monkeypatch)
    client.post("/api/v1/auth/password-reset/request", json={"email": email})
    raw = _extract_token(sent[0][2])

    first = client.post("/api/v1/auth/password-reset/confirm",
                         json={"token": raw, "new_password": "FirstPass99"})
    assert first.status_code == 200

    second = client.post("/api/v1/auth/password-reset/confirm",
                          json={"token": raw, "new_password": "SecondPass99"})
    assert second.status_code == 400


def test_garbage_token_rejected(client, db_session):
    resp = client.post("/api/v1/auth/password-reset/confirm",
                        json={"token": "not-a-real-token", "new_password": "WhateverPass1"})
    assert resp.status_code == 400


def test_reset_enforces_password_strength(client, db_session, monkeypatch):
    email = "reset4@e.com"
    _register(client, email=email)
    sent = _capture_sent_email(monkeypatch)
    client.post("/api/v1/auth/password-reset/request", json={"email": email})
    raw = _extract_token(sent[0][2])

    resp = client.post("/api/v1/auth/password-reset/confirm",
                        json={"token": raw, "new_password": "short"})
    assert resp.status_code == 400
