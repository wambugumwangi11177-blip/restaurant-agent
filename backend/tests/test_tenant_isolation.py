"""
Cross-tenant isolation: a user from one tenant must never be able to read,
update, or delete another tenant's orders, reservations, or inventory items
just by guessing/enumerating sequential integer IDs (IDOR). Found during the
Phase 4 audit (directives/013_production_readiness_roadmap.md) — orders.py,
reservations.py, and inventory.py had zero tenant scoping on their
update/delete-by-id endpoints. menu.py already did this correctly (fetch,
then check db_item.restaurant.tenant_id) — these tests would have caught the
other three routers' gap immediately.
"""

import models
import auth


def _make_tenant_with_user_and_restaurant(db_session, suffix: str):
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

    token = auth.create_access_token({"sub": user.email})
    return restaurant, token


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_cannot_update_another_tenants_order_status(client, db_session):
    restaurant_a, token_a = _make_tenant_with_user_and_restaurant(db_session, "a")
    restaurant_b, token_b = _make_tenant_with_user_and_restaurant(db_session, "b")

    order_b = models.Order(
        restaurant_id=restaurant_b.id, status=models.OrderStatus.PENDING,
        payment_method=models.PaymentMethod.CASH, is_paid=False, total=1000,
    )
    db_session.add(order_b)
    db_session.commit()

    # Tenant A's user tries to change tenant B's order status.
    resp = client.patch(
        f"/orders/{order_b.id}/status",
        json={"status": "served"},
        headers=_auth_headers(token_a),
    )
    assert resp.status_code == 404

    db_session.refresh(order_b)
    assert order_b.status == models.OrderStatus.PENDING  # untouched


def test_cannot_mark_another_tenants_order_paid(client, db_session):
    restaurant_a, token_a = _make_tenant_with_user_and_restaurant(db_session, "a")
    restaurant_b, token_b = _make_tenant_with_user_and_restaurant(db_session, "b")

    order_b = models.Order(
        restaurant_id=restaurant_b.id, status=models.OrderStatus.PENDING,
        payment_method=models.PaymentMethod.PENDING, is_paid=False, total=1000,
    )
    db_session.add(order_b)
    db_session.commit()

    resp = client.patch(
        f"/orders/{order_b.id}/payment",
        json={"payment_method": "cash", "is_paid": True},
        headers=_auth_headers(token_a),
    )
    assert resp.status_code == 404

    db_session.refresh(order_b)
    assert order_b.is_paid is False  # untouched — this would otherwise be a free-order fraud vector


def test_cannot_cancel_another_tenants_reservation(client, db_session):
    from datetime import date, time
    restaurant_a, token_a = _make_tenant_with_user_and_restaurant(db_session, "a")
    restaurant_b, token_b = _make_tenant_with_user_and_restaurant(db_session, "b")

    reservation_b = models.Reservation(
        restaurant_id=restaurant_b.id, customer_name="Bob", party_size=2,
        reservation_date=date(2026, 7, 10), reservation_time=time(19, 0),
        status=models.ReservationStatus.CONFIRMED,
    )
    db_session.add(reservation_b)
    db_session.commit()

    resp = client.delete(f"/reservations/{reservation_b.id}", headers=_auth_headers(token_a))
    assert resp.status_code == 404

    still_there = db_session.query(models.Reservation).filter(models.Reservation.id == reservation_b.id).first()
    assert still_there is not None  # not deleted


def test_cannot_adjust_another_tenants_inventory(client, db_session):
    restaurant_a, token_a = _make_tenant_with_user_and_restaurant(db_session, "a")
    restaurant_b, token_b = _make_tenant_with_user_and_restaurant(db_session, "b")

    item_b = models.InventoryItem(
        restaurant_id=restaurant_b.id, item_name="Rice", quantity=100, unit="kg",
    )
    db_session.add(item_b)
    db_session.commit()

    resp = client.post(
        f"/inventory/{item_b.id}/adjust",
        json={"quantity": -100, "reason": "malicious"},
        headers=_auth_headers(token_a),
    )
    assert resp.status_code == 404

    db_session.refresh(item_b)
    assert item_b.quantity == 100  # untouched


def test_orders_list_is_paginated(client, db_session):
    """GET /orders/ used to hard-cap at 200 with no way to page past it or ask
    for fewer — now skip/limit are real query params."""
    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "pg")
    for i in range(60):
        db_session.add(models.Order(
            restaurant_id=restaurant.id, total=1000 + i,
            status=models.OrderStatus.PENDING, payment_method=models.PaymentMethod.CASH,
        ))
    db_session.commit()

    default_page = client.get("/orders/", headers=_auth_headers(token))
    assert default_page.status_code == 200
    assert len(default_page.json()) == 50   # new default limit, not all 60

    capped = client.get("/orders/?limit=10", headers=_auth_headers(token))
    assert len(capped.json()) == 10

    page_two = client.get("/orders/?limit=10&skip=10", headers=_auth_headers(token))
    assert len(page_two.json()) == 10
    assert {o["id"] for o in page_two.json()}.isdisjoint({o["id"] for o in capped.json()})

    over_max = client.get("/orders/?limit=500", headers=_auth_headers(token))
    assert over_max.status_code == 422   # le=200 rejects a request past the ceiling
