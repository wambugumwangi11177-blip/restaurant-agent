"""Unit tests for phone normalization and STK push request shape."""

import pytest
from payments.mpesa_client import normalize_phone


@pytest.mark.parametrize("raw,expected", [
    ("254712345678", "254712345678"),
    ("0712345678", "254712345678"),
    ("+254712345678", "254712345678"),
    ("712345678", "254712345678"),
    ("0112345678", "254112345678"),
    ("not-a-phone", None),
    ("123", None),
    ("", None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_not_configured_degrades_without_crashing(monkeypatch):
    import importlib
    from payments import mpesa_client
    monkeypatch.delenv("MPESA_CONSUMER_KEY", raising=False)
    importlib.reload(mpesa_client)

    result = mpesa_client.initiate_stk_push("254712345678", 50000, "ORDER-1", "Test order")
    assert result["status"] == "not_configured"


def test_not_configured_masks_phone_in_log(monkeypatch, caplog):
    """Audit remediation: this line used to log the raw customer phone number
    in plaintext (mpesa_client.py:86). Only the last 3 digits should appear."""
    import importlib
    import logging
    from payments import mpesa_client
    monkeypatch.delenv("MPESA_CONSUMER_KEY", raising=False)
    importlib.reload(mpesa_client)

    with caplog.at_level(logging.WARNING):
        mpesa_client.initiate_stk_push("254712345678", 50000, "ORDER-1", "Test order")

    log_text = caplog.text
    assert "254712345678" not in log_text
    assert "***678" in log_text


def test_configured_builds_correct_daraja_payload(monkeypatch):
    import importlib
    from payments import mpesa_client
    monkeypatch.setenv("MPESA_CONSUMER_KEY", "fake_key")
    monkeypatch.setenv("MPESA_CONSUMER_SECRET", "fake_secret")
    monkeypatch.setenv("MPESA_SHORTCODE", "174379")
    monkeypatch.setenv("MPESA_PASSKEY", "fake_passkey")
    monkeypatch.setenv("MPESA_CALLBACK_URL", "https://example.com/webhooks/mpesa")
    importlib.reload(mpesa_client)

    captured = {}

    def fake_get(url, auth=None, timeout=None):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"access_token": "fake_token_123"}
        return R()

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        captured["headers"] = headers
        class R:
            def raise_for_status(self): pass
            def json(self): return {"CheckoutRequestID": "ws_CO_test_12345"}
        return R()

    monkeypatch.setattr(mpesa_client.requests, "get", fake_get)
    monkeypatch.setattr(mpesa_client.requests, "post", fake_post)

    result = mpesa_client.initiate_stk_push("254712345678", 50000, "ORDER-1", "Test order")

    assert result["status"] == "initiated"
    assert result["checkout_request_id"] == "ws_CO_test_12345"
    assert captured["payload"]["Amount"] == 500  # 50000 cents -> 500 whole KES shillings
    assert captured["payload"]["PartyA"] == "254712345678"
    assert captured["headers"]["Authorization"] == "Bearer fake_token_123"
