"""
Event orchestration wiring. Found 2026-07-07 auditing end to end: 5 of 7
event types subscribed by ai/orchestrator/executive.py were never emitted
anywhere, and 2 of 3 scheduler jobs ai/whatsapp/brain.py defines were never
registered — subscribers/definitions existed, but nothing ever triggered
them. These tests lock in that emit -> handler actually fires, using
clear_handlers() + a spy so a future refactor can't silently break the wiring
again without a test failing.
"""

from types import SimpleNamespace
import models
from events.bus import emit, subscribe, clear_handlers, EventType


def _seed_restaurant_with_table(db_session):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    item = models.InventoryItem(
        id=1, restaurant_id=1, item_name="Chicken", quantity=0, unit="kg", low_stock_threshold=5,
    )
    db_session.add_all([r, item])
    db_session.commit()


def test_stock_check_emits_stock_depleted_for_zero_quantity_items(db_session, monkeypatch):
    _seed_restaurant_with_table(db_session)
    clear_handlers()

    received = []
    subscribe(EventType.STOCK_DEPLETED, lambda payload: received.append(payload))

    from ai.whatsapp import brain
    monkeypatch.setattr(brain, "send_whatsapp_message", lambda *a, **k: {"status": "not_configured"})

    # run_stock_check calls db.close() in a finally block — make close() a
    # no-op so the shared test session survives for the assertion below.
    monkeypatch.setattr(db_session, "close", lambda: None)

    brain.run_stock_check(lambda: db_session)

    # emit_async runs in a background thread — give it a moment.
    import time as time_mod
    for _ in range(20):
        if received:
            break
        time_mod.sleep(0.05)

    assert len(received) == 1
    assert received[0]["restaurant_id"] == 1
    assert received[0]["item_name"] == "Chicken"
    assert received[0]["inventory_item_id"] == 1


def test_reservation_no_show_transition_emits_event(client, db_session, monkeypatch):
    import auth
    tenant = models.Tenant(name="Tenant NS")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(tenant_id=tenant.id, email="ns@example.com", hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN)
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Restaurant NS", address="x")
    db_session.add_all([user, restaurant])
    db_session.commit()

    from datetime import date, time
    reservation = models.Reservation(
        restaurant_id=restaurant.id, customer_name="Jane", customer_phone="0700000000",
        party_size=2, reservation_date=date(2026, 7, 10), reservation_time=time(19, 0),
        status=models.ReservationStatus.CONFIRMED,
    )
    db_session.add(reservation)
    db_session.commit()

    clear_handlers()
    received = []
    subscribe(EventType.RESERVATION_NO_SHOW, lambda payload: received.append(payload))

    token = auth.create_access_token({"sub": user.email})
    resp = client.patch(
        f"/reservations/{reservation.id}/status",
        json={"status": "no_show"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # emit_async runs in a background thread — give it a moment.
    import time as time_mod
    for _ in range(20):
        if received:
            break
        time_mod.sleep(0.05)

    assert len(received) == 1
    assert received[0]["customer_name"] == "Jane"
    assert received[0]["party_size"] == 2


def test_approve_recommendation_emits_recommendation_approved(db_session):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    item = models.MenuItem(id=1, restaurant_id=1, name="Burger", price=50000, is_available=True)
    rec = models.PricingRecommendation(
        id=1, restaurant_id=1, menu_item_id=1, recommendation_type="SURGE",
        current_price=50000, suggested_price=55000, status="PENDING",
    )
    db_session.add_all([r, item, rec])
    db_session.commit()

    clear_handlers()
    received = []
    subscribe(EventType.RECOMMENDATION_APPROVED, lambda payload: received.append(payload))

    from ai.pricing.recommendations import approve_recommendation
    result = approve_recommendation(db_session, 1, 1, approved_by="owner@test.com")

    assert result["success"] is True
    assert len(received) == 1
    assert received[0]["item_name"] == "Burger"
    assert received[0]["approved_by"] == "owner@test.com"
    assert received[0]["old_price"] == 50000
    assert received[0]["new_price"] == 55000
