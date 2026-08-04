"""
backend/tests/test_notifications_inapp.py
───────────────────────────────────────────
In-app notifications exist because owner alerts used to be WhatsApp-only behind
an `if owner_phone:` gate: with no phone on file and no Twilio account — the
normal state of a fresh deployment — the system computed a critical stock
warning, wrote an audit log, and told nobody.

The load-bearing assertion in this file is therefore
`test_alert_reaches_the_dashboard_with_no_phone_and_no_twilio`: everything else
is detail, but if that regresses the product is silently back to shouting into
a void.
"""

import importlib

import pytest

import models
import notifications
from ai.whatsapp import twilio_client


@pytest.fixture
def no_twilio(monkeypatch):
    """A deployment with no messaging transport at all — the default state."""
    for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
                "TWILIO_WHATSAPP_FROM", "TWILIO_SMS_FROM", "OWNER_PHONE"):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(twilio_client)
    yield
    monkeypatch.undo()
    importlib.reload(twilio_client)


def _restaurant(db, **kw):
    r = models.Restaurant(name=kw.pop("name", "Test Kitchen"), **kw)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ── the core guarantee ───────────────────────────────────────────────────────

def test_alert_reaches_the_dashboard_with_no_phone_and_no_twilio(db_session, no_twilio):
    """The regression that matters: no owner phone, no Twilio, alert still lands."""
    restaurant = _restaurant(db_session, owner_phone=None)

    notifications.deliver(
        db_session, restaurant,
        title="Ugali flour critically low",
        body="~3h remaining.",
        category="stock_critical", severity=notifications.SEVERITY_CRITICAL,
        link="/dashboard/inventory",
    )

    feed = notifications.list_for(db_session, restaurant.id)
    assert len(feed) == 1
    assert feed[0].title == "Ugali flour critically low"
    assert feed[0].severity == "critical"
    assert feed[0].read_at is None
    assert notifications.unread_count(db_session, restaurant.id) == 1


def test_delivery_survives_a_transport_that_raises(db_session, monkeypatch):
    """
    A broken phone transport must not swallow the in-app alert. The record is
    committed before the forward is attempted precisely so this ordering holds.
    """
    restaurant = _restaurant(db_session, owner_phone="+254700000001")

    def boom(*a, **kw):
        raise RuntimeError("twilio exploded")

    monkeypatch.setattr("ai.whatsapp.brain.send_to_owner", boom)

    notifications.deliver(db_session, restaurant, title="Still delivered", body="x")

    assert len(notifications.list_for(db_session, restaurant.id)) == 1


def test_record_never_raises_into_the_caller(db_session, monkeypatch):
    """
    Callers are event handlers and scheduler jobs whose real work (recording a
    stockout, running a briefing) must not abort because *telling someone* failed.
    """
    restaurant = _restaurant(db_session)
    monkeypatch.setattr(db_session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("db down")))

    assert notifications.record(db_session, restaurant.id, "x") is None


def test_unknown_severity_falls_back_to_info(db_session):
    restaurant = _restaurant(db_session)
    note = notifications.record(db_session, restaurant.id, "t", severity="apocalyptic")
    assert note.severity == "info"


# ── read / unread ────────────────────────────────────────────────────────────

def test_mark_read_and_mark_all_read(db_session):
    restaurant = _restaurant(db_session)
    for i in range(3):
        notifications.record(db_session, restaurant.id, f"alert {i}")
    assert notifications.unread_count(db_session, restaurant.id) == 3

    first = notifications.list_for(db_session, restaurant.id)[0]
    assert notifications.mark_read(db_session, restaurant.id, first.id) is True
    assert notifications.unread_count(db_session, restaurant.id) == 2

    assert notifications.mark_all_read(db_session, restaurant.id) == 2
    assert notifications.unread_count(db_session, restaurant.id) == 0


def test_unread_only_filter(db_session):
    restaurant = _restaurant(db_session)
    a = notifications.record(db_session, restaurant.id, "read me")
    notifications.record(db_session, restaurant.id, "still unread")
    notifications.mark_read(db_session, restaurant.id, a.id)

    unread = notifications.list_for(db_session, restaurant.id, unread_only=True)
    assert [n.title for n in unread] == ["still unread"]


def test_feed_is_newest_first(db_session):
    from datetime import timedelta

    from time_utils import utcnow

    restaurant = _restaurant(db_session)
    old = notifications.record(db_session, restaurant.id, "older")
    old.created_at = utcnow() - timedelta(hours=5)
    db_session.commit()
    notifications.record(db_session, restaurant.id, "newer")

    assert [n.title for n in notifications.list_for(db_session, restaurant.id)] == ["newer", "older"]


# ── tenant isolation ─────────────────────────────────────────────────────────

