"""
M-Pesa STK push callback: real Safaricom callback shape, correlation via
mpesa_checkout_request_id, idempotency, and failure handling. Mirrors the
5 scenarios verified by hand during Phase 1 (directives/012_agentic_roadmap.md).
"""

import models


def _seed(db_session):
    tenant = models.Tenant(name="Mpesa Tenant")
    db_session.add(tenant)
    db_session.commit()
    r = models.Restaurant(id=1, tenant_id=tenant.id, name="Test Bistro", address="x")
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


# ── Callback origin verification (MPESA_CALLBACK_TOKEN) ──
#
# Safaricom signs nothing, so the CallBackURL secret is the only authentication.
# The settlement amount is read from the attacker-controlled body, so without
# this guard a forged ResultCode:0 against a known CheckoutRequestID settles an
# order for free.

def test_forged_callback_without_token_is_rejected(client, db_session, monkeypatch):
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "s3cret-daraja-token")
    _seed(db_session)

    resp = client.post("/webhooks/mpesa", json=_success_callback())
    assert resp.status_code == 403

    order = db_session.query(models.Order).filter(models.Order.id == 1).first()
    assert order.is_paid is False


def test_callback_with_wrong_token_is_rejected(client, db_session, monkeypatch):
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "s3cret-daraja-token")
    _seed(db_session)

    resp = client.post("/webhooks/mpesa/guessed-token", json=_success_callback())
    assert resp.status_code == 403

    order = db_session.query(models.Order).filter(models.Order.id == 1).first()
    assert order.is_paid is False


def test_callback_with_correct_token_settles(client, db_session, monkeypatch):
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "s3cret-daraja-token")
    _seed(db_session)

    resp = client.post("/webhooks/mpesa/s3cret-daraja-token", json=_success_callback())
    assert resp.status_code == 200
    assert resp.json()["ResultCode"] == 0

    order = db_session.query(models.Order).filter(models.Order.id == 1).first()
    assert order.is_paid is True
    assert order.mpesa_receipt == "NLJ7RT61SV"


def test_tokenless_path_still_works_when_token_unset(client, db_session, monkeypatch):
    """Degrade-safe: no env var (local dev) → legacy path keeps working."""
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)
    _seed(db_session)

    resp = client.post("/webhooks/mpesa", json=_success_callback())
    assert resp.status_code == 200

    order = db_session.query(models.Order).filter(models.Order.id == 1).first()
    assert order.is_paid is True


# ── Duplicate / concurrent settlement ─────────────────────────────────────────
#
# `if order.is_paid` is a lock-free read. Two Safaricom retries landing together
# both pass it, both settle, and both emit ORDER_PAID -> two "payment confirmed"
# WhatsApps and two audit rows. The conditional UPDATE moves the decision into
# the DB, where it is atomic.

def test_settle_order_once_is_atomic_under_a_real_race(db_session):
    """
    Deterministic interleave of the exact race: session A reads the order as
    unpaid, session B settles it, then A tries to settle. Only one of them may
    be told it won. (Two sessions, because the race is between two requests,
    each with its own `Depends(get_db)` session.)
    """
    from routers.webhooks import _settle_order_once
    import database

    _seed(db_session)

    session_a = database.SessionLocal()
    session_b = database.SessionLocal()
    try:
        # A reads the order and sees is_paid=False — the lock-free read that
        # made the old code think it was safe to proceed.
        order_a = session_a.query(models.Order).filter(models.Order.id == 1).first()
        assert order_a.is_paid is False

        # B settles first and wins.
        assert _settle_order_once(session_b, 1, "RECEIPT_B") is True

        # A now settles on stale knowledge — the DB must refuse it.
        assert _settle_order_once(session_a, 1, "RECEIPT_A") is False
    finally:
        session_a.close()
        session_b.close()

    db_session.expire_all()
    order = db_session.query(models.Order).filter(models.Order.id == 1).first()
    assert order.is_paid is True
    assert order.mpesa_receipt == "RECEIPT_B"   # the winner's receipt, not overwritten


def test_duplicate_callback_emits_order_paid_exactly_once(client, db_session, monkeypatch):
    """End-to-end: two identical callbacks produce exactly one ORDER_PAID."""
    import events.bus as bus

    emitted = []
    monkeypatch.setattr(bus, "emit_async", lambda et, payload: emitted.append((et, payload)))

    _seed(db_session)
    assert client.post("/webhooks/mpesa", json=_success_callback()).status_code == 200
    assert client.post("/webhooks/mpesa", json=_success_callback()).status_code == 200

    paid = [e for e in emitted if e[0] == bus.EventType.ORDER_PAID]
    assert len(paid) == 1, f"expected exactly one ORDER_PAID, got {len(paid)}"
