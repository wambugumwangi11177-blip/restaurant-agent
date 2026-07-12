"""
HTTP contract for POST /ai/simulate — auth-gated, flag-gated, and returns the
engine's projection shape for a real item.
"""

from datetime import timedelta

import models
import auth
from time_utils import utcnow


def _auth(db_session):
    tenant = models.Tenant(name="Sim Tenant")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id, email="sim@example.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Sim Grill", address="Nairobi")
    db_session.add_all([user, restaurant])
    db_session.commit()
    token = auth.create_access_token({"sub": user.email})
    return restaurant, {"Authorization": f"Bearer {token}"}


def _seed_item(db_session, restaurant_id):
    item = models.MenuItem(restaurant_id=restaurant_id, name="Burger",
                           price=1000, cost_price=400, category="main")
    db_session.add(item)
    db_session.commit()
    for d in range(20):
        o = models.Order(
            restaurant_id=restaurant_id, status=models.OrderStatus.SERVED,
            payment_method=models.PaymentMethod.CASH, is_paid=True, total=1000,
            created_at=utcnow() - timedelta(days=d),
        )
        db_session.add(o)
        db_session.flush()
        db_session.add(models.OrderItem(order_id=o.id, menu_item_id=item.id, quantity=1, unit_price=1000))
    db_session.commit()
    return item


def test_simulate_requires_auth(client):
    resp = client.post("/ai/simulate", json={"change": {"type": "price_change", "item_id": 1, "new_price": 1200}})
    assert resp.status_code in (401, 403)


def test_simulate_returns_projection(client, db_session):
    restaurant, headers = _auth(db_session)
    item = _seed_item(db_session, restaurant.id)

    resp = client.post("/ai/simulate", headers=headers, json={
        "change": {"type": "price_change", "item_id": item.id, "new_price": 1100},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is True
    assert body["change"]["new_price"] == 1100
    assert "verdict" in body and body["verdict"] in ("YES", "CAUTION", "NO")
    assert "profit_cents_month" in body["deltas"]


def test_simulate_disabled_by_flag(client, db_session, monkeypatch):
    restaurant, headers = _auth(db_session)
    _seed_item(db_session, restaurant.id)
    monkeypatch.setenv("FEATURE_SIMULATION", "false")
    resp = client.post("/ai/simulate", headers=headers, json={
        "change": {"type": "price_change", "item_id": 1, "new_price": 1100},
    })
    assert resp.status_code == 200
    assert resp.json()["available"] is False
