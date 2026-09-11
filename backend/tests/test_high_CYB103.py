"""
CYB-103 — the M-Pesa callback must FAIL CLOSED when MPESA_CALLBACK_TOKEN is
unset or empty.

Before the fix, _verify_mpesa_token() with an unconfigured token logged a
one-time warning and ACCEPTED tokenless callbacks (POST /webhooks/mpesa) when
M-Pesa itself was unconfigured — an accept-by-default posture. Now the token
is required unconditionally: unset/empty -> 403 with a log, always. The
startup guard (startup_checks.collect_problems) mirrors this: production
without the token is a hard (boot-blocking) problem even when M-Pesa creds
are absent; dev logs a warning.

Reuses the callback fixtures/shape from test_mpesa_webhook.py.
"""

import pytest

import models
import startup_checks


_TOKEN = "test-daraja-token"


def _seed(db_session):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    order = models.Order(
        id=1, restaurant_id=1, status=models.OrderStatus.PENDING,
        payment_method=models.PaymentMethod.PENDING, is_paid=False,
        customer_name="Jane", customer_phone="254712345678", total=50000,
        mpesa_checkout_request_id="ws_CO_test_001",
    )
    db_session.add_all([r, order])
    db_session.commit()


def _success_callback():
    return {"Body": {"stkCallback": {
        "MerchantRequestID": "mr-1", "CheckoutRequestID": "ws_CO_test_001",
        "ResultCode": 0, "ResultDesc": "The service request is processed successfully.",
        "CallbackMetadata": {"Item": [
            {"Name": "Amount", "Value": 500.00},
            {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
            {"Name": "TransactionDate", "Value": 20260707120000},
            {"Name": "PhoneNumber", "Value": 254712345678},
        ]},
    }}}


def test_unset_token_rejects_callback(client, db_session, monkeypatch):
    """CYB-103: token unset -> callback rejected (no accept-by-default)."""
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)
    _seed(db_session)

    resp = client.post("/webhooks/mpesa", json=_success_callback())
    assert resp.status_code in (403, 503)

    order = db_session.query(models.Order).filter(models.Order.id == 1).first()
    assert order.is_paid is False


def test_empty_token_rejects_callback(client, db_session, monkeypatch):
    """An empty/whitespace token counts as unset."""
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "   ")
    _seed(db_session)

    resp = client.post("/webhooks/mpesa", json=_success_callback())
    assert resp.status_code in (403, 503)


def test_valid_token_accepted(client, db_session, monkeypatch):
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", _TOKEN)
    _seed(db_session)

    resp = client.post(f"/webhooks/mpesa/{_TOKEN}", json=_success_callback())
    assert resp.status_code == 200
    assert resp.json()["ResultCode"] == 0

    order = db_session.query(models.Order).filter(models.Order.id == 1).first()
    assert order.is_paid is True


def test_invalid_token_rejected(client, db_session, monkeypatch):
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", _TOKEN)
    _seed(db_session)

    resp = client.post("/webhooks/mpesa/wrong-token", json=_success_callback())
    assert resp.status_code == 403


# ── Startup guard ─────────────────────────────────────────────────────────────
# Production requires the token even without M-Pesa creds (the token IS the
# callback's only authentication); non-production warns.

def test_startup_production_requires_token_even_without_mpesa_creds(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)

    hard, soft = startup_checks.collect_problems()
    assert any("MPESA_CALLBACK_TOKEN" in h for h in hard)
    with pytest.raises(RuntimeError):
        startup_checks.enforce_startup_checks()


def test_startup_dev_without_token_warns_only(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("MPESA_ENV", raising=False)
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.delenv("MPESA_CALLBACK_TOKEN", raising=False)

    hard, soft = startup_checks.collect_problems()
    assert not any("MPESA_CALLBACK_TOKEN" in h for h in hard)
    assert any("MPESA_CALLBACK_TOKEN" in s for s in soft)
    startup_checks.enforce_startup_checks()  # must NOT raise outside production
