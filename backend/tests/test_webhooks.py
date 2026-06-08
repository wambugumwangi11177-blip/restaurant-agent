"""
Test suite for webhook endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from main import app
import hmac
import hashlib
import os

client = TestClient(app)

def test_stripe_webhook_endpoint_exists():
    """Test that Stripe webhook endpoint exists."""
    response = client.post("/webhooks/stripe")
    # Should return 400 (missing signature) not 404 (not found)
    assert response.status_code != 404

def test_mpesa_webhook_endpoint_exists():
    """Test that M-Pesa webhook endpoint exists."""
    response = client.post("/webhooks/mpesa")
    # Should return 400 (missing signature) not 404 (not found)
    assert response.status_code != 404

def test_stripe_webhook_missing_signature():
    """Test Stripe webhook with missing signature."""
    response = client.post(
        "/webhooks/stripe",
        json={"test": "data"}
    )
    assert response.status_code == 400
    assert "Missing Stripe-Signature header" in response.json()["detail"]

def test_mpesa_webhook_missing_signature():
    """Test M-Pesa webhook with missing signature."""
    response = client.post(
        "/webhooks/mpesa",
        json={"test": "data"}
    )
    # Should return 400 or process in dev mode (since no secret configured)
    # In dev mode with no secret, it should still process
    assert response.status_code == 200  # Dev mode allows it
    assert response.json()["status"] == "received"

def test_webhook_json_parsing():
    """Test that webhooks can parse JSON data."""
    # Test Stripe webhook with valid-like payload but missing signature
    response = client.post(
        "/webhooks/stripe",
        json={"id": "evt_test", "object": "event", "type": "payment_intent.succeeded"},
        headers={"Stripe-Signature": "invalid_signature"}
    )
    # Should fail signature verification, not JSON parsing
    assert response.status_code == 400
    # Should be signature error, not JSON error
    assert "signature" in response.json()["detail"].lower()

def test_webhook_handles_large_payload():
    """Test webhook handling of larger payloads."""
    large_data = {"data": "x" * 10000}  # 10KB payload
    response = client.post(
        "/webhooks/stripe",
        json=large_data,
        headers={"Stripe-Signature": "invalid_signature"}
    )
    # Should handle large payloads (fail on signature, not size)
    assert response.status_code == 400
    assert "signature" in response.json()["detail"].lower()