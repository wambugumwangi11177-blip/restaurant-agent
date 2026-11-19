"""
Login brute-force lockout + rate limiting.
"""

import models
from tests.factories import seed_owner


def _creds(db_session, email="lockouttest@example.com", password="CorrectHorseBattery1!"):
    user, _, _ = seed_owner(db_session, email=email, password=password, tenant_name="Lockout Test Co")
    return user.email, password


def test_account_locks_after_max_failed_attempts(client, db_session):
    email, password = _creds(db_session)

    for _ in range(5):
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
        assert resp.status_code == 401

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 429
    assert "locked" in resp.json()["detail"].lower()


def test_successful_login_resets_failed_attempt_counter(client, db_session):
    email, password = _creds(db_session, email="resettest@example.com")

    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})

    user = db_session.query(models.User).filter_by(email=email).one()
    assert user.failed_login_attempts == 3

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200

    db_session.refresh(user)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_login_rate_limit_returns_429_after_threshold(client, db_session):
    email, password = _creds(db_session, email="ratelimittest@example.com")

    statuses = []
    for _ in range(12):
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
        statuses.append(resp.status_code)

    assert 429 in statuses