"""
backend/tests/test_versioning_and_sessions.py
─────────────────────────────────────────────────
API versioning (additive dual-mount) and JWT session revocation (token_version).
"""

import auth
import models


# ── API versioning ───────────────────────────────────────────────────────────

def test_legacy_and_versioned_data_paths_both_resolve(client):
    # 401 (auth required), NOT 404 → the route exists at both mounts.
    assert client.get("/orders/").status_code == 401
    assert client.get("/api/v1/orders/").status_code == 401


def test_health_and_webhooks_are_not_versioned(client):
    assert client.get("/health/").status_code == 200
    assert client.get("/api/v1/health/").status_code == 404          # not versioned
    assert client.post("/webhooks/stripe", content=b"{}").status_code == 501
    assert client.post("/api/v1/webhooks/stripe", content=b"{}").status_code == 404  # not versioned


def test_openapi_documents_versioned_and_hides_legacy(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/orders/" in paths          # canonical, documented
    assert "/orders/" not in paths             # legacy kept working but hidden (deprecated)


# ── JWT session revocation ───────────────────────────────────────────────────

def _register(client, email="rev@example.com", pw="password123"):
    r = client.post("/api/v1/auth/register",
                    json={"email": email, "password": pw, "tenant_name": "T"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_logout_all_revokes_existing_tokens(client):
    token = _register(client)
    h = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/auth/me", headers=h).status_code == 200

    revoked = client.post("/api/v1/auth/logout-all", headers=h)
    assert revoked.status_code == 200
    assert revoked.json()["token_version"] == 1

    # The token used to revoke (and any other outstanding token) is now invalid.
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401

    # A fresh login mints a token at the new version and works again.
    r2 = client.post("/api/v1/auth/login",
                     json={"email": "rev@example.com", "password": "password123"})
    assert r2.status_code == 200
    h2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=h2).status_code == 200


def test_token_with_stale_version_is_rejected(client, db_session):
    # Mint a token whose ver is behind the user's current token_version.
    user = models.User(
        tenant_id=None, email="stale@example.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, token_version=3,
    )
    db_session.add(user)
    db_session.commit()

    stale = auth.create_access_token({"sub": user.email, "ver": 2})
    fresh = auth.create_access_token({"sub": user.email, "ver": 3})
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {stale}"}).status_code == 401
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


def test_legacy_token_without_ver_claim_still_valid(client, db_session):
    # Backward compat: a pre-feature token carries no "ver" → treated as 0, which
    # matches a fresh user's default token_version.
    user = models.User(
        tenant_id=None, email="legacy@example.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email})  # no ver claim
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {token}"}).status_code == 200
