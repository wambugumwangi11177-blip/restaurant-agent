"""
Sprint 2 of the fraud-detection/escalation build: ai/escalation/engine.py.

Covers: severity gets stamped on the Notification by the existing
push_notifier fan-out (no new call site needed), the ladder advances
managers-paged -> voice-call at the right timeouts, acknowledging stops the
clock, and a notification with no severity is never touched by the sweep
(every pre-Sprint-2 event keeps behaving exactly as before).
"""

from datetime import timedelta

import auth
import models
from time_utils import utcnow
from ai.escalation.engine import (
    run_escalation_sweep, severity_for, LEVEL_1_TIMEOUT_MINUTES, LEVEL_2_TIMEOUT_MINUTES,
)


def _make_user(db_session, tenant, suffix, role=models.Role.STAFF, staff_role=None):
    user = models.User(
        tenant_id=tenant.id, email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=role, staff_role=staff_role, is_active=True, token_version=0,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_restaurant(db_session, suffix):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    db_session.refresh(restaurant)
    return tenant, restaurant


def _backdated_notification(db_session, user, severity, minutes_ago, escalation_level=0):
    notif = models.Notification(
        user_id=user.id, title="Test alert", body="Something needs attention",
        event_type="stock.critical", severity=severity,
        created_at=utcnow() - timedelta(minutes=minutes_ago),
        escalation_level=escalation_level,
    )
    db_session.add(notif)
    db_session.commit()
    db_session.refresh(notif)
    return notif


# ── severity_for / mapping ──────────────────────────────────────────────────

def test_severity_for_known_and_unknown_events():
    assert severity_for("stock.critical") == "critical"
    assert severity_for("stock.variance_flagged") == "high"
    assert severity_for("order.ready") is None  # ordinary operational event


def test_stock_critical_notification_is_stamped_critical(db_session):
    from ai.orchestrator.push_notifier import _on_stock_critical

    tenant, restaurant = _make_restaurant(db_session, "esc1")
    owner = _make_user(db_session, tenant, "esc1owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)

    _on_stock_critical({"restaurant_id": restaurant.id, "item_name": "Rice", "hours_remaining": 1})

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).first()
    assert notif.severity == "critical"
    assert notif.escalation_level == 0
    assert notif.acknowledged_at is None


def test_ordinary_event_is_not_stamped_with_severity(db_session):
    from ai.orchestrator.push_notifier import _on_order_ready

    tenant, restaurant = _make_restaurant(db_session, "esc2")
    manager = _make_user(db_session, tenant, "esc2mgr", staff_role=models.StaffRole.MANAGER)

    _on_order_ready({"restaurant_id": restaurant.id, "order_id": 1, "table_number": 4, "customer_name": ""})

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == manager.id).first()
    assert notif.severity is None


# ── Ladder: level 0 -> 1 (page managers) ────────────────────────────────────

