"""
backend/tests/test_phase2_integrity.py
─────────────────────────────────────────
Database-level integrity constraints (Phase 2). These are enforced by the schema
itself (create_all applies them from models.py; migration 016 applies them to
existing Postgres DBs), so a bug or a raw SQL edit can't persist impossible data.

SQLite enforces CHECK constraints and UNIQUE constraints natively, so these run
under the normal test DB.

The HTTP-level tests below (test_*_returns_422_*) cover the layer above the DB
constraint: Pydantic Field(gt=0) validation added to schemas.py so a bad
quantity/party_size/duration never reaches the DB as a raw IntegrityError (a
500), but comes back as a clean 422 instead.
"""

from datetime import date, time

import pytest
from sqlalchemy.exc import IntegrityError

import auth
import models


def _restaurant(db_session):
    t = models.Tenant(name="T")
    db_session.add(t)
    db_session.commit()
    r = models.Restaurant(tenant_id=t.id, name="R", address="x")
    db_session.add(r)
    db_session.commit()
    return r


def test_order_total_cannot_be_negative(db_session):
    r = _restaurant(db_session)
    db_session.add(models.Order(
        restaurant_id=r.id, total=-1,
        status=models.OrderStatus.PENDING, payment_method=models.PaymentMethod.CASH,
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_order_total_zero_is_allowed(db_session):
    """A comped / zero-total order is legitimate — the check is >= 0, not > 0."""
    r = _restaurant(db_session)
    db_session.add(models.Order(
        restaurant_id=r.id, total=0,
        status=models.OrderStatus.PENDING, payment_method=models.PaymentMethod.CASH,
    ))
    db_session.commit()  # must not raise


def test_menu_item_price_cannot_be_negative(db_session):
    r = _restaurant(db_session)
    db_session.add(models.MenuItem(restaurant_id=r.id, name="X", price=-5, category="m"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_reservation_party_size_must_be_positive(db_session):
    r = _restaurant(db_session)
    db_session.add(models.Reservation(
        restaurant_id=r.id, customer_name="x", party_size=0,
        reservation_date=date(2026, 7, 10), reservation_time=time(19, 0),
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_table_number_rejected_within_restaurant(db_session):
    r = _restaurant(db_session)
    db_session.add(models.Table(restaurant_id=r.id, table_number=7))
    db_session.commit()
    db_session.add(models.Table(restaurant_id=r.id, table_number=7))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_same_table_number_allowed_across_restaurants(db_session):
    r1 = _restaurant(db_session)
    r2 = _restaurant(db_session)
    db_session.add(models.Table(restaurant_id=r1.id, table_number=1))
    db_session.add(models.Table(restaurant_id=r2.id, table_number=1))
    db_session.commit()  # unique is (restaurant_id, table_number), not table_number alone


def _user_headers(db_session, r: models.Restaurant, suffix: str = "u") -> dict:
    user = models.User(
        tenant_id=r.tenant_id, email=f"{suffix}@example.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
    )
    db_session.add(user)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def test_order_quantity_zero_returns_422_not_500(client, db_session):
    r = _restaurant(db_session)
    headers = _user_headers(db_session, r)
    menu_item = models.MenuItem(restaurant_id=r.id, name="Burger", price=500, category="mains")
    db_session.add(menu_item)
    db_session.commit()

    resp = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 0}]},
        headers=headers,
    )
    assert resp.status_code == 422


def test_reservation_party_size_negative_returns_422_not_500(client, db_session):
    r = _restaurant(db_session)
    headers = _user_headers(db_session, r)

    resp = client.post(
        "/reservations/",
        json={
            "customer_name": "Jane",
            "party_size": -1,
            "reservation_date": "2026-08-01",
            "reservation_time": "19:00:00",
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_reservation_duration_zero_returns_422_not_500(client, db_session):
    r = _restaurant(db_session)
    headers = _user_headers(db_session, r)

    resp = client.post(
        "/reservations/",
        json={
            "customer_name": "Jane",
            "party_size": 2,
            "reservation_date": "2026-08-01",
            "reservation_time": "19:00:00",
            "duration_minutes": 0,
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_stock_receive_quantity_zero_returns_422_not_500(client, db_session):
    r = _restaurant(db_session)
    headers = _user_headers(db_session, r)
    item = models.InventoryItem(
        restaurant_id=r.id, item_name="Rice", quantity=10, unit="kg",
        cost_per_unit=100, low_stock_threshold=2, expiry_days=30,
    )
    db_session.add(item)
    db_session.commit()

    resp = client.post(f"/inventory/{item.id}/receive", json={"quantity": 0}, headers=headers)
    assert resp.status_code == 422


def test_stock_adjust_negative_quantity_is_still_allowed(client, db_session):
    """StockAdjust.quantity is intentionally signed (positive = add, negative =
    remove per its own docstring) — Field(gt=0) must NOT be applied here."""
    r = _restaurant(db_session)
    headers = _user_headers(db_session, r)
    item = models.InventoryItem(
        restaurant_id=r.id, item_name="Rice", quantity=10, unit="kg",
        cost_per_unit=100, low_stock_threshold=2, expiry_days=30,
    )
    db_session.add(item)
    db_session.commit()

    resp = client.post(f"/inventory/{item.id}/adjust", json={"quantity": -3, "reason": "waste"}, headers=headers)
    assert resp.status_code == 200
