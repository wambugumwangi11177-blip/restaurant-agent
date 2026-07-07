"""
M-Pesa STK push callback: real Safaricom callback shape, correlation via
mpesa_checkout_request_id, idempotency, and failure handling. Mirrors the
5 scenarios verified by hand during Phase 1 (directives/012_agentic_roadmap.md).
"""

import models


def _seed(db_session):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    order = models.Order(
        id=1, restaurant_id=1, status=models.OrderStatus.PENDING,
        payment_method=models.PaymentMethod.PENDING, is_paid=False,
        customer_name="Jane", customer_phone="254712345678", total=50000,
        mpesa_checkout_request_id="ws_CO_test_001",
    )
    order2 = models.Order(
        id=2, restaurant_id=1, status=models.OrderStatus.PENDING,
        payment_method=models.PaymentMethod.PENDING, is_paid=False,
        customer_name="Bob", customer_phone="254799999999", total=30000,
        mpesa_checkout_request_id="ws_CO_test_002",
    )
    db_session.add_all([r, order, order2])
    db_session.commit()


def _success_callback(checkout_id="ws_CO_test_001"):
    return {"Body": {"stkCallback": {
        "MerchantRequestID": "mr-1", "CheckoutRequestID": checkout_id,
        "ResultCode": 0, "ResultDesc": "The service request is processed successfully.",
        "CallbackMetadata": {"Item": [
            {"Name": "Amount", "Value": 500.00},
            {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
            {"Name": "TransactionDate", "Value": 20260707120000},
            {"Name": "PhoneNumber", "Value": 254712345678},
        ]},
    }}}


def test_successful_payment_marks_order_paid(client, db_session):
    _seed(db_session)
    resp = client.post("/webhooks/mpesa", json=_success_callback())
    assert resp.status_code == 200
    assert resp.json()["ResultCode"] == 0

    order = db_session.query(models.Order).filter(models.Order.id == 1).first()
    assert order.is_paid is True
    assert order.payment_method == models.PaymentMethod.MPESA
    assert order.mpesa_receipt == "NLJ7RT61SV"


def test_duplicate_callback_is_idempotent(client, db_session):
    _seed(db_session)
    client.post("/webhooks/mpesa", json=_success_callback())
    resp = client.post("/webhooks/mpesa", json=_success_callback())
    assert resp.status_code == 200
    # Re-processing would otherwise re-send the WhatsApp receipt / re-write
    # the audit log — the webhook's own idempotency check must have skipped it.


def test_failed_payment_does_not_mark_paid(client, db_session):
    _seed(db_session)
    failure_callback = {"Body": {"stkCallback": {
        "MerchantRequestID": "mr-2", "CheckoutRequestID": "ws_CO_test_002",
        "ResultCode": 1032, "ResultDesc": "Request cancelled by user",
    }}}
    resp = client.post("/webhooks/mpesa", json=failure_callback)
    assert resp.status_code == 200

    order2 = db_session.query(models.Order).filter(models.Order.id == 2).first()
    assert order2.is_paid is False


def test_unknown_checkout_request_id_does_not_crash(client, db_session):
    _seed(db_session)
    unknown_callback = {"Body": {"stkCallback": {
        "MerchantRequestID": "mr-3", "CheckoutRequestID": "ws_CO_does_not_exist",
        "ResultCode": 0,
    }}}
    resp = client.post("/webhooks/mpesa", json=unknown_callback)
    assert resp.status_code == 200


def test_underpaid_callback_does_not_settle_order(client, db_session):
    """A success-coded callback reporting far less than the order total (e.g. a
    forged callback claiming KES 1 against a KES 500 order) must NOT mark the
    order paid."""
    _seed(db_session)  # order 1 total = 50000 cents (KES 500)
    underpaid = {"Body": {"stkCallback": {
        "MerchantRequestID": "mr-4", "CheckoutRequestID": "ws_CO_test_001",
        "ResultCode": 0, "ResultDesc": "OK",
        "CallbackMetadata": {"Item": [
            {"Name": "Amount", "Value": 1.00},   # KES 1 -> 100 cents, well below 50000
            {"Name": "MpesaReceiptNumber", "Value": "FORGED123"},
            {"Name": "PhoneNumber", "Value": 254712345678},
        ]},
    }}}
    resp = client.post("/webhooks/mpesa", json=underpaid)
    assert resp.status_code == 200  # still acks Safaricom

    order = db_session.query(models.Order).filter(models.Order.id == 1).first()
    assert order.is_paid is False
    assert order.mpesa_receipt is None
