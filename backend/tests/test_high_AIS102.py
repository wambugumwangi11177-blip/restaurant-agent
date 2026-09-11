"""
AIS-102 — the PII scrub must FAIL CLOSED before the LLM boundary.

narrator._scrub_payload() documented "Fail-open on scrubber/DB errors" while
its bail-out log said "sending would leak — bailing out". This pins the
resolution toward fail-closed: if the scrubber errors, OR the per-tenant
known-names lookup fails (making the redaction set indeterminate), narrate()
must return None WITHOUT calling the LLM — the unredacted payload must never
reach the third-party provider.
"""

from types import SimpleNamespace

import pytest

from ai import llm_client, pii_scrub
from ai.reasoning import narrator


_STUB_MODEL_ID = "stub-ais102-model"

_WELL_FORMED = (
    '{"headline": "ok", "priorities": [], '
    '"actions": [{"action": "a", "why": "w", "impact": "i"}]}'
)


def _stub_llm(monkeypatch):
    """Stub the provider boundary and record whether it was ever called."""
    narrator._cache.clear()
    calls = {"n": 0}

    monkeypatch.setattr(llm_client, "is_available", lambda: True)

    def fake_chat_with_usage(**kwargs):
        calls["n"] += 1
        return SimpleNamespace(
            text=_WELL_FORMED, model=_STUB_MODEL_ID,
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
    monkeypatch.setattr(llm_client, "chat_with_usage", fake_chat_with_usage)
    return calls


def test_scrubber_error_is_fail_closed(monkeypatch):
    """If scrub_for_llm raises, narrate() must return None and NEVER call the LLM."""
    calls = _stub_llm(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("scrubber exploded")

    monkeypatch.setattr(pii_scrub, "scrub_for_llm", boom)

    result = narrator.narrate({"summary": {"x": 1}}, "profit")
    assert result is None
    assert calls["n"] == 0, "LLM was called despite a PII scrub failure (fail-open)"


def test_known_names_lookup_error_is_fail_closed(monkeypatch):
    """If the tenant name-denylist can't be built, redaction is indeterminate —
    narrate() must refuse the LLM call rather than scrub with an empty list."""
    calls = _stub_llm(monkeypatch)

    from database import SessionLocal
    from ai.reasoning import narrator as _n

    def boom(*args, **kwargs):
        raise RuntimeError("DB gone")

    monkeypatch.setattr(pii_scrub, "known_names_for_restaurant", boom)

    result = narrator.narrate({"summary": {"x": 1}}, "profit", restaurant_id=1)
    assert result is None
    assert calls["n"] == 0, "LLM was called with an indeterminate denylist"
