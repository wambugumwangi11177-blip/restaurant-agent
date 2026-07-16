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


def test_duplicate_mpesa_receipt_rejected_across_orders(db_session):
    r = _restaurant(db_session)
    db_session.add(models.Order(
        restaurant_id=r.id, total=100, mpesa_receipt="NLJ7RT61SV",
        status=models.OrderStatus.PENDING, payment_method=models.PaymentMethod.MPESA,
    ))
    db_session.commit()
    db_session.add(models.Order(
        restaurant_id=r.id, total=200, mpesa_receipt="NLJ7RT61SV",
        status=models.OrderStatus.PENDING, payment_method=models.PaymentMethod.MPESA,
    ))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_multiple_unpaid_orders_with_null_mpesa_receipt_allowed(db_session):
    r = _restaurant(db_session)
    db_session.add(models.Order(
        restaurant_id=r.id, total=100,
        status=models.OrderStatus.PENDING, payment_method=models.PaymentMethod.PENDING,
    ))
    db_session.add(models.Order(
        restaurant_id=r.id, total=200,
        status=models.OrderStatus.PENDING, payment_method=models.PaymentMethod.PENDING,
    ))
    db_session.commit()  # mpesa_receipt is NULL on both — the partial index must not fire


def test_duplicate_staff_phone_rejected_within_restaurant(db_session):
    r = _restaurant(db_session)
    db_session.add(models.StaffMember(restaurant_id=r.id, name="A", phone="+254700000001"))
    db_session.commit()
    db_session.add(models.StaffMember(restaurant_id=r.id, name="B", phone="+254700000001"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_staff_members_without_phone_allowed(db_session):
    r = _restaurant(db_session)
    db_session.add(models.StaffMember(restaurant_id=r.id, name="A"))
    db_session.add(models.StaffMember(restaurant_id=r.id, name="B"))
    db_session.commit()  # phone is NULL on both — the partial index must not fire
