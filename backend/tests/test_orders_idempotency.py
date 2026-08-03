"""
Order idempotency key (tech-debt D15). Backs the POS offline queue: a client
retries the same order payload after a network drop, and the server must
return the original order instead of creating a duplicate. These tests prove
the replay-returns-existing behavior, that a missing key is unaffected, and
that the same key across two different tenants creates two distinct orders
(a key collision must never leak one tenant's order to another).
"""

import auth
import models


def _make_tenant_with_admin_and_menu_item(db_session, suffix: str):
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

    item = models.MenuItem(restaurant_id=restaurant.id, name="Burger", price=50000, is_available=True)
    db_session.add(item)
    db_session.commit()

    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return restaurant, item, token


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_replaying_the_same_key_returns_the_original_order(client, db_session):
    restaurant, item, token = _make_tenant_with_admin_and_menu_item(db_session, "a")

    payload = {
        "items": [{"menu_item_id": item.id, "quantity": 2}],
        "payment_method": "cash",
        "idempotency_key": "client-generated-key-1",
    }

    first = client.post("/orders/", json=payload, headers=_auth_headers(token))
    assert first.status_code == 200
    first_id = first.json()["id"]

    # Same key, same payload — simulates a retried submission after the client
    # never saw the first response (network drop right after the server wrote it).
    second = client.post("/orders/", json=payload, headers=_auth_headers(token))
    assert second.status_code == 200
    assert second.json()["id"] == first_id

    count = db_session.query(models.Order).filter(models.Order.restaurant_id == restaurant.id).count()
    assert count == 1


def test_missing_idempotency_key_behaves_as_before(client, db_session):
    restaurant, item, token = _make_tenant_with_admin_and_menu_item(db_session, "b")

    payload = {"items": [{"menu_item_id": item.id, "quantity": 1}], "payment_method": "cash"}

    first = client.post("/orders/", json=payload, headers=_auth_headers(token))
    second = client.post("/orders/", json=payload, headers=_auth_headers(token))
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] != second.json()["id"]

    count = db_session.query(models.Order).filter(models.Order.restaurant_id == restaurant.id).count()
    assert count == 2


def test_same_key_across_tenants_creates_distinct_orders(client, db_session):
    restaurant_a, item_a, token_a = _make_tenant_with_admin_and_menu_item(db_session, "tenantA")
    restaurant_b, item_b, token_b = _make_tenant_with_admin_and_menu_item(db_session, "tenantB")

    shared_key = "collides-across-tenants"

    resp_a = client.post("/orders/", json={
        "items": [{"menu_item_id": item_a.id, "quantity": 1}],
        "payment_method": "cash", "idempotency_key": shared_key,
    }, headers=_auth_headers(token_a))
    resp_b = client.post("/orders/", json={
        "items": [{"menu_item_id": item_b.id, "quantity": 1}],
        "payment_method": "cash", "idempotency_key": shared_key,
    }, headers=_auth_headers(token_b))

    assert resp_a.status_code == 200 and resp_b.status_code == 200
    assert resp_a.json()["id"] != resp_b.json()["id"]