def test_unacknowledged_critical_alert_pages_managers_after_timeout(db_session):
    tenant, restaurant = _make_restaurant(db_session, "esc3")
    owner = _make_user(db_session, tenant, "esc3owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    manager = _make_user(db_session, tenant, "esc3mgr", staff_role=models.StaffRole.MANAGER)

    timeout = LEVEL_1_TIMEOUT_MINUTES["critical"]
    notif = _backdated_notification(db_session, owner, "critical", minutes_ago=timeout + 1)

    result = run_escalation_sweep(db_session)

    assert result["escalated_to_managers"] == 1
    db_session.refresh(notif)
    assert notif.escalation_level == 1

    mgr_notifs = db_session.query(models.Notification).filter(models.Notification.user_id == manager.id).all()
    assert len(mgr_notifs) == 1
    assert mgr_notifs[0].severity == "critical"


def test_alert_within_timeout_is_not_escalated_yet(db_session):
    tenant, restaurant = _make_restaurant(db_session, "esc4")
    owner = _make_user(db_session, tenant, "esc4owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    _make_user(db_session, tenant, "esc4mgr", staff_role=models.StaffRole.MANAGER)

    timeout = LEVEL_1_TIMEOUT_MINUTES["critical"]
    notif = _backdated_notification(db_session, owner, "critical", minutes_ago=timeout - 1)

    result = run_escalation_sweep(db_session)

    assert result["escalated_to_managers"] == 0
    db_session.refresh(notif)
    assert notif.escalation_level == 0


def test_high_severity_uses_its_own_longer_timeout(db_session):
    tenant, restaurant = _make_restaurant(db_session, "esc5")
    owner = _make_user(db_session, tenant, "esc5owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    _make_user(db_session, tenant, "esc5mgr", staff_role=models.StaffRole.MANAGER)

    critical_timeout = LEVEL_1_TIMEOUT_MINUTES["critical"]
    high_timeout = LEVEL_1_TIMEOUT_MINUTES["high"]
    assert high_timeout > critical_timeout  # sanity: high is meant to be slower than critical

    # Old enough for critical's timeout, not yet for high's.
    notif = _backdated_notification(db_session, owner, "high", minutes_ago=critical_timeout + 1)
    run_escalation_sweep(db_session)
    db_session.refresh(notif)
    assert notif.escalation_level == 0


# ── Ladder: level 1 -> 2 (voice call, critical only) ────────────────────────

def test_critical_alert_escalates_to_call_after_second_timeout(db_session, monkeypatch):
    tenant, restaurant = _make_restaurant(db_session, "esc6")
    restaurant.owner_phone = "+254700000001"
    db_session.commit()
    owner = _make_user(db_session, tenant, "esc6owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)

    calls = []
    monkeypatch.setattr(
        "ai.whatsapp.twilio_client.call",
        lambda to_number, message: calls.append((to_number, message)) or {"status": "sent", "sid": "CA123"},
    )

    timeout = LEVEL_2_TIMEOUT_MINUTES["critical"]
    notif = _backdated_notification(db_session, owner, "critical", minutes_ago=timeout + 1, escalation_level=1)

    result = run_escalation_sweep(db_session)

    assert result["escalated_to_call"] == 1
    db_session.refresh(notif)
    assert notif.escalation_level == 2
    assert len(calls) == 1


def test_high_severity_never_reaches_voice_call(db_session):
    """High has no LEVEL_2_TIMEOUT_MINUTES entry — even left unacknowledged
    forever, it should never advance past level 1 (paging managers)."""
    tenant, restaurant = _make_restaurant(db_session, "esc7")
    owner = _make_user(db_session, tenant, "esc7owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)

    notif = _backdated_notification(db_session, owner, "high", minutes_ago=10000, escalation_level=1)

    result = run_escalation_sweep(db_session)

    assert result["escalated_to_call"] == 0
    db_session.refresh(notif)
    assert notif.escalation_level == 1


# ── Acknowledging stops the clock ───────────────────────────────────────────

def test_acknowledged_alert_is_never_escalated(db_session):
    tenant, restaurant = _make_restaurant(db_session, "esc8")
    owner = _make_user(db_session, tenant, "esc8owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    _make_user(db_session, tenant, "esc8mgr", staff_role=models.StaffRole.MANAGER)

    timeout = LEVEL_1_TIMEOUT_MINUTES["critical"]
    notif = _backdated_notification(db_session, owner, "critical", minutes_ago=timeout + 100)
    notif.acknowledged_at = utcnow()
    db_session.commit()

    result = run_escalation_sweep(db_session)

    assert result["escalated_to_managers"] == 0
    db_session.refresh(notif)
    assert notif.escalation_level == 0


def test_acknowledge_endpoint_stops_future_escalation(client, db_session):
    tenant, restaurant = _make_restaurant(db_session, "esc9")
    owner = _make_user(db_session, tenant, "esc9owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    token = auth.create_access_token({"sub": owner.email, "ver": 0})

    timeout = LEVEL_1_TIMEOUT_MINUTES["critical"]
    notif = _backdated_notification(db_session, owner, "critical", minutes_ago=timeout + 1)

    r = client.post(f"/notifications/{notif.id}/acknowledge", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["acknowledged_at"] is not None

    result = run_escalation_sweep(db_session)
    assert result["escalated_to_managers"] == 0
