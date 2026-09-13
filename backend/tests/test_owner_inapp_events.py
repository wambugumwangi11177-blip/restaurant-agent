"""Enriched owner event notices persist without provider credentials or phones."""
import pytest
import models


@pytest.mark.parametrize("handler,payload,event_type", [
    ("on_stock_depleted", {"item_name": "Chicken"}, "stock_depleted"),
    ("on_stock_transfer_discrepancy", {"transfer_id": 1, "item_name": "Chicken",
        "declared_quantity": 10, "confirmed_quantity": 8}, "stock_transfer_discrepancy"),
    ("on_stock_count_discrepancy", {"item_name": "Chicken", "expected_quantity": 10,
        "counted_quantity": 8}, "stock_count_discrepancy"),
    ("on_purchase_order_created", {"po_id": 1, "item_name": "Chicken", "quantity": 10},
        "purchase_order_drafted"),
    ("on_purchase_order_delivered", {"po_id": 1, "item_name": "Chicken",
        "quantity_ordered": 10, "quantity_received": 8, "shortfall": 2},
        "purchase_order_short_delivery"),
])
def test_owner_events_persist_without_phone_and_do_not_cross_tenants(
        db_session, monkeypatch, handler, payload, event_type):
    from ai.orchestrator import executive
    from ai.whatsapp import brain
    tenant = models.Tenant(name="Owner events")
    other = models.Tenant(name="Other events")
    db_session.add_all([tenant, other])
    db_session.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Owner restaurant", owner_phone=None)
    owner = models.User(tenant_id=tenant.id, email="owner-events@example.com",
        hashed_password="unused", role=models.Role.ADMIN, is_active=True)
    foreign = models.User(tenant_id=other.id, email="foreign-events@example.com",
        hashed_password="unused", role=models.Role.ADMIN, is_active=True)
    db_session.add_all([restaurant, owner, foreign])
    db_session.commit()
    monkeypatch.setattr(executive, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(brain, "send_whatsapp_message", lambda *a, **kw:
        pytest.fail("An owner event attempted external phone dispatch"))
    getattr(executive, handler)({"restaurant_id": restaurant.id, **payload})
    notice = db_session.query(models.Notification).filter_by(event_type=event_type).one()
    assert notice.user_id == owner.id
    assert "Chicken" in notice.body
    assert db_session.query(models.Notification).filter_by(user_id=foreign.id).count() == 0
