"""
Sprint 4 of the fraud-detection/cash-reconciliation build:
ai/cash_reconciliation/intelligence.py + routers/cash_reconciliation.py.

Covers: expected-cash computation from real Order rows, tolerance math
(small gaps don't flag, real gaps do), the event fired only on a real flag,
reuse of the fraud module's M-Pesa mismatch check (not reimplemented), and
the endpoint's role gates.
"""

from datetime import timedelta

import auth
import models
from time_utils import utcnow
from ai.cash_reconciliation.intelligence import (
    record_drawer_count, compute_reconciliation_report, expected_cash_amount_cents,
    DrawerCountError, DRAWER_TOLERANCE_CENTS,
)


def _make_restaurant_and_staff(db_session, suffix):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    owner = models.User(
        tenant_id=tenant.id, email=f"owner{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER, token_version=0,
    )
    manager = models.User(
        tenant_id=tenant.id, email=f"mgr{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, staff_role=models.StaffRole.MANAGER, token_version=0,
    )
    waiter = models.User(
        tenant_id=tenant.id, email=f"waiter{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, staff_role=models.StaffRole.WAITER, token_version=0,
    )
    db_session.add_all([owner, manager, waiter])
    db_session.commit()
    return restaurant, owner, manager, waiter


def _cash_order(db_session, restaurant, total_cents, created_at):
    o = models.Order(
        restaurant_id=restaurant.id, total=total_cents,
        payment_method=models.PaymentMethod.CASH, is_paid=True, created_at=created_at,
    )
    db_session.add(o)
    db_session.commit()
    return o


# ── expected_cash_amount_cents ──────────────────────────────────────────────

def test_expected_cash_sums_only_paid_cash_orders_in_window(db_session):
    restaurant, owner, manager, waiter = _make_restaurant_and_staff(db_session, "cr1")
    now = utcnow()
    start, end = now - timedelta(hours=1), now + timedelta(hours=1)

    _cash_order(db_session, restaurant, 5000, now)   # in window, cash, paid
    _cash_order(db_session, restaurant, 3000, now)   # in window, cash, paid

    unpaid = models.Order(restaurant_id=restaurant.id, total=9999,
                          payment_method=models.PaymentMethod.CASH, is_paid=False, created_at=now)
    mpesa = models.Order(restaurant_id=restaurant.id, total=9999,
                         payment_method=models.PaymentMethod.MPESA, is_paid=True, created_at=now)
    outside_window = models.Order(restaurant_id=restaurant.id, total=9999,
                                  payment_method=models.PaymentMethod.CASH, is_paid=True,
                                  created_at=now - timedelta(days=5))
    db_session.add_all([unpaid, mpesa, outside_window])
    db_session.commit()

    expected = expected_cash_amount_cents(db_session, restaurant.id, start, end)
    assert expected == 8000


# ── record_drawer_count: tolerance math ─────────────────────────────────────

