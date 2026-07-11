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
import re
import hmac
import hashlib
import base64
import logging

logger = logging.getLogger("ai.whatsapp.twilio")

TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
# SMS sender: a Twilio number or an approved alphanumeric Sender ID. Kept
# separate from WhatsApp because the two channels bill and format differently,
# and a deployment may have one configured but not the other. Not everyone in
# Kenya uses WhatsApp — SMS reaches any phone — so SMS is a first-class channel,
# not a fallback afterthought.
TWILIO_SMS_FROM      = os.getenv("TWILIO_SMS_FROM", "")

CONFIGURED = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)

# Channels this transport understands.
CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_SMS      = "sms"

# Emoji / pictographs render as tofu boxes on feature phones and eat into the
# 160-char SMS segment budget, and WhatsApp *bold* markers are literal asterisks
# over SMS. strip both for SMS.
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U0000FE00-\U0000FE0F\U0000200D←-⇿⌀-⏿]",   # + variation selectors & ZWJ
    flags=re.UNICODE,
)


def to_sms(message: str) -> str:
    """
    Render a WhatsApp-formatted message as plain SMS text: drop emoji, remove
    *bold* markers, and collapse the runs of blank lines the WhatsApp templates
    use for spacing (which would waste SMS segments). Content is unchanged.
    """
    text = _EMOJI_RE.sub("", message)
    text = text.replace("*", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Trim stray leading spaces left where an emoji used to sit.
    text = "\n".join(line.rstrip().lstrip() if line.strip() else "" for line in text.split("\n"))
    return text.strip()


def _channel_configured(channel: str) -> bool:
    if not CONFIGURED:
        return False
    if channel == CHANNEL_SMS:
        return bool(TWILIO_SMS_FROM)
    return bool(TWILIO_WHATSAPP_FROM)


def send(to_number: str, message: str, channel: str = CHANNEL_WHATSAPP,
         media_url: str | None = None) -> dict:
    """
    Send a message via Twilio over WhatsApp (default) or SMS.
    Returns {"status": str, "sid": str | None}. No DB access — caller logs.

    For SMS the message is auto-rendered plain (to_sms) and the `whatsapp:`
    address prefix is never applied. `media_url` attaches a publicly reachable
    media file (e.g. a voice-note audio URL) — WhatsApp only; ignored for SMS,
    which can't carry rich media.
    """
    if not _channel_configured(channel):
        logger.warning(f"[Twilio] NOT CONFIGURED ({channel}) — would send to {to_number}: {message[:200]}")
        return {"status": "not_configured", "sid": None}

    try:
        from twilio.rest import Client
        from twilio.http.http_client import TwilioHttpClient
        # Bound the HTTP call so a slow Twilio never hangs the request (critical
        # on a single gunicorn worker). No automatic retry: a message send is not
        # idempotent — retrying a timed-out request risks double-sending a
        # WhatsApp/SMS. Callers already treat a failed send as best-effort.
        http_client = TwilioHttpClient(timeout=float(os.getenv("TWILIO_TIMEOUT_SECONDS", "10")))
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, http_client=http_client)

        create_kwargs = {}
        if channel == CHANNEL_SMS:
            to = to_number.replace("whatsapp:", "")
            body = to_sms(message)
            from_ = TWILIO_SMS_FROM
        else:
            to = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
            body = message
            from_ = TWILIO_WHATSAPP_FROM
            if media_url:
                create_kwargs["media_url"] = [media_url]

        msg = client.messages.create(from_=from_, to=to, body=body, **create_kwargs)
        return {"status": "sent", "sid": msg.sid}
    except ImportError:
        logger.error("[Twilio] Package not installed. Run: pip install twilio")
        return {"status": "twilio_not_installed", "sid": None}
    except Exception as exc:
        logger.error(f"[Twilio] Send error: {exc}")
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
