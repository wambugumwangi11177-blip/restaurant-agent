"""
phone_utils.normalize_phone: an owner's phone stored at onboarding must match the
inbound WhatsApp number at compare time. Before this, auth.py stored the raw form
while webhooks.py normalized only the inbound number, so a non-E.164 entry (local
07…, spaces, a leading +) silently never matched and owner commands broke.
"""
from phone_utils import normalize_phone


def test_local_zero_prefix_matches_inbound_e164():
    # Owner types the local format; Twilio delivers E.164 — must resolve equal.
    assert normalize_phone("0712345678") == normalize_phone("whatsapp:+254712345678")


def test_formatting_noise_is_stripped():
    canonical = normalize_phone("254712345678")
    assert normalize_phone("+254712345678") == canonical
    assert normalize_phone("254 712 345 678") == canonical
    assert normalize_phone("254-712-345678") == canonical
    assert normalize_phone("whatsapp:+254 712 345 678") == canonical


def test_empty_and_none_are_empty_string():
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""


def test_idempotent():
    once = normalize_phone("0712345678")
    assert normalize_phone(once) == once


def test_distinct_numbers_do_not_collapse():
    assert normalize_phone("0712345678") != normalize_phone("0787654321")
