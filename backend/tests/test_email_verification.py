"""
Email verification — resend/verify flows without public registration.
"""

import re

from tests.factories import seed_owner


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


def test_resend_defaults_unverified_and_sends_email(client, db_session, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    _, _, headers = seed_owner(db_session, email="verify1@e.com", is_email_verified=False)
    resend = client.post("/api/v1/auth/resend-verification", headers=headers)
    assert resend.status_code == 200
    assert len(sent) == 1

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["is_email_verified"] is False


def test_verify_email_with_valid_token(client, db_session, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    user, _, headers = seed_owner(db_session, email="verify2@e.com", is_email_verified=False)
    client.post("/api/v1/auth/resend-verification", headers=headers)
    raw = _extract_token(sent[0][2])

    verify = client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert verify.status_code == 200

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["is_email_verified"] is True


def test_verify_email_token_is_single_use(client, db_session, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    _, _, headers = seed_owner(db_session, email="verify3@e.com", is_email_verified=False)
    client.post("/api/v1/auth/resend-verification", headers=headers)
    raw = _extract_token(sent[0][2])

    first = client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert second.status_code == 400


def test_garbage_verify_token_rejected(client, db_session):
    resp = client.post("/api/v1/auth/verify-email", json={"token": "garbage"})
    assert resp.status_code == 400


def test_resend_blocked_once_verified(client, db_session, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    _, _, headers = seed_owner(db_session, email="verify4@e.com", is_email_verified=False)
    client.post("/api/v1/auth/resend-verification", headers=headers)
    raw = _extract_token(sent[0][2])
    client.post("/api/v1/auth/verify-email", json={"token": raw})

    blocked = client.post("/api/v1/auth/resend-verification", headers=headers)
    assert blocked.status_code == 400


def test_unverified_account_can_still_login(client, db_session):
    user, _, _ = seed_owner(db_session, email="verify5@e.com", password="GoodPass1", is_email_verified=False)
    login = client.post("/api/v1/auth/login", json={"email": user.email, "password": "GoodPass1"})
    assert login.status_code == 200