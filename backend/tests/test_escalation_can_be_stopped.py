"""Something in the product must be able to stop the escalation ladder.

ai/escalation/engine.py sweeps every five minutes, pages managers at 15
minutes for a critical alert and phones the owner at 45, for any notification
with a severity and no acknowledged_at. The only code that sets
acknowledged_at is POST /notifications/{id}/acknowledge — which no frontend
file calls. /read sets is_read, which the sweep explicitly ignores.

So every critical event ran the whole ladder, every time, because the owner
had no button that stopped the clock. They do have a button: the one on the
Home card, which is the same finding seen from the other side.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import auth
import models
from time_utils import utcnow
from ai.escalation.engine import run_escalation_sweep


@pytest.fixture
def owner(db_session):
    db = db_session
    db.add(models.Tenant(id=1100, name="Escalation tenant"))
    db.flush()
    db.add(models.Restaurant(id=1101, tenant_id=1100, name="Escalation test"))
    db.flush()
    user = models.User(tenant_id=1100, active_restaurant_id=1101,
                       email="esc-owner@example.com", hashed_password="unused",
                       role=models.Role.ADMIN)
    db.add(user)
    db.commit()
    return user, {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email})}"}


def _alert(db, user_id, event_type, severity="critical", age_minutes=20):
    n = models.Notification(
        user_id=user_id, title="Suspicious transactions",
        body="Void spike detected", event_type=event_type,
        severity=severity, escalation_level=0,
        created_at=utcnow() - timedelta(minutes=age_minutes))
    db.add(n)
    db.commit()
    return n


def _cash_shortfall(db, rid, user_id):
    db.add(models.CashDrawerCount(
        restaurant_id=rid, expected_amount_cents=1_000_000,
        counted_amount_cents=600_000, counted_by_user_id=user_id,
        window_start=utcnow() - timedelta(hours=9),
        window_end=utcnow() - timedelta(hours=1),
        counted_at=utcnow() - timedelta(hours=1)))
    db.commit()


# ── The gap ──────────────────────────────────────────────────────────────────

def test_marking_read_does_not_stop_the_clock(client, db_session, owner):
    """The distinction the escalation engine is built on: seen is not handled."""
    user, headers = owner
    alert = _alert(db_session, user.id, "cash.reconciliation_flagged", "high", 40)

    res = client.post(f"/api/v1/notifications/{alert.id}/read", headers=headers)
    assert res.status_code == 200

    db_session.expire_all()
    assert db_session.query(models.Notification).filter_by(id=alert.id).one().acknowledged_at is None
    assert run_escalation_sweep(db_session)["escalated_to_managers"] == 1


# ── The fix ──────────────────────────────────────────────────────────────────

def test_deciding_the_card_acknowledges_its_alerts(client, db_session, owner):
    user, headers = owner
    _cash_shortfall(db_session, 1101, user.id)
    alert = _alert(db_session, user.id, "cash.reconciliation_flagged", "high", 40)

    feed = client.get("/api/v1/overview/today", headers=headers).json()
    card = next(c for c in feed["attention"] if c.get("agent") == "cash_reconciliation")
    body = client.post(f"/api/v1/overview/attention/{card['id']}/decision",
                       json={"decision": "approved"}, headers=headers).json()
    assert body["alerts_acknowledged"] == 1

    db_session.expire_all()
    assert db_session.query(models.Notification).filter_by(id=alert.id).one().acknowledged_at is not None
    assert run_escalation_sweep(db_session)["escalated_to_managers"] == 0


def test_later_also_stops_the_clock(client, db_session, owner):
    """"Later" still means the owner has seen it, which is what the ladder
    is checking for. Paging a manager about something already on the owner's
    screen is the alert fatigue this is meant to prevent."""
    user, headers = owner
    _cash_shortfall(db_session, 1101, user.id)
    alert = _alert(db_session, user.id, "cash.reconciliation_flagged", "high", 40)

    feed = client.get("/api/v1/overview/today", headers=headers).json()
    card = next(c for c in feed["attention"] if c.get("agent") == "cash_reconciliation")
    client.post(f"/api/v1/overview/attention/{card['id']}/decision",
                json={"decision": "later"}, headers=headers)

    db_session.expire_all()
    assert db_session.query(models.Notification).filter_by(id=alert.id).one().acknowledged_at is not None


def test_acknowledging_one_finding_does_not_silence_another(client, db_session, owner):
    """A theft flag and a stock alert are different problems. Deciding one must
    not quietly stop the ladder for the other."""
    user, headers = owner
    _cash_shortfall(db_session, 1101, user.id)
    cash_alert = _alert(db_session, user.id, "cash.reconciliation_flagged", "high", 40)
    stock_alert = _alert(db_session, user.id, "stock.critical", "critical", 20)

    feed = client.get("/api/v1/overview/today", headers=headers).json()
    card = next(c for c in feed["attention"] if c.get("agent") == "cash_reconciliation")
    client.post(f"/api/v1/overview/attention/{card['id']}/decision",
                json={"decision": "approved"}, headers=headers)

    db_session.expire_all()
    assert db_session.query(models.Notification).filter_by(id=cash_alert.id).one().acknowledged_at is not None
    assert db_session.query(models.Notification).filter_by(id=stock_alert.id).one().acknowledged_at is None


def test_one_tenant_cannot_acknowledge_anothers_alerts(client, db_session, owner):
    user, headers = owner
    db_session.add(models.Tenant(id=1200, name="Other tenant"))
    db_session.flush()
    db_session.add(models.Restaurant(id=1201, tenant_id=1200, name="Other"))
    other = models.User(tenant_id=1200, active_restaurant_id=1201,
                        email="other@example.com", hashed_password="unused",
                        role=models.Role.ADMIN)
    db_session.add(other)
    db_session.commit()
    foreign = _alert(db_session, other.id, "cash.reconciliation_flagged", "high", 40)

    _cash_shortfall(db_session, 1101, user.id)
    _alert(db_session, user.id, "cash.reconciliation_flagged", "high", 40)
    feed = client.get("/api/v1/overview/today", headers=headers).json()
    card = next(c for c in feed["attention"] if c.get("agent") == "cash_reconciliation")
    client.post(f"/api/v1/overview/attention/{card['id']}/decision",
                json={"decision": "approved"}, headers=headers)

    db_session.expire_all()
    assert db_session.query(models.Notification).filter_by(id=foreign.id).one().acknowledged_at is None


def test_an_unescalated_notification_is_left_alone(client, db_session, owner):
    """Only severity-tagged alerts drive the ladder; ordinary notifications
    keep their own unread state."""
    user, headers = owner
    _cash_shortfall(db_session, 1101, user.id)
    ordinary = models.Notification(
        user_id=user.id, title="Order ready", body="Table 4",
        event_type="cash.reconciliation_flagged", severity=None,
        created_at=utcnow() - timedelta(minutes=40))
    db_session.add(ordinary)
    db_session.commit()

    feed = client.get("/api/v1/overview/today", headers=headers).json()
    card = next(c for c in feed["attention"] if c.get("agent") == "cash_reconciliation")
    client.post(f"/api/v1/overview/attention/{card['id']}/decision",
                json={"decision": "approved"}, headers=headers)

    db_session.expire_all()
    row = db_session.query(models.Notification).filter_by(id=ordinary.id).one()
    assert row.acknowledged_at is None
    assert row.is_read is False
