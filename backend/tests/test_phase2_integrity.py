"""
backend/tests/test_phase2_integrity.py
─────────────────────────────────────────
Database-level integrity constraints (Phase 2). These are enforced by the schema
itself (create_all applies them from models.py; migration 016 applies them to
existing Postgres DBs), so a bug or a raw SQL edit can't persist impossible data.

SQLite enforces CHECK constraints and UNIQUE constraints natively, so these run
under the normal test DB.
"""

from datetime import date, time

import pytest
from sqlalchemy.exc import IntegrityError

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


# ─────────────────────────────────────────────────────────────────────────────
# HTTP-level validation (Field(gt=0) on schemas.py) — catches bad input as a
# clean 422 at the API boundary, before it ever reaches the DB-level CHECK
# constraints exercised above. Same invariants, different layer.
# ─────────────────────────────────────────────────────────────────────────────

def test_order_item_zero_quantity_is_rejected_as_422(client, db_session):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    item = models.MenuItem(id=1, restaurant_id=1, name="Burger", price=50000, is_available=True)
    db_session.add_all([r, item])
    db_session.commit()

    resp = client.post("/orders/public?restaurant_id=1", json={
        "items": [{"menu_item_id": 1, "quantity": 0}],
        "payment_method": "cash",
    })
    assert resp.status_code == 422


def test_order_item_negative_quantity_is_rejected_as_422(client, db_session):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    item = models.MenuItem(id=1, restaurant_id=1, name="Burger", price=50000, is_available=True)
    db_session.add_all([r, item])
    db_session.commit()

    resp = client.post("/orders/public?restaurant_id=1", json={
        "items": [{"menu_item_id": 1, "quantity": -1}],
        "payment_method": "cash",
    })
    assert resp.status_code == 422


def test_reservation_zero_party_size_is_rejected_as_422(client, db_session):
    import auth
    tenant = models.Tenant(name="T2")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id, email="owner_422@example.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R2", address="x")
    db_session.add_all([user, restaurant])
    db_session.commit()
    token = auth.create_access_token({"sub": user.email})

    resp = client.post("/reservations/", json={
        "customer_name": "Test Customer",
        "party_size": 0,
        "reservation_date": str(date(2026, 8, 1)),
        "reservation_time": "19:00:00",
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422
