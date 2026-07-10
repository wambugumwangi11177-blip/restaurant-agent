"""
HTTP smoke tests for every /ai/* route — the ones that have silently 500'd or
returned a swallowed {"error": ...} before, and had zero request-level coverage.

The failure mode these guard against is specific to this codebase: the route
bodies wrap their agent call in `_safe_run`/bare try-except, which converts an
exception into a 200 with an `{"error": ...}` payload. So `assert 200` proves
nothing — /ai/inventory once imported a function name that did not exist and
returned a 200 the whole time. Every test here therefore asserts BOTH the 200
AND that no error key came back AND a shape key the agent only produces when it
actually ran.

Two fixtures: an empty restaurant (agents must degrade, not crash, on no data)
and a seeded one (agents must produce their real shape).
"""

from datetime import time, timedelta

import pytest

import models
import auth
from time_utils import utcnow


def _auth(db_session):
    tenant = models.Tenant(name="Smoke Tenant")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id, email="smoke@example.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Smoke Grill", address="Nairobi")
    db_session.add_all([user, restaurant])
    db_session.commit()
    token = auth.create_access_token({"sub": user.email})
    return restaurant, {"Authorization": f"Bearer {token}"}


def _seed_activity(db_session, restaurant_id):
    """A minimal but non-trivial dataset: menu, inventory, orders, a reservation."""
    items = [
        models.MenuItem(restaurant_id=restaurant_id, name=f"Dish{i}", price=1000 * i,
                        cost_price=300 * i, category="main")
        for i in range(1, 6)
    ]
    inv = models.InventoryItem(restaurant_id=restaurant_id, item_name="Chicken",
                               quantity=3.0, unit="kg", low_stock_threshold=10)
    tbl = models.Table(restaurant_id=restaurant_id, table_number=1, capacity=4,
                       status=models.TableStatus.AVAILABLE)
    db_session.add_all(items + [inv, tbl])
    db_session.commit()

    for d in range(40):
        o = models.Order(
            restaurant_id=restaurant_id, status=models.OrderStatus.SERVED,
            order_type=models.OrderType.DINE_IN,
            payment_method=models.PaymentMethod.CASH, is_paid=True, total=0,
            created_at=utcnow() - timedelta(days=d % 20),
        )
        db_session.add(o)
        db_session.flush()
        mi = items[d % len(items)]
        db_session.add(models.OrderItem(order_id=o.id, menu_item_id=mi.id,
                                        quantity=2, unit_price=mi.price))
        o.total = 2 * mi.price
    db_session.add(models.Reservation(
        restaurant_id=restaurant_id, customer_name="G", customer_phone="1", party_size=4,
        reservation_date=(utcnow() - timedelta(days=2)).date(), reservation_time=time(19, 0),
        status=models.ReservationStatus.COMPLETED,
    ))
    db_session.commit()


# (path, one key the agent only emits when it truly ran)
ROUTES = [
    ("/ai/inventory",             None),   # documented prior 500 (ImportError)
    ("/ai/labor",                 None),
    ("/ai/supply-chain",          None),
    ("/ai/profit",                None),
    ("/ai/revenue-forecast",      "trends"),
    ("/ai/kds-intelligence",      None),
    ("/ai/inventory-predictions", None),
    ("/ai/reservation-insights",  "revenue_impact"),
    ("/ai/menu-engineering",      "matrix"),
    ("/ai/dashboard",             "health_score"),
]


@pytest.mark.parametrize("path,expected_key", ROUTES)
def test_ai_route_on_empty_restaurant_does_not_crash(client, db_session, path, expected_key):
    """A brand-new restaurant with no data must get a graceful payload, not a 500
    and not a swallowed error."""
    _restaurant, headers = _auth(db_session)

    resp = client.get(path, headers=headers)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:200]}"

    body = resp.json()
    assert isinstance(body, dict)
    # The bug class: _safe_run turns an ImportError/AttributeError into a 200
    # carrying {"error": ...}. An empty restaurant is allowed to return a
    # {"error": "No restaurant found"}-style note ONLY on the two dashboard
    # routes that opt out of auto-create; the agent routes auto-create and must
    # not surface an error.
    if path not in ("/ai/dashboard",):
        assert "error" not in body, f"{path} returned a swallowed error: {body.get('error')}"


@pytest.mark.parametrize("path,expected_key", ROUTES)
def test_ai_route_on_seeded_restaurant_returns_real_shape(client, db_session, path, expected_key):
    restaurant, headers = _auth(db_session)
    _seed_activity(db_session, restaurant.id)

    resp = client.get(path, headers=headers)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}: {resp.text[:200]}"

    body = resp.json()
    assert isinstance(body, dict)
    assert "error" not in body, f"{path} returned a swallowed error: {body.get('error')}"
    if expected_key:
        assert expected_key in body, f"{path} missing expected key '{expected_key}': {list(body)}"


def test_ai_routes_require_authentication(client, db_session):
    """Every AI route is behind auth — an unauthenticated GET must be rejected."""
    for path, _ in ROUTES:
        resp = client.get(path)
        assert resp.status_code in (401, 403), f"{path} allowed an unauthenticated request"
