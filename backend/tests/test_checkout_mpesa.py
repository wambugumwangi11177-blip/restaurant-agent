"""
Order checkout: STK push is triggered for M-Pesa orders, phone normalization
guards against malformed numbers, and the payment_method bug (create_public_order
silently forcing PENDING regardless of customer's chosen method) stays fixed.
"""

import importlib
import models
from payments import mpesa_client


def _seed_menu(db_session):
    tenant = models.Tenant(name="Test Tenant")
    db_session.add(tenant)
    db_session.commit()
    r = models.Restaurant(id=1, tenant_id=tenant.id, name="Test Bistro", address="x")
    item = models.MenuItem(id=1, restaurant_id=1, name="Burger", price=50000, is_available=True)
    db_session.add_all([r, item])
    db_session.commit()


def _mock_daraja(monkeypatch, checkout_request_id="ws_CO_checkout_flow_001"):
    def fake_get(url, auth=None, timeout=None):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"access_token": "fake_token"}
        return R()

    def fake_post(url, headers=None, json=None, timeout=None):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"CheckoutRequestID": checkout_request_id}
        return R()

    monkeypatch.setenv("MPESA_CONSUMER_KEY", "fake_key")
    monkeypatch.setenv("MPESA_CONSUMER_SECRET", "fake_secret")
    monkeypatch.setenv("MPESA_SHORTCODE", "174379")
    monkeypatch.setenv("MPESA_PASSKEY", "fake_passkey")
    monkeypatch.setenv("MPESA_CALLBACK_URL", "https://example.com/webhooks/mpesa")

    # payments.mpesa_client reads its env vars at import time (CONFIGURED,
    # MPESA_*). It was already imported at test-collection time, before these
    # monkeypatched env vars existed — reload so it picks them up now, and
    # reapply the mocked requests.get/post onto the reloaded module.
    importlib.reload(mpesa_client)
    monkeypatch.setattr(mpesa_client.requests, "get", fake_get)
    monkeypatch.setattr(mpesa_client.requests, "post", fake_post)


def test_mpesa_order_triggers_stk_push_and_stores_checkout_id(client, db_session, monkeypatch):
    _seed_menu(db_session)
    _mock_daraja(monkeypatch)

    resp = client.post("/orders/public?restaurant_id=1", json={
        "items": [{"menu_item_id": 1, "quantity": 1}],
        "payment_method": "mpesa",
        "customer_name": "Jane",
        "customer_phone": "0712345678",
        "consent": True,
    })
    assert resp.status_code == 200
    assert resp.json()["payment_method"] == "mpesa"

    order = db_session.query(models.Order).filter(models.Order.id == resp.json()["id"]).first()
    assert order.mpesa_checkout_request_id == "ws_CO_checkout_flow_001"


def test_malformed_phone_skips_stk_push_without_crashing(client, db_session, monkeypatch):
    _seed_menu(db_session)
    _mock_daraja(monkeypatch)

    resp = client.post("/orders/public?restaurant_id=1", json={
        "items": [{"menu_item_id": 1, "quantity": 1}],
        "payment_method": "mpesa",
        "customer_name": "Bob",
        "customer_phone": "not-a-real-phone",
        "consent": True,
    })
    assert resp.status_code == 200

    order = db_session.query(models.Order).filter(models.Order.id == resp.json()["id"]).first()
    assert order.mpesa_checkout_request_id is None


def test_cash_order_keeps_chosen_payment_method(client, db_session, monkeypatch):
    """Regression test: create_public_order used to always force PENDING
    regardless of the customer's chosen payment_method."""
    _seed_menu(db_session)
    _mock_daraja(monkeypatch)

    resp = client.post("/orders/public?restaurant_id=1", json={
        "items": [{"menu_item_id": 1, "quantity": 1}],
        "payment_method": "cash",
        "customer_name": "Cash Customer",
        "customer_phone": "0700000000",
        "consent": True,
    })
    assert resp.json()["payment_method"] == "cash"
