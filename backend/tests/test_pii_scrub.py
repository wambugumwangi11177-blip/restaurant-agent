"""
PII scrubbing at the LLM boundary (P4, 2026-07-11).

Proves scrub_for_llm() redacts phones / M-Pesa codes / label-gated PIN & ID
digits, while leaving money and percentage figures intact so number-grounding
still works. See ai/pii_scrub.py.
"""

from ai.pii_scrub import scrub_for_llm


def test_redacts_kenyan_phone_formats():
    for raw in ["0712345678", "+254712345678", "254712345678", "0112345678"]:
        out = scrub_for_llm(f"call the customer on {raw} today")
        assert raw not in out, raw
        assert "[phone]" in out


def test_redacts_mpesa_confirmation_code():
    out = scrub_for_llm("Payment QGR7H2K9P1 received")
    assert "QGR7H2K9P1" not in out
    assert "[mpesa-code]" in out


def test_redacts_pin_only_with_label():
    out = scrub_for_llm("my pin is 1234 ok")
    assert "1234" not in out
    assert "pin" in out.lower()
    assert "[redacted]" in out


def test_redacts_national_id_with_label():
    out = scrub_for_llm("ID number 12345678 for the record")
    assert "12345678" not in out
    assert "[redacted]" in out


def test_keeps_money_and_percentages():
    # These MUST survive — grounding.collect_payload_numbers runs after scrub and
    # the model needs to cite them.
    text = "Revenue was KES 45,000 today, up 12% from yesterday across 87 orders."
    out = scrub_for_llm(text)
    assert "45,000" in out
    assert "12%" in out
    assert "87" in out


def test_bare_large_number_not_treated_as_id():
    # No 'id'/'pin' label -> a bare 8-digit figure (could be cents) is untouched.
    out = scrub_for_llm("Total sales 12345678 cents this month")
    assert "12345678" in out


def test_safe_on_empty_and_non_string():
    assert scrub_for_llm("") == ""
    assert scrub_for_llm(None) is None


def test_idempotent():
    once = scrub_for_llm("reach them on 0712345678")
    twice = scrub_for_llm(once)
    assert once == twice
