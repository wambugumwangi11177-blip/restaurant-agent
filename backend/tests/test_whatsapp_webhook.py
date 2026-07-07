"""
Inbound WhatsApp webhook: Twilio signature validation must be real and
fail-closed, and the keyword fast-path must never touch the LLM orchestrator.
"""

import importlib
import os
from twilio.request_validator import RequestValidator

import models
from ai.whatsapp import twilio_client


def _seed_restaurant(db_session, owner_phone="+15559999999"):
    os.environ["TWILIO_AUTH_TOKEN"] = "testtoken123"
    # Clear any legacy env config so we exercise the owner_phone COLUMN path.
    os.environ.pop("OWNER_PHONE_1", None)
    os.environ.pop("OWNER_PHONE", None)

    # ai.whatsapp.twilio_client reads TWILIO_AUTH_TOKEN at import time (it was
    # already imported at test-collection time, before this env var existed) —
    # reload so validate_twilio_request actually sees "testtoken123".
    importlib.reload(twilio_client)

    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x", owner_phone=owner_phone)
    db_session.add(r)
    db_session.commit()


def _sign(url: str, params: dict) -> str:
    return RequestValidator(os.environ["TWILIO_AUTH_TOKEN"]).compute_signature(url, params)


def test_missing_signature_is_rejected(client, db_session):
    _seed_restaurant(db_session)
    resp = client.post(
        "http://testserver/webhooks/whatsapp",
        data={"From": "whatsapp:+15559999999", "Body": "SALES"},
    )
    assert resp.status_code == 403


def test_bad_signature_is_rejected(client, db_session):
    _seed_restaurant(db_session)
    resp = client.post(
        "http://testserver/webhooks/whatsapp",
        data={"From": "whatsapp:+15559999999", "Body": "SALES"},
        headers={"X-Twilio-Signature": "garbage"},
    )
    assert resp.status_code == 403


def test_valid_signature_keyword_command_replies(client, db_session):
    """
    The known-command path must reply with real data and must never invoke
    the LLM orchestrator — this is the whole point of the hybrid router
    (directives/012_agentic_roadmap.md, Phase 2): most owner traffic should
    cost zero tokens.
    """
    _seed_restaurant(db_session)
    os.environ.pop("ANTHROPIC_API_KEY", None)  # if this test needed the LLM, it would now fail/degrade

    url = "https://testserver/webhooks/whatsapp"  # https: matches twilio_client's forced-https rewrite
    request_url = "http://testserver/webhooks/whatsapp"
    params = {"From": "whatsapp:+15559999999", "Body": "SALES"}
    sig = _sign(url, params)

    resp = client.post(request_url, data=params, headers={"X-Twilio-Signature": sig})
    assert resp.status_code == 200
    assert "Sales Today" in resp.text or "Revenue" in resp.text


def test_unknown_sender_returns_empty_twiml_without_crashing(client, db_session):
    _seed_restaurant(db_session)
    url = "https://testserver/webhooks/whatsapp"
    request_url = "http://testserver/webhooks/whatsapp"
    params = {"From": "whatsapp:+10009998888", "Body": "SALES"}
    sig = _sign(url, params)

    resp = client.post(request_url, data=params, headers={"X-Twilio-Signature": sig})
    assert resp.status_code == 200
    assert "<Response>" in resp.text
