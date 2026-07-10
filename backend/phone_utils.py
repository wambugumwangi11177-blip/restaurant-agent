"""
backend/phone_utils.py
───────────────────────
One canonical form for phone numbers, so a number WRITTEN in one place (an owner
typing their phone into the onboarding wizard) reliably MATCHES the same number
READ in another (an inbound WhatsApp `From` header).

The bug this exists to prevent: routers/auth.py used to store `owner_phone`
verbatim from the form, while routers/webhooks.py normalized only the *inbound*
Twilio number before an exact-string compare. An owner who typed `0712 345 678`
or `+254712345678` stored a value that could never equal the `254712345678`
Twilio delivers — silently breaking owner commands and outbound alerts. Both the
writer and the reader must run every number through normalize_phone() so they
are comparing the same representation.

Scope: this app is Kenya-only (KES, M-Pesa/Safaricom, Daraja). Owners routinely
enter the local `07…`/`01…` format; Twilio always delivers E.164 (`2547…`). So
normalization (a) strips formatting noise to digits and (b) converts a 9–10 digit
local number with a leading 0 to its 254 country-code form. It deliberately does
NOT invent a country code for a bare number that has neither a leading 0 nor a
254 prefix — that would merge genuinely different numbers.
"""

import re

_KE_COUNTRY_CODE = "254"


def normalize_phone(raw: str | None) -> str:
    """
    Canonicalize a phone number to E.164 (leading '+') for storage and
    comparison. Returns "" for empty/None input. Idempotent — safe to call on an
    already-normalized value.

    E.164 with the '+' is required, not digits-only: the outbound sender
    (ai/whatsapp/twilio_client.py) formats `whatsapp:{stored}`, and Twilio
    rejects `whatsapp:254…` — it needs `whatsapp:+254…`.

    Examples (all → "+254712345678"):
        "+254712345678", "254712345678", "0712345678",
        "whatsapp:+254 712 345 678", "254-712-345678"
    """
    if not raw:
        return ""
    # Drop a Twilio channel prefix and reduce to digits (removes +, spaces,
    # dashes, parentheses, and the "whatsapp:" prefix all at once).
    digits = re.sub(r"\D", "", raw.replace("whatsapp:", ""))
    if not digits:
        return ""
    # Local format: leading 0 + 9 national digits (e.g. 0712345678) → 254712345678.
    if digits.startswith("0") and len(digits) == 10:
        digits = _KE_COUNTRY_CODE + digits[1:]
    return "+" + digits