def test_one_restaurant_never_sees_anothers_notifications(db_session):
    mine = _restaurant(db_session, name="Mine")
    theirs = _restaurant(db_session, name="Theirs")
    notifications.record(db_session, theirs.id, "their secret alert")

    assert notifications.list_for(db_session, mine.id) == []
    assert notifications.unread_count(db_session, mine.id) == 0


def test_marking_another_restaurants_notification_read_fails(db_session):
    mine = _restaurant(db_session, name="Mine")
    theirs = _restaurant(db_session, name="Theirs")
    foreign = notifications.record(db_session, theirs.id, "not yours")

    # False, not an exception, and identical to the response for an id that does
    # not exist — so the endpoint cannot be used to probe for existence.
    assert notifications.mark_read(db_session, mine.id, foreign.id) is False
    assert notifications.mark_read(db_session, mine.id, 999999) is False
    assert notifications.unread_count(db_session, theirs.id) == 1


def test_mark_all_read_does_not_touch_other_restaurants(db_session):
    mine = _restaurant(db_session, name="Mine")
    theirs = _restaurant(db_session, name="Theirs")
    notifications.record(db_session, mine.id, "mine")
    notifications.record(db_session, theirs.id, "theirs")

    notifications.mark_all_read(db_session, mine.id)

    assert notifications.unread_count(db_session, theirs.id) == 1


# ── wiring: the real alert paths ─────────────────────────────────────────────

def test_stock_depleted_event_lands_in_the_feed(db_session, no_twilio):
    """
    End-to-end through the orchestrator handler, which previously did nothing at
    all without an owner phone.
    """
    from ai.orchestrator.executive import on_stock_depleted

    restaurant = _restaurant(db_session, owner_phone=None)

    on_stock_depleted({"restaurant_id": restaurant.id, "item_name": "Sukuma wiki"})

    feed = notifications.list_for(db_session, restaurant.id)
    assert any("Sukuma wiki" in n.title for n in feed)
    assert feed[0].category == "stock_depleted"
    assert feed[0].severity == "critical"
    assert feed[0].link == "/dashboard/inventory"


def test_slow_day_check_lands_in_the_feed(db_session, no_twilio, monkeypatch):
    from ai.whatsapp import brain

    restaurant = _restaurant(db_session, owner_phone=None)
    monkeypatch.setattr(brain, "compose_slow_day_alert", lambda db, rid: "Revenue is 30% below average.")

    brain.run_slow_day_check(lambda: db_session)

    feed = notifications.list_for(db_session, restaurant.id)
    assert feed and feed[0].category == "slow_day_alert"
    assert feed[0].severity == "warning"


# ── HTTP surface ─────────────────────────────────────────────────────────────

def _auth_client(client):
    """Register a user (which also creates their restaurant) and return the
    Authorization header for it. Registration returns the token directly, so
    there is no need for a second login round-trip."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "owner@example.com",
        "password": "GoodPass1",
        "tenant_name": "Bell Test Kitchen",
    })
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_feed_endpoint_requires_auth(client):
    assert client.get("/api/v1/notifications/").status_code == 401


def test_feed_endpoint_returns_items_and_unread(client, db_session):
    headers = _auth_client(client)

    restaurant = db_session.query(models.Restaurant).first()
    notifications.record(db_session, restaurant.id, "Stock low", body="3h left",
                         category="stock_critical", severity="critical")

    body = client.get("/api/v1/notifications/", headers=headers).json()

    assert body["unread"] == 1
    assert body["items"][0]["title"] == "Stock low"
    assert body["items"][0]["severity"] == "critical"


def test_read_endpoints_clear_the_badge(client, db_session):
    headers = _auth_client(client)
    restaurant = db_session.query(models.Restaurant).first()
    first = notifications.record(db_session, restaurant.id, "one")
    notifications.record(db_session, restaurant.id, "two")

    resp = client.post(f"/api/v1/notifications/{first.id}/read", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["unread"] == 1

    resp = client.post("/api/v1/notifications/read-all", headers=headers)
    assert resp.json()["unread"] == 0


def test_reading_another_tenants_notification_is_404(client, db_session):
    headers = _auth_client(client)
    other = _restaurant(db_session, name="Someone Else")
    foreign = notifications.record(db_session, other.id, "not yours")

    resp = client.post(f"/api/v1/notifications/{foreign.id}/read", headers=headers)

    assert resp.status_code == 404
    assert notifications.unread_count(db_session, other.id) == 1


def test_limit_is_bounded(client, db_session):
    """`limit` is client-supplied; an unbounded value would pull the whole
    history into memory."""
    headers = _auth_client(client)
    restaurant = db_session.query(models.Restaurant).first()
    for i in range(5):
        notifications.record(db_session, restaurant.id, f"n{i}")

    body = client.get("/api/v1/notifications/?limit=100000", headers=headers).json()

    assert len(body["items"]) == 5  # bounded, not rejected
