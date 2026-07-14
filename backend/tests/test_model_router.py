"""
Multi-model AI Router (Phase 7).

The single most valuable routing rule is "forecast/deterministic tasks use no
LLM" — it must hold regardless of which provider is configured. Reasoning must
route to the HIGH tier, cheap/realtime to LOW, and unknown needs must fall back
safely rather than error.
"""

import pytest

from ai import llm_client
from ai.routing import choose_model, route_task, NEED
from ai.llm_client import TIER_LOW, TIER_HIGH


@pytest.fixture
def groq_active(monkeypatch):
    """Pretend Groq is the configured provider so model resolution returns ids."""
    monkeypatch.setattr(llm_client, "_PROVIDER", "groq")
    return "groq"


def test_forecast_never_uses_an_llm(groq_active):
    r = choose_model(NEED.FORECAST)
    assert r.use_llm is False
    assert r.model == "engine"


def test_deterministic_tasks_route_to_engine(groq_active):
    for task in ("revenue_forecast", "twin", "simulation", "decisions_ranking"):
        assert route_task(task).use_llm is False


def test_reasoning_routes_to_high_tier(groq_active):
    r = choose_model(NEED.REASONING)
    assert r.use_llm is True
    assert r.tier == TIER_HIGH
    assert r.model == llm_client.model_for_tier(TIER_HIGH)
    assert r.preferred_provider == "anthropic"


def test_cheap_and_realtime_route_to_low_tier(groq_active):
    assert choose_model(NEED.CHEAP).tier == TIER_LOW
    assert choose_model(NEED.REALTIME).tier == TIER_LOW


def test_strategy_task_is_reasoning(groq_active):
    r = route_task("strategy")
    assert r.tier == TIER_HIGH
    assert "strategy" in r.reason


def test_unknown_need_falls_back_to_cheap(groq_active):
    r = choose_model("teleportation")
    assert r.tier == TIER_LOW


def test_unknown_task_falls_back_to_cheap(groq_active):
    assert route_task("something_new").tier == TIER_LOW


def test_reason_notes_provider_mismatch(groq_active):
    # reasoning prefers anthropic but groq is active → reason should say so
    r = choose_model(NEED.REASONING)
    assert "prefers anthropic" in r.reason


def test_no_provider_configured_still_decides(monkeypatch):
    monkeypatch.setattr(llm_client, "_PROVIDER", None)
    # forecast still routes to engine; llm needs resolve model to None gracefully
    assert choose_model(NEED.FORECAST).use_llm is False
    r = choose_model(NEED.REASONING)
    assert r.use_llm is True and r.model is None    # no model, but a valid decision
