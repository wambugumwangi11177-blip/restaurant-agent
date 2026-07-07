"""
backend/payments/mpesa_client.py
─────────────────────────────────
Safaricom Daraja API integration. Pure request/response — no DB, no business
logic. Mirrors the shape of ai/whatsapp/twilio_client.py: a CONFIGURED flag,
graceful degradation when credentials aren't set, real HTTP calls otherwise.

Env vars required (Daraja sandbox or production):
    MPESA_CONSUMER_KEY
    MPESA_CONSUMER_SECRET
    MPESA_SHORTCODE            (Paybill/Till number, e.g. "174379" for sandbox)
    MPESA_PASSKEY
    MPESA_CALLBACK_URL         (public HTTPS URL Safaricom will POST results to)
    MPESA_ENV                  ("sandbox" or "production", default "sandbox")
"""

import os
import base64
import datetime
import logging
import requests

logger = logging.getLogger("payments.mpesa")

MPESA_CONSUMER_KEY    = os.getenv("MPESA_CONSUMER_KEY", "")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET", "")
MPESA_SHORTCODE       = os.getenv("MPESA_SHORTCODE", "")
MPESA_PASSKEY         = os.getenv("MPESA_PASSKEY", "")
MPESA_CALLBACK_URL    = os.getenv("MPESA_CALLBACK_URL", "")
MPESA_ENV             = os.getenv("MPESA_ENV", "sandbox")

def normalize_phone(phone: str) -> str | None:
    """
    Daraja requires MSISDN in 2547XXXXXXXX / 2541XXXXXXXX format (no '+', no
    leading 0). Accepts the common Kenyan input shapes a customer might type
    or that WhatsApp/order forms might send. Returns None if unrecognizable
    rather than guessing — an STK push to a malformed number just fails
    silently on Safaricom's side, which is worse than rejecting it here.
    """
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        return "254" + digits[1:]
    if digits.startswith("7") and len(digits) == 9:
        return "254" + digits
    if digits.startswith("1") and len(digits) == 9:
        return "254" + digits
    return None


CONFIGURED = bool(
    MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET and MPESA_SHORTCODE
    and MPESA_PASSKEY and MPESA_CALLBACK_URL
)

_BASE_URL = (
    "https://api.safaricom.co.ke" if MPESA_ENV == "production"
    else "https://sandbox.safaricom.co.ke"
)


def _get_access_token() -> str:
    resp = requests.get(
        f"{_BASE_URL}/oauth/v1/generate?grant_type=client_credentials",
        auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def initiate_stk_push(phone_number: str, amount_cents: int, account_reference: str, description: str) -> dict:
    """
    Trigger an STK push (Lipa Na M-Pesa Online) prompt on the customer's phone.

    phone_number: MSISDN in 2547XXXXXXXX format (no '+', no 'whatsapp:' prefix).
    amount_cents: order total in cents — converted to whole KES shillings here,
                  since Daraja's STK push API only accepts whole-shilling amounts.

    Returns {"status": "initiated", "checkout_request_id": str} on success,
    {"status": "not_configured"} if credentials aren't set,
    {"status": "error", "detail": str} on failure.
    """
    if not CONFIGURED:
        logger.warning(f"[MPesa] NOT CONFIGURED — would push KES {amount_cents // 100} to {phone_number}")
        return {"status": "not_configured", "checkout_request_id": None}

    amount_shillings = max(amount_cents // 100, 1)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode(
        f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode("utf-8")
    ).decode("utf-8")

    try:
        token = _get_access_token()
        resp = requests.post(
            f"{_BASE_URL}/mpesa/stkpush/v1/processrequest",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "BusinessShortCode": MPESA_SHORTCODE,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": amount_shillings,
                "PartyA": phone_number,
                "PartyB": MPESA_SHORTCODE,
                "PhoneNumber": phone_number,
                "CallBackURL": MPESA_CALLBACK_URL,
                "AccountReference": account_reference,
                "TransactionDesc": description,
            },
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()
        return {"status": "initiated", "checkout_request_id": body.get("CheckoutRequestID")}
    except requests.RequestException as exc:
        logger.error(f"[MPesa] STK push error: {exc}")
        return {"status": "error", "detail": str(exc), "checkout_request_id": None}
