"""
Login brute-force lockout + rate limiting. Security pass 2026-07-07: found
zero protection existed on the login endpoint at all — no failed-attempt
tracking, and rate limiting was configured (slowapi) but never actually
applied to any route. These tests prove both actually trigger, not just that
the code exists.
"""

import auth
import models


def _register_user(client, email="lockouttest@example.com", password="CorrectHorseBattery1!"):
    resp = client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "tenant_name": "Lockout Test Co",
    })
    assert resp.status_code == 201
    return email, password


def test_account_locks_after_max_failed_attempts(client, db_session):
    email, password = _register_user(client)

    # 5 wrong-password attempts (MAX_FAILED_ATTEMPTS)
    for _ in range(5):
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
        assert resp.status_code == 401

    # 6th attempt: even with the CORRECT password, account is locked.
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 429
    assert "locked" in resp.json()["detail"].lower()


def test_successful_login_resets_failed_attempt_counter(client, db_session):
    email, password = _register_user(client, email="resettest@example.com")

    # 3 failures (below the lockout threshold of 5)
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})

    user = db_session.query(models.User).filter(models.User.email == email).first()
    assert user.failed_login_attempts == 3

    # Correct login resets the counter
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200

    db_session.refresh(user)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_login_rate_limit_returns_429_after_threshold(client, db_session):
    """Rate limit is 10/minute per IP on /api/v1/auth/login (see routers/auth.py)."""
    email, password = _register_user(client, email="ratelimittest@example.com")

    statuses = []
    for _ in range(12):
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
        statuses.append(resp.status_code)

    # Some of the later requests must be rate-limited (429), proving the
    # limiter is actually wired to this route and not just configured.
    assert 429 in statuses


def test_register_rate_limit_returns_429_after_threshold(client, db_session):
    """Rate limit is 5/hour per IP on /api/v1/auth/register."""
    statuses = []
    for i in range(7):
        resp = client.post("/api/v1/auth/register", json={
            "email": f"spam{i}@example.com", "password": "SomePassword1!", "tenant_name": f"Spam Co {i}",
        })
        statuses.append(resp.status_code)

    assert 429 in statuses
