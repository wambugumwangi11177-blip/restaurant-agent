"""
Sprint 3 of the fraud-detection build: ai/fraud/detection.py.

Covers each pattern detector independently against synthetic OrderAudit/Order
data (mirrors tests/test_stock_custody_and_staff_roles.py's approach for
stock_custody), plus the cold-start guards that keep a brand-new restaurant
from getting false-positive flags on day one.
"""

from datetime import timedelta

import auth
import models
from time_utils import utcnow
from ai.fraud.detection import (
    compute_fraud_report,
    MIN_BASELINE_DAYS, VOID_SPIKE_MIN_COUNT,
    REFUND_VELOCITY_WINDOW_MINUTES, REFUND_VELOCITY_MIN_COUNT,
    OFF_HOURS_MIN_ORDERS,
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
    waiter = models.User(
        tenant_id=tenant.id, email=f"waiter{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, staff_role=models.StaffRole.WAITER, token_version=0,
    )
    db_session.add_all([owner, waiter])
    db_session.commit()
    return restaurant, owner, waiter


def _order(db_session, restaurant, total=1000, created_at=None):
    o = models.Order(restaurant_id=restaurant.id, total=total, created_at=created_at or utcnow())
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


def _audit(db_session, order, restaurant, actor, action, created_at):
    a = models.OrderAudit(
        order_id=order.id, restaurant_id=restaurant.id,
        action=action, actor_user_id=actor.id, created_at=created_at,
    )
    db_session.add(a)
    db_session.commit()
    return a


# ── Void spike (per-staff baseline) ─────────────────────────────────────────

def test_void_spike_flags_actor_who_blows_past_own_baseline(db_session):
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "vs1")
    now = utcnow()

    # 10 days of a quiet, consistent baseline: 1 cancel/day.
    for day in range(MIN_BASELINE_DAYS + 3):
        o = _order(db_session, restaurant, created_at=now - timedelta(days=day + 1))
        _audit(db_session, o, restaurant, waiter, models.OrderAuditAction.CANCEL,
               created_at=now - timedelta(days=day + 1))

    # Today: way more cancels than the 1/day baseline — well past floor + stddev.
    for _ in range(VOID_SPIKE_MIN_COUNT + 5):
        o = _order(db_session, restaurant, created_at=now - timedelta(hours=1))
        _audit(db_session, o, restaurant, waiter, models.OrderAuditAction.CANCEL,
               created_at=now - timedelta(hours=1))

    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert report.flagged
    assert len(report.void_spikes) == 1
    assert report.void_spikes[0].actor_user_id == waiter.id


def test_void_spike_cold_start_guard_no_baseline_history(db_session):
    """Fewer than MIN_BASELINE_DAYS of history — must not flag, even with a
    high count today (nothing to compare it against yet)."""
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "vs2")
    now = utcnow()

    for _ in range(VOID_SPIKE_MIN_COUNT + 10):
        o = _order(db_session, restaurant, created_at=now - timedelta(hours=1))
        _audit(db_session, o, restaurant, waiter, models.OrderAuditAction.CANCEL,
               created_at=now - timedelta(hours=1))

    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert report.void_spikes == []


def test_void_spike_below_floor_count_never_flags(db_session):
    """Even a statistically 'high' rate below VOID_SPIKE_MIN_COUNT shouldn't
    flag — the floor guards against noise on a quiet day."""
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "vs3")
    now = utcnow()

    for day in range(MIN_BASELINE_DAYS + 3):
        o = _order(db_session, restaurant, created_at=now - timedelta(days=day + 1))
        _audit(db_session, o, restaurant, waiter, models.OrderAuditAction.CANCEL,
               created_at=now - timedelta(days=day + 1))

    # Only 2 today — below VOID_SPIKE_MIN_COUNT regardless of baseline.
    for _ in range(2):
        o = _order(db_session, restaurant, created_at=now - timedelta(hours=1))
        _audit(db_session, o, restaurant, waiter, models.OrderAuditAction.CANCEL,
               created_at=now - timedelta(hours=1))

    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert report.void_spikes == []


# ── Refund velocity (burst detection) ───────────────────────────────────────

def test_refund_velocity_flags_a_fast_burst(db_session):
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "rv1")
    now = utcnow()

    for i in range(REFUND_VELOCITY_MIN_COUNT):
        o = _order(db_session, restaurant, created_at=now - timedelta(minutes=5 * i))
        _audit(db_session, o, restaurant, waiter, models.OrderAuditAction.REFUND,
               created_at=now - timedelta(minutes=5 * i))

    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert len(report.refund_velocity) == 1
    assert report.refund_velocity[0].actor_user_id == waiter.id
    assert report.refund_velocity[0].count >= REFUND_VELOCITY_MIN_COUNT


