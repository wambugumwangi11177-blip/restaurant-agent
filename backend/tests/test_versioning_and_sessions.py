"""
API versioning (additive dual-mount) and JWT session revocation (token_version).
"""

import auth
import models

from tests.factories import seed_owner


def test_legacy_and_versioned_data_paths_both_resolve(client):
    assert client.get("/staff/").status_code == 401
    assert client.get("/api/v1/staff/").status_code == 401


def test_health_and_webhooks_are_not_versioned(client):
    assert client.get("/health/").status_code == 200
    assert client.get("/api/v1/health/").status_code == 404
    assert client.post("/webhooks/stripe", content=b"{}").status_code == 404
    assert client.post("/api/v1/webhooks/stripe", content=b"{}").status_code == 404


def test_openapi_documents_versioned_and_hides_legacy(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/staff/" in paths
    assert "/orders/" not in paths


def test_logout_all_revokes_existing_tokens(client, db_session):
    user, _, headers = seed_owner(db_session, email="rev@example.com", password="password123")
    token = headers["Authorization"].removeprefix("Bearer ")
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    revoked = client.post("/api/v1/auth/logout-all", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["token_version"] == 1

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401

    r2 = client.post("/api/v1/auth/login", json={"email": user.email, "password": "password123"})
    assert r2.status_code == 200
    h2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=h2).status_code == 200


def test_token_with_stale_version_is_rejected(client, db_session):
    user = models.User(
        tenant_id=None, email="stale@example.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, token_version=3,
    )
    db_session.add(user)
    db_session.commit()

    stale = auth.create_access_token({"sub": user.email, "ver": 2})
    fresh = auth.create_access_token({"sub": user.email, "ver": 3})
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {stale}"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


def test_legacy_token_without_ver_claim_still_valid(client, db_session):
    user = models.User(
        tenant_id=None, email="legacy@example.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, token_version=0,
    )
    db_session.add(user)
    db_session.commit()
    legacy = auth.create_access_token({"sub": user.email})
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200


def test_public_register_and_restaurant_login_disabled(client):
    assert client.post("/api/v1/auth/register", json={
        "email": "x@e.com", "password": "GoodPass1", "tenant_name": "X",
    }).status_code == 404
    assert client.post("/api/v1/auth/login/restaurant", json={
        "restaurant_name": "Eleven", "password": "GoodPass1",
    }).status_code == 404