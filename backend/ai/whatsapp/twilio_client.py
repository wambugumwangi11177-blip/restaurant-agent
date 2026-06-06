"""
backend/ai/whatsapp/twilio_client.py
─────────────────────────────────────
Twilio integration layer. Pure send/validate — no DB, no business logic.

Fixes vs previous version:
  BUG-01  — validate_twilio_request reconstructs HTTPS URL explicitly so
             reverse-proxy deployments (Render, Railway) don't break signature checks
  CLEAN   — removed unused `urllib.parse` import
  CLEAN   — removed unused `Optional` import (not needed in Python 3.10+)
"""

import os
import hmac
import hashlib
import base64

TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

CONFIGURED = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)


def send(to_number: str, message: str) -> dict:
    """
    Send a WhatsApp message via Twilio.
    Returns {"status": str, "sid": str | None}.
    No DB access — caller handles logging.
    """
    if not CONFIGURED:
        print(f"[Twilio] NOT CONFIGURED — would send to {to_number}:\n{message[:200]}")
        return {"status": "not_configured", "sid": None}

    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        to = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
        msg = client.messages.create(from_=TWILIO_WHATSAPP_FROM, to=to, body=message)
        return {"status": "sent", "sid": msg.sid}
    except ImportError:
        print("[Twilio] Package not installed. Run: pip install twilio")
        return {"status": "twilio_not_installed", "sid": None}
    except Exception as exc:
        print(f"[Twilio] Send error: {exc}")
        return {"status": "error", "sid": None}


def validate_twilio_request(
    request_url: str,
    post_params: dict,
    signature: str,
) -> bool:
    """
    Validate that an inbound HTTP request genuinely came from Twilio.
    Twilio signs: HTTPS URL + sorted POST params concatenated as key+value.

    BUG-01 FIX: Apps behind reverse proxies (Render, Railway, Vercel) receive
    requests as http:// internally even though Twilio sends to https://.
    We force https:// so the computed signature matches what Twilio computed.

    Returns True if valid. Returns False if TWILIO_AUTH_TOKEN is not set (fail-safe).
    """
    if not TWILIO_AUTH_TOKEN:
        return False

    # Force https — Twilio always signs the public HTTPS URL
    url = request_url
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]

    # Build the string Twilio signs: URL + sorted(key + value) for each param
    s = url
    if post_params:
        for key in sorted(post_params.keys()):
            s += key + str(post_params[key])

    mac = hmac.new(
        TWILIO_AUTH_TOKEN.encode("utf-8"),
        s.encode("utf-8"),
        hashlib.sha1,
    )
    expected = base64.b64encode(mac.digest()).decode("utf-8")

    # compare_digest prevents timing attacks
    return hmac.compare_digest(expected, signature)