def test_refund_velocity_ignores_spread_out_refunds(db_session):
    """Same total count, but spread outside the velocity window — must not flag."""
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "rv2")
    now = utcnow()

    for i in range(REFUND_VELOCITY_MIN_COUNT):
        spacing = REFUND_VELOCITY_WINDOW_MINUTES * 3 * i
        o = _order(db_session, restaurant, created_at=now - timedelta(minutes=spacing))
        _audit(db_session, o, restaurant, waiter, models.OrderAuditAction.REFUND,
               created_at=now - timedelta(minutes=spacing))

    report = compute_fraud_report(db_session, restaurant.id, window_hours=48)
    assert report.refund_velocity == []


# ── Payment mismatches ───────────────────────────────────────────────────────

def test_payment_mismatch_flags_paid_mpesa_order_with_no_receipt(db_session):
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "pm1")
    o = models.Order(
        restaurant_id=restaurant.id, total=1500,
        payment_method=models.PaymentMethod.MPESA, is_paid=True,
        mpesa_receipt=None, created_at=utcnow(),
    )
    db_session.add(o)
    db_session.commit()

    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert len(report.payment_mismatches) == 1
    assert report.payment_mismatches[0].order_id == o.id


def test_payment_mismatch_does_not_flag_orders_with_a_real_receipt(db_session):
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "pm2")
    o = models.Order(
        restaurant_id=restaurant.id, total=1500,
        payment_method=models.PaymentMethod.MPESA, is_paid=True,
        mpesa_receipt="ABC123XYZ", created_at=utcnow(),
    )
    db_session.add(o)
    db_session.commit()

    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert report.payment_mismatches == []


def test_payment_mismatch_does_not_flag_cash_orders(db_session):
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "pm3")
    o = models.Order(
        restaurant_id=restaurant.id, total=1500,
        payment_method=models.PaymentMethod.CASH, is_paid=True,
        mpesa_receipt=None, created_at=utcnow(),
    )
    db_session.add(o)
    db_session.commit()

    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert report.payment_mismatches == []


# ── Off-hours activity ───────────────────────────────────────────────────────

def test_off_hours_cold_start_guard(db_session):
    """Fewer than OFF_HOURS_MIN_ORDERS of history — must not flag anything,
    since there's no reliable 'normal' window to compare against yet."""
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "oh1")
    now = utcnow()
    o = _order(db_session, restaurant, created_at=now)
    _audit(db_session, o, restaurant, waiter, models.OrderAuditAction.CANCEL, created_at=now)

    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert report.off_hours == []


def test_off_hours_flags_activity_outside_normal_trading_window(db_session):
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "oh2")
    now = utcnow()

    # Build a clean history: every order lands between hour 10 and hour 20.
    from datetime import datetime, timezone
    for day in range(OFF_HOURS_MIN_ORDERS + 5):
        ts = (now - timedelta(days=day + 1)).replace(hour=14, minute=0, second=0, microsecond=0)
        _order(db_session, restaurant, created_at=ts)

    # An order-audit action at 3am — well outside the 10-20 window.
    off_hours_ts = now.replace(hour=3, minute=0, second=0, microsecond=0)
    o = _order(db_session, restaurant, created_at=off_hours_ts)
    _audit(db_session, o, restaurant, waiter, models.OrderAuditAction.CANCEL, created_at=off_hours_ts)

    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert len(report.off_hours) == 1
    assert report.off_hours[0].order_id == o.id


# ── Combined report / on-demand endpoint ────────────────────────────────────

def test_clean_restaurant_has_no_flags(db_session):
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "clean1")
    o = _order(db_session, restaurant)
    report = compute_fraud_report(db_session, restaurant.id, window_hours=24)
    assert report.flagged is False


def test_fraud_report_endpoint_gated_to_oversight_roles(client, db_session):
    restaurant, owner, waiter = _make_restaurant_and_staff(db_session, "ep1")
    owner_token = auth.create_access_token({"sub": owner.email, "ver": 0})
    waiter_token = auth.create_access_token({"sub": waiter.email, "ver": 0})

    r_owner = client.get("/fraud/report", headers={"Authorization": f"Bearer {owner_token}"})
    assert r_owner.status_code == 200
    assert r_owner.json()["flagged"] is False

    r_waiter = client.get("/fraud/report", headers={"Authorization": f"Bearer {waiter_token}"})
    assert r_waiter.status_code == 403
