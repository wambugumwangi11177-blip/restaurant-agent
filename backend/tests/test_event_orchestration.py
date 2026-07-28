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


def _tenant_id(db) -> int:
    tenant = models.Tenant(name="Events Tenant")
    db.add(tenant)
    db.commit()
    return tenant.id


def _seed_restaurant_with_table(db_session):
    r = models.Restaurant(id=1, tenant_id=_tenant_id(db_session), name="Test Bistro", address="x")
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
    r = models.Restaurant(id=1, tenant_id=_tenant_id(db_session), name="Test Bistro", address="x")
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


# ── MPESA_PAYMENT_FAILED ──────────────────────────────────────────────────────
#
# webhooks.py emitted this event and executive.register_all_handlers never
# subscribed to it (found 2026-07-08): a cancelled or insufficient-funds STK push
# told nobody, and the order silently stayed unpaid.

def _seed_restaurant_with_owner(db_session, owner_phone="+254712345678"):
    r = models.Restaurant(id=1, tenant_id=_tenant_id(db_session), name="Test Bistro", address="x",
                          owner_phone=owner_phone)
    order = models.Order(
        id=7, restaurant_id=1, status=models.OrderStatus.PENDING,
        payment_method=models.PaymentMethod.PENDING, is_paid=False, total=50000,
    )
    db_session.add_all([r, order])
    db_session.commit()


def test_mpesa_payment_failed_is_subscribed(db_session):
    """The event must have a handler at all — this is the bug that shipped."""
    clear_handlers()
    from ai.orchestrator.executive import register_all_handlers
    register_all_handlers()

    import events.bus as bus
    assert bus._handlers.get(EventType.MPESA_PAYMENT_FAILED), \
        "MPESA_PAYMENT_FAILED is emitted by webhooks.py but nothing subscribes to it"


def test_mpesa_payment_failed_notifies_the_owner_once(db_session, monkeypatch):
    _seed_restaurant_with_owner(db_session)

    sent = []
    import ai.whatsapp as whatsapp_mod
    monkeypatch.setattr(whatsapp_mod, "send_whatsapp_message",
                        lambda to, msg, **kw: sent.append((to, msg)))

    clear_handlers()
    from ai.orchestrator.executive import register_all_handlers, on_mpesa_payment_failed
    register_all_handlers()

    on_mpesa_payment_failed({
        "restaurant_id": 1, "order_id": 7, "reason": "Request cancelled by user",
    })

    assert len(sent) == 1
    to, msg = sent[0]
    assert to == "+254712345678"           # the owner, not the customer
    assert "#7" in msg
    assert "Request cancelled by user" in msg


def test_mpesa_payment_failed_audits_even_with_no_owner_phone(db_session, monkeypatch):
    """No owner number configured must not swallow the failure silently."""
    _seed_restaurant_with_owner(db_session, owner_phone=None)
    monkeypatch.delenv("OWNER_PHONE", raising=False)
    monkeypatch.delenv("OWNER_PHONE_1", raising=False)

    sent = []
    import ai.whatsapp as whatsapp_mod
    monkeypatch.setattr(whatsapp_mod, "send_whatsapp_message",
                        lambda to, msg, **kw: sent.append((to, msg)))

    from ai.orchestrator.executive import on_mpesa_payment_failed
    on_mpesa_payment_failed({"restaurant_id": 1, "order_id": 7, "reason": "Timeout"})

    assert sent == []
    logs = db_session.query(models.AgentAuditLog).filter(
        models.AgentAuditLog.action_type == "mpesa_payment_failed"
    ).all()
    assert len(logs) == 1
    assert "Timeout" in logs[0].reasoning


def test_successful_payment_does_not_notify_owner_of_failure(db_session, monkeypatch):
    """Regression guard: the success path must not trip the failure handler."""
    _seed_restaurant_with_owner(db_session)

    sent = []
    import ai.whatsapp as whatsapp_mod
    monkeypatch.setattr(whatsapp_mod, "send_whatsapp_message",
                        lambda to, msg, **kw: sent.append((to, msg)))

    clear_handlers()
    from ai.orchestrator.executive import register_all_handlers
    register_all_handlers()

    emit(EventType.ORDER_PAID, {
        "restaurant_id": 1, "order_id": 7, "amount_cents": 50000,
        "customer_phone": None, "mpesa_reference": "OK123",
    })

    assert not any("Payment Failed" in m for _, m in sent)
