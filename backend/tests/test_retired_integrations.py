"""The in-app-only product has no external settlement or phone endpoints."""
import pytest
import models


@pytest.mark.parametrize("path", ["/webhooks/mpesa", "/webhooks/mpesa/old-token",
                                  "/webhooks/whatsapp", "/webhooks/stripe"])
def test_retired_webhooks_cannot_mutate_orders(client, db_session, path):
    restaurant = models.Restaurant(name="Historical records")
    db_session.add(restaurant)
    db_session.flush()
    order = models.Order(restaurant_id=restaurant.id, total=10000, is_paid=False,
                         payment_method=models.PaymentMethod.MPESA)
    db_session.add(order)
    db_session.commit()
    response = client.post(path, json={"order_id": order.id, "ResultCode": 0})
    assert response.status_code == 404
    db_session.refresh(order)
    assert order.is_paid is False
    assert order.total == 10000
    assert order.payment_method == models.PaymentMethod.MPESA


def test_legacy_phone_send_cannot_dispatch(monkeypatch):
    from ai.whatsapp.brain import send_whatsapp_message
    assert send_whatsapp_message("+254700000001", "Private customer message") == {
        "status": "retired", "sid": None}
