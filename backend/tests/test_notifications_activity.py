"""
backend/tests/test_notifications_activity.py
──────────────────────────────────────────────
The feed is meant to be a complete picture of what the software did — not only
of what went wrong. These tests walk the real HTTP endpoints (place an order,
move it through the kitchen, take payment, book a table, receive stock, change
the menu) and assert each one leaves a trace, addressed to the right audience.

Two properties are load-bearing:

  • **Routine events reach the floor, financial ones do not.** An order landing
    is useless to the owner alone and essential to the kitchen; a menu price
    change is the opposite. Getting this wrong in the permissive direction is
    the RBAC leak this suite exists to prevent recurring.
  • **A notification failure never fails the operation.** The order is the
    product; the bell entry describing it is not.
"""

import pytest

import models
import notifications


@pytest.fixture
def admin(client):
    """An ADMIN user (registration creates one) plus their restaurant."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "owner@example.com", "password": "GoodPass1", "tenant_name": "Activity Kitchen",
    })
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _restaurant(db):
    return db.query(models.Restaurant).first()


def _feed(db, category=None):
    rows = notifications.list_for(db, _restaurant(db).id, limit=200)
    return [n for n in rows if category is None or n.category == category]


def _menu_item(client, headers, name="Ugali", price=30000):
    resp = client.post("/api/v1/menu/", headers=headers, json={
        "name": name, "price": price, "category": "Main",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _place_order(client, headers, item_id, qty=2):
    resp = client.post("/api/v1/orders/", headers=headers, json={
        "items": [{"menu_item_id": item_id, "quantity": qty}],
        "order_type": "dine_in", "customer_name": "Walk-in",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ── orders ───────────────────────────────────────────────────────────────────

def test_placing_an_order_is_recorded_for_everyone(client, db_session, admin):
    item_id = _menu_item(client, admin)

    _place_order(client, admin, item_id)

    created = _feed(db_session, "order_created")
    assert len(created) == 1
    # The kitchen is the whole point of this one.
    assert created[0].audience == notifications.AUDIENCE_ALL
    assert created[0].severity == "info"
    assert created[0].link == "/dashboard/orders"


def test_order_status_change_is_recorded_once_per_transition(client, db_session, admin):
    item_id = _menu_item(client, admin)
    order_id = _place_order(client, admin, item_id)

    client.patch(f"/api/v1/orders/{order_id}/status", headers=admin, json={"status": "prep"})
    client.patch(f"/api/v1/orders/{order_id}/status", headers=admin, json={"status": "prep"})
    client.patch(f"/api/v1/orders/{order_id}/status", headers=admin, json={"status": "ready"})

    # Three PATCHes, two real transitions. Re-asserting the current status
    # changed nothing and must not announce that it did.
    assert len(_feed(db_session, "order_status")) == 2


def test_cancelling_an_order_is_a_warning_not_an_info(client, db_session, admin):
    item_id = _menu_item(client, admin)
    order_id = _place_order(client, admin, item_id)

    client.patch(f"/api/v1/orders/{order_id}/status", headers=admin, json={"status": "cancelled"})

    cancelled = _feed(db_session, "order_cancelled")
    assert len(cancelled) == 1
    assert cancelled[0].severity == "warning"


def test_payment_is_recorded_once_on_the_unpaid_to_paid_transition(client, db_session, admin):
    item_id = _menu_item(client, admin)
    order_id = _place_order(client, admin, item_id)

    client.patch(f"/api/v1/orders/{order_id}/payment", headers=admin,
                 json={"payment_method": "cash", "is_paid": True})
    client.patch(f"/api/v1/orders/{order_id}/payment", headers=admin,
                 json={"payment_method": "cash", "is_paid": True})

    paid = _feed(db_session, "order_paid")
    assert len(paid) == 1
    assert "cash" in paid[0].body


# ── reservations ─────────────────────────────────────────────────────────────

def test_booking_and_its_status_changes_are_recorded(client, db_session, admin):
    resp = client.post("/api/v1/reservations/", headers=admin, json={
        "customer_name": "Achieng", "party_size": 4,
        "reservation_date": "2026-09-01", "reservation_time": "19:00:00",
    })
    assert resp.status_code == 200, resp.text
    reservation_id = resp.json()["id"]

    created = _feed(db_session, "reservation_created")
    assert len(created) == 1
    assert "Achieng" in created[0].title
    assert created[0].audience == notifications.AUDIENCE_ALL

    client.patch(f"/api/v1/reservations/{reservation_id}/status", headers=admin,
                 json={"status": "cancelled"})

    status_events = _feed(db_session, "reservation_status")
    assert len(status_events) == 1
    assert status_events[0].severity == "warning"


def test_deleting_a_booking_is_recorded_after_the_row_is_gone(client, db_session, admin):
    """Guards a real trap: reading attributes off a deleted instance post-commit
    raises, so the name has to be captured first."""
    resp = client.post("/api/v1/reservations/", headers=admin, json={
        "customer_name": "Wanjiru", "party_size": 2,
        "reservation_date": "2026-09-02", "reservation_time": "18:30:00",
    })
    reservation_id = resp.json()["id"]

    resp = client.delete(f"/api/v1/reservations/{reservation_id}", headers=admin)

    assert resp.status_code == 200
    assert any("Wanjiru" in n.title for n in _feed(db_session, "reservation_status"))


# ── inventory ────────────────────────────────────────────────────────────────

def _inventory_item(client, headers):
    resp = client.post("/api/v1/inventory/", headers=headers, json={
        "item_name": "Rice", "quantity": 10, "unit": "kg",
        "cost_per_unit": 15000, "low_stock_threshold": 2,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_receiving_stock_is_recorded_for_everyone(client, db_session, admin):
    item_id = _inventory_item(client, admin)

    client.post(f"/api/v1/inventory/{item_id}/receive", headers=admin,
                json={"quantity": 25, "supplier": "Mama Mboga"})

    received = _feed(db_session, "stock_received")
    assert len(received) == 1
    assert received[0].audience == notifications.AUDIENCE_ALL
    assert "Rice" in received[0].title


def test_stock_adjustment_is_a_warning_and_names_the_reason(client, db_session, admin):
    """Waste and breakage are a cost line — the one routine action an owner
    actually wants to notice."""
    item_id = _inventory_item(client, admin)

    client.post(f"/api/v1/inventory/{item_id}/adjust", headers=admin,
                json={"quantity": -3, "reason": "spoilage"})

    adjusted = _feed(db_session, "stock_adjusted")
    assert len(adjusted) == 1
    assert adjusted[0].severity == "warning"
    assert "spoilage" in adjusted[0].body


# ── menu (financial — admin only) ────────────────────────────────────────────

def test_menu_changes_are_admin_only(client, db_session, admin):
    item_id = _menu_item(client, admin, name="Pilau", price=45000)

    client.put(f"/api/v1/menu/{item_id}", headers=admin, json={"price": 52000})
    client.put(f"/api/v1/menu/{item_id}", headers=admin, json={"is_available": False})

    events = _feed(db_session, "menu_changed")
    assert len(events) == 3          # added, price changed, marked unavailable
    assert all(e.audience == notifications.AUDIENCE_ADMIN for e in events), \
        "menu edits are pricing decisions; price is ADMIN-gated everywhere else"
    assert any("price changed" in e.title for e in events)
    assert any("unavailable" in e.title for e in events)


# ── the staff view of all of the above ───────────────────────────────────────

def test_staff_see_the_floor_events_but_no_pricing(client, db_session, admin):
    """The whole point of the audience column, exercised over the real feed."""
    item_id = _menu_item(client, admin)          # admin-only
    _place_order(client, admin, item_id)         # everyone

    restaurant = _restaurant(db_session)
    staff_feed = notifications.list_for(db_session, restaurant.id, role=models.Role.STAFF)
    admin_feed = notifications.list_for(db_session, restaurant.id, role=models.Role.ADMIN)

    assert [n.category for n in staff_feed] == ["order_created"]
    assert {n.category for n in admin_feed} == {"order_created", "menu_changed"}


# ── failure isolation ────────────────────────────────────────────────────────

def test_a_broken_notification_never_fails_the_order(client, db_session, admin, monkeypatch):
    """
    The order is the product; the bell entry describing it is not.

    Fails the *inside* of the helper rather than replacing the helper itself:
    the realistic fault is a bug in the notification path (a None attribute, an
    unexpected enum, a dead connection), and that is what `@_never_fails` has to
    contain. This exact scenario returned 500 to the POS before that decorator
    existed — a lost sale caused by a cosmetic feature.
    """
    item_id = _menu_item(client, admin)

    def boom(*a, **kw):
        raise RuntimeError("notification subsystem down")

    monkeypatch.setattr(notifications, "record", boom)

    resp = client.post("/api/v1/orders/", headers=admin, json={
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "order_type": "dine_in", "customer_name": "Walk-in",
    })

    assert resp.status_code == 200, "a notification failure must not cost a sale"
    assert db_session.query(models.Order).count() == 1


def test_a_broken_notification_never_fails_a_booking(client, db_session, admin, monkeypatch):
    """Same guarantee on the reservation path, which deletes a row before it
    records — the sequencing most likely to go wrong."""
    monkeypatch.setattr(notifications, "record", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("x")))

    resp = client.post("/api/v1/reservations/", headers=admin, json={
        "customer_name": "Otieno", "party_size": 2,
        "reservation_date": "2026-09-03", "reservation_time": "20:00:00",
    })

    assert resp.status_code == 200
    assert db_session.query(models.Reservation).count() == 1


# ── the paths nobody is watching ─────────────────────────────────────────────

def test_a_customer_app_order_is_recorded(client, db_session, admin):
    """
    The order source with no one standing at the till when it lands, and the one
    that produced nothing at all until this was noticed in review.
    """
    item_id = _menu_item(client, admin)
    restaurant = _restaurant(db_session)

    resp = client.post(f"/orders/public?restaurant_id={restaurant.id}", json={
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "customer_name": "Njeri", "customer_phone": "+254700000009",
        "consent": True,
    })
    assert resp.status_code == 200, resp.text

    created = _feed(db_session, "order_created")
    assert len(created) == 1
    assert "customer app" in created[0].body
    assert created[0].audience == notifications.AUDIENCE_ALL


def test_an_mpesa_settlement_is_recorded(db_session, admin, client):
    """
    M-Pesa is the primary payment method in this market and it settles through
    the webhook, not the POS. Recording only on the POS path — as an earlier
    version did — left every M-Pesa payment invisible in the feed.
    """
    from ai.orchestrator.executive import on_order_paid

    restaurant = _restaurant(db_session)

    on_order_paid({
        "restaurant_id": restaurant.id, "order_id": 41, "amount_cents": 250000,
        "customer_phone": "", "mpesa_reference": "QGR7XYZ12",
    })

    paid = _feed(db_session, "order_paid")
    assert len(paid) == 1
    assert "2,500" in paid[0].body
    assert "QGR7XYZ12" in paid[0].body


def test_pos_payment_records_exactly_one_notification(client, db_session, admin):
    """
    Both the POS endpoint and the webhook emit ORDER_PAID into the same handler.
    Recording in the endpoint *and* the handler would double up here.
    """
    item_id = _menu_item(client, admin)
    order_id = _place_order(client, admin, item_id)

    client.patch(f"/api/v1/orders/{order_id}/payment", headers=admin,
                 json={"payment_method": "cash", "is_paid": True})

    # emit_async runs the handler on a thread; give it a moment to land.
    import time
    for _ in range(50):
        if _feed(db_session, "order_paid"):
            break
        time.sleep(0.05)

    assert len(_feed(db_session, "order_paid")) == 1
