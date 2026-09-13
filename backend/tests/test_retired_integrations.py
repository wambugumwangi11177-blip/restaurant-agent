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


@pytest.mark.parametrize("path,body", [("/ai/marketing/promo", {"offer_text": "Test only"}),
                                      ("/ai/marketing/winback", {})])
def test_retired_marketing_dispatch_returns_gone(client, db_session, path, body):
    from auth import get_current_user
    from main import app
    owner = models.User(email="retired-owner@example.com", hashed_password="unused",
                        role=models.Role.ADMIN, is_active=True)
    db_session.add(owner)
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: owner
    try:
        response = client.post(path, json=body)
        assert response.status_code == 410
        assert "in-app" in response.json()["detail"]
        assert db_session.query(models.AgentMessage).count() == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
