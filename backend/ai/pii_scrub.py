"""
backend/ai/pii_scrub.py
────────────────────────
Best-effort PII redaction applied at the ONE boundary where text leaves this
process for a third-party LLM (Groq / Anthropic) — see
ai/whatsapp/orchestrator.py. Everything else (the deterministic keyword replies
in brain.py) never leaves the process and is deliberately NOT scrubbed, so the
owner still reads real names/phones in their WhatsApp replies.

What it redacts and why:
  - Kenyan phone numbers — the customer is already identified server-side by
    phone; the LLM never needs the raw number in its context to reason ("the
    lapsed regular") and it's the most common PII leak (winback lists fall back
    to raw phone when a name is missing).
  - M-Pesa confirmation codes — transaction identifiers, no reasoning value.
  - PIN / National-ID digits, but ONLY when a "pin"/"id" label precedes them —
    a bare 7-8 digit number is far more likely a money figure, and clobbering
    those would break number-grounding (grounding.collect_payload_numbers runs
    AFTER this on tool results). Context-gating is what keeps money intact.
  - Customer/staff names ALREADY ON RECORD for the calling restaurant (audit
    remediation, Tier 3 item 8) — see known_names_for_restaurant() and the
    optional `known_names` param below. A denylist, not free-text name
    detection (no NER dependency): it redacts a name once it exists somewhere
    in this restaurant's Order.customer_name / StaffMember.name columns, but
    can't catch a name a customer only ever speaks in the chat itself and
    that was never recorded elsewhere. Documented, accepted residual gap —
    the alternative (a full NER pass) is a real dependency + accuracy
    tradeoff of its own, not obviously better for a Kenyan-name corpus.

Deliberately does NOT touch currency amounts or percentages: grounding depends
on those surviving so the model can cite them and the verifier can check them.
This is a heuristic layer, not a guarantee — documented as such.
"""

import re

# +2547XXXXXXXX / 2547XXXXXXXX / 07XXXXXXXX and the 01x (Airtel/newer) ranges.
# 10-12 digit shape with a 254/0 prefix — distinct from money figures.
_PHONE_RE = re.compile(r"\b(?:\+?254|0)(?:7|1)\d{8}\b")

# M-Pesa confirmation codes: 10 uppercase alphanumerics, e.g. "QGR7H2K9P1".
# Requires 2 leading letters + at least one digit so it doesn't match plain
# 10-letter words.
_MPESA_RE = re.compile(r"\b[A-Z]{2}(?=[A-Z0-9]*\d)[A-Z0-9]{8}\b")

# Label-gated secrets: keep the label + connector, redact only the digit group.
# The middle group allows a short run of non-digits ("is", ":", " no. ", " = ")
# between the label word and the number, but is bounded so it can't reach across
# a sentence into an unrelated figure.
_PIN_RE = re.compile(r"(?i)\b(pin)\b(\D{0,6}?)(\d{3,6})\b")
_ID_RE = re.compile(r"(?i)\b(id)\b(\D{0,10}?)(\d{7,8})\b")


def scrub_for_llm(text: str, known_names: "list[str] | None" = None) -> str:
    """Redact PII from text before it is handed to a third-party LLM. Idempotent
    and safe on non-strings (returned unchanged).

    `known_names`, if given, is an additional denylist of names to redact —
    see known_names_for_restaurant() below to build one. Kept optional so
    existing callers are unaffected: omitting it reproduces the exact prior
    behaviour (phone/M-Pesa/PIN/ID only, no name coverage)."""
    if not text or not isinstance(text, str):
        return text
    text = _PHONE_RE.sub("[phone]", text)
    text = _MPESA_RE.sub("[mpesa-code]", text)
    text = _PIN_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", text)
    text = _ID_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", text)
    if known_names:
        text = _redact_known_names(text, known_names)
    return text


def _redact_known_names(text: str, known_names: "list[str]") -> str:
    """Whole-word, case-insensitive redaction of each name in `known_names`.
    Longest names first, so "John Doe" is redacted as one unit before a
    shorter "John" entry (e.g. a staff member sharing a customer's first
    name) could fragment it. Names under 2 characters are skipped — too
    short to meaningfully identify anyone and too likely to collide with
    ordinary words."""
    names = sorted(
        {n.strip() for n in known_names if n and len(n.strip()) >= 2},
        key=len,
        reverse=True,
    )
    for name in names:
        pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        text = pattern.sub("[name]", text)
    return text


def known_names_for_restaurant(db, restaurant_id: int) -> "list[str]":
    """Denylist source for the `known_names` param above: every distinct
    customer name from this restaurant's Orders/Reservations, plus every
    active staff member's name. Call-site responsibility (not done here) to
    keep this off the hot path — see ai/whatsapp/orchestrator.py and
    ai/orchestrator/strategist.py for where it's actually invoked."""
    import models

    customer_names = [
        row[0] for row in
        db.query(models.Order.customer_name)
        .filter(models.Order.restaurant_id == restaurant_id, models.Order.customer_name != "")
        .distinct()
        .all()
    ]
    reservation_names = [
        row[0] for row in
        db.query(models.Reservation.customer_name)
        .filter(models.Reservation.restaurant_id == restaurant_id, models.Reservation.customer_name != "")
        .distinct()
        .all()
    ]
    staff_names = [
        row[0] for row in
        db.query(models.StaffMember.name)
        .filter(models.StaffMember.restaurant_id == restaurant_id, models.StaffMember.name != "")
        .distinct()
        .all()
    ]
    return list({*customer_names, *reservation_names, *staff_names})
