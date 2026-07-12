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


def scrub_for_llm(text: str) -> str:
    """Redact PII from text before it is handed to a third-party LLM. Idempotent
    and safe on non-strings (returned unchanged)."""
    if not text or not isinstance(text, str):
        return text
    text = _PHONE_RE.sub("[phone]", text)
    text = _MPESA_RE.sub("[mpesa-code]", text)
    text = _PIN_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", text)
    text = _ID_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", text)
    return text
