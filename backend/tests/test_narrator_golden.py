"""
Golden-output regression tests for the reasoning narrator (P7, 2026-07-11).

These lock in the CONTRACT of narrate(), not exact LLM prose (which is
non-deterministic). For representative tasks — profit (LOW tier), pricing
(MEDIUM, a money decision), marketing (constrained: must never invent audience
sizes) — they assert:
  • the returned dict always has the full shape (headline/priorities/actions +
    grounding + provenance keys),
  • a well-formed reply that only cites payload figures comes back verified,
  • each action carries the {action, why, impact} keys guaranteed by the P6
    Pydantic validation,
  • a malformed (non-JSON) reply degrades to the graceful fallback, never raises,
  • an invented figure (e.g. a fake audience size in marketing) is redacted by
    the grounding guard.

The LLM is stubbed — no network, no tokens. Mirrors _stub_llm in
test_reasoning_endpoints.py.
"""

from types import SimpleNamespace

import pytest

from ai import llm_client
from ai.reasoning import narrator

_STUB_MODEL_ID = "stub-golden-model"

# Purely qualitative reply — cites no figures, so grounding must pass it clean.
_WELL_FORMED = (
    '{"headline": "Delivery is your least profitable channel.", '
    '"priorities": ["Your bestseller carries a thin margin.", "Waste is creeping up."], '
    '"actions": [{"action": "Promote high-margin starters", '
    '"why": "they lift blended margin", "impact": "more profit per cover"}]}'
)

_EXPECTED_KEYS = {
    "headline", "priorities", "actions",
    "model", "tier", "cached",
    "verified", "ungrounded_numbers",
}


def _stub(monkeypatch, reply_text: str):
    narrator._cache.clear()  # module-global; a prior test/call could shadow this one
    monkeypatch.setattr(llm_client, "is_available", lambda: True)

    def fake_chat_with_usage(**kwargs):
        return SimpleNamespace(
            text=reply_text, model=_STUB_MODEL_ID,
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
    monkeypatch.setattr(llm_client, "chat_with_usage", fake_chat_with_usage)


# A minimal payload per task. Content is irrelevant to a qualitative reply (the
# whitelist just trims it); it only needs to be a dict so narrate() proceeds.
_PAYLOADS = {
    "profit": {"summary": {"gross_margin_pct": 62}, "channels": [{"name": "delivery"}]},
    "pricing": {"recommendations": [{"item": "Burger", "action": "REPRICE"}]},
    "marketing": {"reachable_audience": 3, "lapsed_regulars": [{"name": "A"}]},
}


@pytest.mark.parametrize("task", ["profit", "pricing", "marketing"])
def test_well_formed_reply_has_full_shape_and_is_verified(task, monkeypatch):
    _stub(monkeypatch, _WELL_FORMED)
    result = narrator.narrate(dict(_PAYLOADS[task]), task)

    assert result is not None
    assert _EXPECTED_KEYS <= set(result), f"{task}: missing {_EXPECTED_KEYS - set(result)}"
    # Grounding: a figure-free reply is fully grounded.
    assert result["verified"] is True
    assert result["ungrounded_numbers"] == []
    # Structure, not prose.
    assert result["headline"] != ""
    assert len(result["actions"]) >= 1
    for a in result["actions"]:
        assert set(a.keys()) == {"action", "why", "impact"}
    assert result["cached"] is False
    assert result["model"] == _STUB_MODEL_ID


@pytest.mark.parametrize("task", ["profit", "pricing", "marketing"])
def test_malformed_reply_degrades_gracefully(task, monkeypatch):
    # Plain prose, no JSON object at all — must not raise, must flag the fallback.
    _stub(monkeypatch, "Sorry, I can't structure that right now.")
    result = narrator.narrate(dict(_PAYLOADS[task]), task)

    assert result is not None
    assert result.get("parse_fallback") is True
    assert result["headline"] != ""          # truncated prose becomes the headline
    assert result["actions"] == []
    # Grounding still ran on the fallback and produced its keys.
    assert "verified" in result


def test_marketing_invented_audience_size_is_redacted(monkeypatch):
    # The marketing task must never state audience numbers it wasn't given.
    # "500 customers" appears in no payload, so the guard must strip it.
    _stub(
        monkeypatch,
        '{"headline": "Blast all 500 customers tonight.", "priorities": [], "actions": []}',
    )
    result = narrator.narrate({"reachable_audience": 3}, "marketing")

    assert result["verified"] is False
    assert "500" in result["ungrounded_numbers"]
    assert "500" not in result["headline"]
