"""
backend/tests/test_phase1_hardening.py
─────────────────────────────────────────
Regression tests for the Phase 1 production-hardening pass:

  • menu.py update/delete are now tenant-scoped (fail closed → 404), closing the
    IDOR the tenant-isolation suite never actually covered for menu items.
  • rate_limit._client_ip reads the trusted proxy hop (right side of XFF), so a
    spoofed leading value can't mint a fresh rate-limit key.
  • /webhooks/stripe fails closed with 501 (was an unsigned 200 stub).
  • BodySizeLimitMiddleware rejects oversized bodies with 413.
  • CorrelationIdMiddleware sets/echoes X-Request-ID.
"""

import types
import models
import auth


# ── helpers (mirror tests/test_tenant_isolation.py) ──────────────────────────

def _make_tenant(db_session, suffix: str):
    tenant = models.Tenant(name=f"Tenant {suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"owner_{suffix}@example.com",
        hashed_password=auth.get_password_hash("irrelevant"),
        role=models.Role.ADMIN,
    )
    db_session.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"Restaurant {suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    return restaurant, auth.create_access_token({"sub": user.email})


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── menu.py tenant scoping (the IDOR the old post-fetch check masked) ─────────

def test_cannot_update_another_tenants_menu_item(client, db_session):
    _, token_a = _make_tenant(db_session, "a")
    restaurant_b, _ = _make_tenant(db_session, "b")
    item_b = models.MenuItem(restaurant_id=restaurant_b.id, name="Ugali", price=200, category="mains")
    db_session.add(item_b)
    db_session.commit()

    resp = client.put(f"/menu/{item_b.id}", json={"name": "hacked"}, headers=_headers(token_a))
    assert resp.status_code == 404

    db_session.refresh(item_b)
    assert item_b.name == "Ugali"  # untouched


def test_cannot_delete_another_tenants_menu_item(client, db_session):
    _, token_a = _make_tenant(db_session, "a")
    restaurant_b, _ = _make_tenant(db_session, "b")
    item_b = models.MenuItem(restaurant_id=restaurant_b.id, name="Sukuma", price=100, category="sides")
    db_session.add(item_b)
    db_session.commit()

    resp = client.delete(f"/menu/{item_b.id}", headers=_headers(token_a))
    assert resp.status_code == 404

    still_there = db_session.query(models.MenuItem).filter(models.MenuItem.id == item_b.id).first()
    assert still_there is not None  # not deleted


def test_owner_can_still_update_own_menu_item(client, db_session):
    restaurant_a, token_a = _make_tenant(db_session, "a")
    item_a = models.MenuItem(restaurant_id=restaurant_a.id, name="Pilau", price=500, category="mains")
    db_session.add(item_a)
    db_session.commit()

    resp = client.put(f"/menu/{item_a.id}", json={"price": 550}, headers=_headers(token_a))
    assert resp.status_code == 200
    db_session.refresh(item_a)
    assert item_a.price == 550


# ── XFF rate-limit key: read the trusted hop, never the spoofable leading one ─

def _fake_request(xff: str | None, peer: str = "10.0.0.1"):
    headers = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    return types.SimpleNamespace(
        headers=headers,
        client=types.SimpleNamespace(host=peer),
    )


def test_client_ip_ignores_spoofed_leading_xff(monkeypatch):
    import rate_limit
    monkeypatch.setattr(rate_limit, "_TRUSTED_PROXY_HOPS", 1)
    # Attacker prepends a fake IP; the edge proxy appended the real one on the right.
    assert rate_limit._client_ip(_fake_request("1.2.3.4, 9.9.9.9")) == "9.9.9.9"
    # Many spoofed values still resolve to the trusted-appended rightmost hop.
    assert rate_limit._client_ip(_fake_request("a, b, c, 9.9.9.9")) == "9.9.9.9"
    # Single real value (direct/one proxy) passes through.
    assert rate_limit._client_ip(_fake_request("9.9.9.9")) == "9.9.9.9"
    # No header → raw peer.
    assert rate_limit._client_ip(_fake_request(None)) == "10.0.0.1"


# ── webhook / middleware behaviours ──────────────────────────────────────────

def test_stripe_webhook_disabled_501(client):
    assert client.post("/webhooks/stripe", content=b"{}").status_code == 501


def test_oversized_body_rejected_413(client, monkeypatch):
    import middleware.body_limit as bl
    monkeypatch.setattr(bl, "MAX_REQUEST_BODY_BYTES", 100)
    # 200 bytes > 100-byte cap → 413 on the Content-Length fast path, before the route.
    resp = client.post("/orders/public?restaurant_id=1", content=b"x" * 200,
                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 413


def test_correlation_id_present_and_echoed(client):
    r = client.get("/health/")
    assert r.headers.get("X-Request-ID")
    r2 = client.get("/health/", headers={"X-Request-ID": "trace-xyz-1"})
    assert r2.headers.get("X-Request-ID") == "trace-xyz-1"
