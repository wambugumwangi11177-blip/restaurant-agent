"""
app/kernel/channels/whatsapp.py
───────────────────────────────
WhatsApp via Twilio: signature validation for inbound webhooks and a plain
REST send for outbound. No Twilio SDK — both are a few lines of HTTP.

Signature algorithm (Twilio docs, "Validating requests"): base64 of
HMAC-SHA1(auth_token, full_url + concatenation of every POST param as
key+value, sorted by key), compared to the X-Twilio-Signature header.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

import httpx

from app.config import get_settings


class ChannelNotConfigured(RuntimeError):
    pass


class ChannelSendError(RuntimeError):
    pass


def compute_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    payload = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def valid_signature(url: str, params: dict[str, str], signature: str | None) -> bool:
    token = get_settings().twilio_auth_token
    if not token or not signature:
        return False
    return hmac.compare_digest(compute_signature(token, url, params), signature)


def send(to_digits: str, body: str) -> str:
    """Send a WhatsApp message; returns Twilio's message SID."""
    s = get_settings()
    if not s.twilio_configured:
        raise ChannelNotConfigured("Twilio WhatsApp is not configured (TWILIO_ACCOUNT_SID/AUTH_TOKEN/WHATSAPP_FROM)")
    try:
        r = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
            data={"From": s.twilio_whatsapp_from, "To": f"whatsapp:+{to_digits}", "Body": body[:1600]},
            auth=(s.twilio_account_sid, s.twilio_auth_token),
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise ChannelSendError(f"could not reach Twilio: {e}") from e
    if r.status_code >= 400:
        raise ChannelSendError(f"Twilio error {r.status_code}: {r.text[:300]}")
    return r.json().get("sid", "")


def twiml_message(text: str) -> str:
    """A synchronous webhook reply (no outbound API call needed)."""
    from xml.sax.saxutils import escape

    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text[:1600])}</Message></Response>'