def test_small_gap_within_tolerance_is_not_flagged(db_session):
    restaurant, owner, manager, waiter = _make_restaurant_and_staff(db_session, "cr2")
    now = utcnow()
    start, end = now - timedelta(hours=1), now + timedelta(hours=1)
    _cash_order(db_session, restaurant, 100000, now)  # KES 1000 expected

    count = record_drawer_count(
        db_session, restaurant.id, manager.id,
        counted_amount_cents=100000 - (DRAWER_TOLERANCE_CENTS // 2),
        window_start=start, window_end=end,
    )
    assert count.expected_amount_cents == 100000

    report = compute_reconciliation_report(db_session, restaurant.id, window_hours=24)
    assert report.drawer_variances[0].flagged is False
    assert report.flagged is False


def test_real_gap_beyond_tolerance_is_flagged_and_emits_event(db_session, monkeypatch):
    restaurant, owner, manager, waiter = _make_restaurant_and_staff(db_session, "cr3")
    now = utcnow()
    start, end = now - timedelta(hours=1), now + timedelta(hours=1)
    _cash_order(db_session, restaurant, 100000, now)  # KES 1000 expected

    emitted = []
    monkeypatch.setattr("events.bus.emit_async", lambda event_type, payload: emitted.append((event_type, payload)))

    count = record_drawer_count(
        db_session, restaurant.id, manager.id,
        counted_amount_cents=100000 - (DRAWER_TOLERANCE_CENTS * 5),  # well beyond tolerance
        window_start=start, window_end=end,
    )

    assert len(emitted) == 1
    event_type, payload = emitted[0]
    assert event_type.value == "cash.reconciliation_flagged"
    assert payload["count_id"] == count.id
    assert payload["variance_cents"] < 0

    report = compute_reconciliation_report(db_session, restaurant.id, window_hours=24)
    assert report.flagged is True
    assert report.drawer_variances[0].flagged is True


def test_negative_counted_amount_rejected(db_session):
    restaurant, owner, manager, waiter = _make_restaurant_and_staff(db_session, "cr4")
    now = utcnow()
    try:
        record_drawer_count(
            db_session, restaurant.id, manager.id,
            counted_amount_cents=-100,
            window_start=now - timedelta(hours=1), window_end=now,
        )
        assert False, "expected DrawerCountError"
    except DrawerCountError:
        pass


def test_invalid_window_rejected(db_session):
    restaurant, owner, manager, waiter = _make_restaurant_and_staff(db_session, "cr5")
    now = utcnow()
    try:
        record_drawer_count(
            db_session, restaurant.id, manager.id,
            counted_amount_cents=1000,
            window_start=now, window_end=now - timedelta(hours=1),  # end before start
        )
        assert False, "expected DrawerCountError"
    except DrawerCountError:
        pass


# ── M-Pesa mismatch reuse ───────────────────────────────────────────────────

def test_report_includes_mpesa_mismatches_from_fraud_module(db_session):
    restaurant, owner, manager, waiter = _make_restaurant_and_staff(db_session, "cr6")
    now = utcnow()
    o = models.Order(
        restaurant_id=restaurant.id, total=2000,
        payment_method=models.PaymentMethod.MPESA, is_paid=True,
        mpesa_receipt=None, created_at=now,
    )
    db_session.add(o)
    db_session.commit()

    report = compute_reconciliation_report(db_session, restaurant.id, window_hours=24)
    assert len(report.mpesa_mismatches) == 1
    assert report.mpesa_mismatches[0].order_id == o.id
    assert report.flagged is True


# ── Endpoint role gates ──────────────────────────────────────────────────────

def test_submit_and_read_endpoints_gated_correctly(client, db_session):
    restaurant, owner, manager, waiter = _make_restaurant_and_staff(db_session, "cr7")
    now = utcnow()
    _cash_order(db_session, restaurant, 5000, now)

    manager_token = auth.create_access_token({"sub": manager.email, "ver": 0})
    waiter_token = auth.create_access_token({"sub": waiter.email, "ver": 0})

    r_submit = client.post(
        "/cash-reconciliation/counts",
        json={
            "counted_amount_cents": 5000,
            "window_start": (now - timedelta(hours=1)).isoformat(),
            "window_end": (now + timedelta(hours=1)).isoformat(),
        },
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert r_submit.status_code == 201, r_submit.text

    r_submit_denied = client.post(
        "/cash-reconciliation/counts",
        json={
            "counted_amount_cents": 5000,
            "window_start": now.isoformat(), "window_end": (now + timedelta(hours=1)).isoformat(),
        },
        headers={"Authorization": f"Bearer {waiter_token}"},
    )
    assert r_submit_denied.status_code == 403

    r_read = client.get("/cash-reconciliation/report", headers={"Authorization": f"Bearer {manager_token}"})
    assert r_read.status_code == 200
    assert r_read.json()["flagged"] is False

    r_read_denied = client.get("/cash-reconciliation/report", headers={"Authorization": f"Bearer {waiter_token}"})
    assert r_read_denied.status_code == 403
