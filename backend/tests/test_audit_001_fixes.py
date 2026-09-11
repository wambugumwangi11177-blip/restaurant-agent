"""
Regression tests for LAI-AUDIT-001 fixes (AUD-002 / AUD-004 / AUD-005).

AUD-002 — order-total arithmetic was duplicated inline in create_order and
          create_public_order (already divergent); now one shared
          domain/pricing.build_order_lines() serves both.
AUD-004 — invalid order_type / payment_method / delivery_channel used to be
          silently coerced to defaults (DINE_IN / TAKEOUT / PENDING /
          WALK_IN), i.e. a typo'd payment_method recorded the order as
          UNPAID. Now 400, mirroring update_order_status's existing 400.
AUD-005 — an unrecognised ?status= filter on GET /orders used to be silently
          dropped, returning the UNFILTERED list. Now 400.

Each test pins the *fixed* behavior AND the valid-path still works.
"""

import pytest

import auth
import models


@pytest.fixture
def owner_setup(db_session):
    """One tenant, Owner, restaurant, two menu items. Mirrors the local
    fixture pattern used by test_order_audit.py / test_recipe_*.py."""
    tenant = models.Tenant(name="RT-fixes")
    db_session.add(tenant)
    db_session.commit()
    owner = models.User(
        tenant_id=tenant.id, email="owner-fixes@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER, token_version=0,
    )
    db_session.add(owner)
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R-fixes", address="x")
    db_session.add(restaurant)
    db_session.commit()

    burger = models.MenuItem(restaurant_id=restaurant.id, name="Burger",
                             price=500, cost_price=200, category="mains")
    pizza = models.MenuItem(restaurant_id=restaurant.id, name="Pizza",
                            price=900, cost_price=350, category="mains",
                            is_available=False)  # public path must refuse
    db_session.add_all([burger, pizza])
    db_session.commit()

    token = auth.create_access_token({"sub": owner.email, "ver": 0})
    return restaurant, owner, token, burger, pizza


# ── AUD-002: shared pricing arithmetic — valid path, staff route ────────────

def test_create_order_total_uses_shared_pricing(client, db_session, owner_setup):
    restaurant, owner, token, burger, pizza = owner_setup
    r = client.post(
        "/orders/",
        json={"items": [
            {"menu_item_id": burger.id, "quantity": 2},
            {"menu_item_id": pizza.id, "quantity": 1},
        ]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # 2×500 + 1×900 = 1900 cents
    assert body["total"] == 1900
    assert len(body["items"]) == 2
    assert {i["unit_price"] for i in body["items"]} == {500, 900}


# ── AUD-004: no more silent enum coercion on create ─────────────────────────

def test_create_order_rejects_invalid_payment_method(client, owner_setup):
    restaurant, owner, token, burger, pizza = owner_setup
    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": burger.id, "quantity": 1}],
              "payment_method": "mpesa-typo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "payment_method" in r.json()["detail"]


def test_create_order_rejects_invalid_order_type(client, owner_setup):
    restaurant, owner, token, burger, pizza = owner_setup
    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": burger.id, "quantity": 1}],
              "order_type": "dinein-typo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "order_type" in r.json()["detail"]


def test_create_order_rejects_invalid_delivery_channel(client, owner_setup):
    restaurant, owner, token, burger, pizza = owner_setup
    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": burger.id, "quantity": 1}],
              "delivery_channel": "walkin-typo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "delivery_channel" in r.json()["detail"]


def test_public_order_rejects_invalid_payment_method(client, owner_setup):
    restaurant, owner, token, burger, pizza = owner_setup
    r = client.post(
        f"/orders/public?restaurant_id={restaurant.id}",
        json={"items": [{"menu_item_id": burger.id, "quantity": 1}],
              "payment_method": "card-typo"},
    )
    assert r.status_code == 400
    assert "payment_method" in r.json()["detail"]


# ── AUD-002 (public path): shared builder + availability filter intact ──────

def test_public_order_refuses_unavailable_item(client, owner_setup):
    restaurant, owner, token, burger, pizza = owner_setup
    r = client.post(
        f"/orders/public?restaurant_id={restaurant.id}",
        json={"items": [{"menu_item_id": pizza.id, "quantity": 1}]},
    )
    assert r.status_code == 404
    assert "unavailable" in r.json()["detail"]


def test_public_order_total_still_correct(client, owner_setup):
    restaurant, owner, token, burger, pizza = owner_setup
    r = client.post(
        f"/orders/public?restaurant_id={restaurant.id}",
        json={"items": [{"menu_item_id": burger.id, "quantity": 3}]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["total"] == 1500  # 3×500


# ── AUD-005: invalid ?status= now 400 instead of unfiltered list ────────────

def test_list_orders_rejects_invalid_status_filter(client, owner_setup):
    restaurant, owner, token, burger, pizza = owner_setup
    r = client.get(
        "/orders/?status=cooked-typo",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "status" in r.json()["detail"]


def test_list_orders_valid_status_filter_still_works(client, db_session, owner_setup):
    restaurant, owner, token, burger, pizza = owner_setup
    # Seed one order so the filtered list isn't trivially empty.
    order = models.Order(restaurant_id=restaurant.id, total=500,
                         status=models.OrderStatus.PENDING)
    db_session.add(order)
    db_session.commit()

    r = client.get(
        "/orders/?status=pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["status"] == "pending"
