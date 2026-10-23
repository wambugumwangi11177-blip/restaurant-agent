"""
LLM client provider selection and Groq response normalization. Mocked HTTP
boundary only — no real network/tokens spent in CI. The real live-API
round-trip (directives/012_agentic_roadmap.md) was verified by hand once
with a real Groq key against a throwaway local database; this suite is the
permanent regression coverage for the same code path.
"""

import importlib
import json
import os
from types import SimpleNamespace

import pytest


def _reload_llm_client():
    from ai import llm_client
    importlib.reload(llm_client)
    return llm_client


@pytest.fixture(autouse=True)
def _restore_llm_client_after_env_reload():
    """Reload reads provider keys at import. Put the module back so later tests are not left with a fake key."""
    yield
    for name in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY",
                 "OPENROUTER_MODEL", "OPENROUTER_MODEL_LOW", "OPENROUTER_MODEL_HIGH",
                 "OPENROUTER_MODEL_CREATIVE", "OPENROUTER_FALLBACK_MODEL"):
        os.environ.pop(name, None)
    _reload_llm_client()


def test_no_provider_configured_is_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    llm_client = _reload_llm_client()
    assert llm_client.is_available() is False


def test_openrouter_selected_when_only_openrouter_key_present(monkeypatch):
    """Production (Railway) has only OPENROUTER_API_KEY set. Before this was
    supported, _PROVIDER resolved to None there and every LLM feature silently
    served its deterministic fallback — /ai/strategy returned the same ranked
    plan for every goal asked."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake_openrouter_key")
    llm_client = _reload_llm_client()
    assert llm_client._PROVIDER == "openrouter"
    assert llm_client.is_available() is True


def test_openrouter_preferred_over_groq_and_anthropic(monkeypatch):
    """OpenRouter is the owner's configured gateway, so it wins when set."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake_anthropic_key")
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake_openrouter_key")
    llm_client = _reload_llm_client()
    assert llm_client._PROVIDER == "openrouter"


def test_openrouter_default_model_is_not_a_groq_id(monkeypatch):
    """Guards the OpenAI-compatible branches' `resolved or _default_model()`
    fallback: OpenRouter ids are namespaced per vendor, so handing it Groq's
    default would 404."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake_openrouter_key")
    llm_client = _reload_llm_client()
    assert llm_client._default_model() == llm_client._OPENROUTER_MODEL
    assert llm_client._default_model() != llm_client._GROQ_MODEL
    # Every tier resolves to something concrete, not None.
    for tier in (llm_client.TIER_LOW, llm_client.TIER_MEDIUM, llm_client.TIER_HIGH):
        assert llm_client.model_for_tier(tier)


def test_groq_selected_when_only_groq_key_present(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    llm_client = _reload_llm_client()
    assert llm_client._PROVIDER == "groq"
    assert llm_client.is_available() is True


def test_anthropic_preferred_when_both_keys_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake_anthropic_key")
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    llm_client = _reload_llm_client()
    assert llm_client._PROVIDER == "anthropic"


def _fake_openai_response(content=None, tool_calls=None, model="llama-3.3-70b-versatile"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    return SimpleNamespace(choices=[choice], model=model, usage=usage)


def test_groq_tool_use_response_normalized_to_anthropic_shape(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    llm_client = _reload_llm_client()

    tool_call = SimpleNamespace(
        id="call_123",
        function=SimpleNamespace(name="get_sales_today", arguments="{}"),
    )
    fake_response = _fake_openai_response(content=None, tool_calls=[tool_call])

    class FakeCompletions:
        def create(self, **kwargs):
            return fake_response

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    llm_client._client = FakeClient()

    result = llm_client.chat_with_tools(
        messages=[{"role": "user", "content": "how are sales"}],
        tools=[{"name": "get_sales_today", "description": "x", "input_schema": {"type": "object", "properties": {}}}],
        system="test system prompt",
    )

    assert result.stop_reason == "tool_use"
    assert len(result.content) == 1
    assert result.content[0].type == "tool_use"
    assert result.content[0].name == "get_sales_today"
    assert result.content[0].input == {}
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20


def test_groq_end_turn_response_normalized(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    llm_client = _reload_llm_client()

    fake_response = _fake_openai_response(content="Sales are looking good today!", tool_calls=None)

    class FakeCompletions:
        def create(self, **kwargs):
            return fake_response

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    llm_client._client = FakeClient()

    result = llm_client.chat_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        system="test",
    )

    assert result.stop_reason == "end_turn"
    assert result.content[0].type == "text"
    assert result.content[0].text == "Sales are looking good today!"


def test_canonical_messages_translate_tool_result_to_openai_tool_role(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    llm_client = _reload_llm_client()

    canonical = [
        {"role": "user", "content": "how are sales"},
        {"role": "assistant", "content": [
            SimpleNamespace(type="tool_use", id="call_123", name="get_sales_today", input={}),
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "call_123", "content": "Revenue: KES 0"},
        ]},
    ]

    translated = llm_client._canonical_messages_to_openai(canonical)

    assert translated[0] == {"role": "user", "content": "how are sales"}
    assert translated[1]["role"] == "assistant"
    assert translated[1]["tool_calls"][0]["id"] == "call_123"
    assert translated[1]["tool_calls"][0]["function"]["name"] == "get_sales_today"
    assert translated[2] == {"role": "tool", "tool_call_id": "call_123", "content": "Revenue: KES 0"}


def test_canonical_messages_preserve_tool_call_arguments(monkeypatch):
    """Regression: the assistant tool-call turn used to hardcode arguments to
    '{}', silently dropping any arguments the model chose. They must survive."""
    import json as _json
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    llm_client = _reload_llm_client()

    canonical = [
        {"role": "user", "content": "book a table for 4 at 7pm"},
        {"role": "assistant", "content": [
            SimpleNamespace(
                type="tool_use", id="call_9",
                name="find_tables", input={"party_size": 4, "time": "19:00"},
            ),
        ]},
    ]

    translated = llm_client._canonical_messages_to_openai(canonical)
    args = _json.loads(translated[1]["tool_calls"][0]["function"]["arguments"])
    assert args == {"party_size": 4, "time": "19:00"}


def test_openrouter_defaults_are_deepseek_with_a_qwen_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake_openrouter_key")
    for name in ("OPENROUTER_MODEL", "OPENROUTER_MODEL_LOW", "OPENROUTER_MODEL_HIGH",
                 "OPENROUTER_MODEL_CREATIVE", "OPENROUTER_FALLBACK_MODEL"):
        monkeypatch.delenv(name, raising=False)
    llm_client = _reload_llm_client()
    assert llm_client._OPENROUTER_MODEL == "deepseek/deepseek-v4-flash"
    assert llm_client._OPENROUTER_MODEL_LOW == "deepseek/deepseek-v4-flash"
    assert llm_client.model_for_tier(llm_client.TIER_HIGH) == "deepseek/deepseek-v4-flash"
    assert llm_client.model_for_tier(llm_client.TIER_CREATIVE) == "deepseek/deepseek-v4-flash"
    assert llm_client._OPENROUTER_FALLBACK_MODEL == "qwen/qwen3.7-flash"
    assert ":free" not in llm_client._OPENROUTER_MODEL
    body = llm_client._openrouter_extra(None, llm_client._OPENROUTER_MODEL)
    assert body["provider"]["data_collection"] == "deny"
    assert body["models"] == ["deepseek/deepseek-v4-flash", "qwen/qwen3.7-flash"]


def test_empty_content_is_retried_once(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    llm_client = _reload_llm_client()
    seen = {"n": 0}

    class FakeCompletions:
        def create(self, **kwargs):
            seen["n"] += 1
            content = "" if seen["n"] == 1 else "A different take on the same figures."
            return _fake_openai_response(content=content)

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    llm_client._client = FakeClient()
    result = llm_client.chat_with_usage([{"role": "user", "content": "ideas"}], system="be brief")
    assert seen["n"] == 2
    assert result.text == "A different take on the same figures."


def test_empty_content_after_retry_stays_empty_and_is_logged(monkeypatch, caplog):
    import logging
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    llm_client = _reload_llm_client()

    class FakeCompletions:
        def create(self, **kwargs):
            return _fake_openai_response(content="  ")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    llm_client._client = FakeClient()
    with caplog.at_level(logging.WARNING):
        result = llm_client.chat_with_usage([{"role": "user", "content": "ideas"}])
    assert result.text.strip() == ""
    assert "empty content after one retry" in caplog.text


def test_openrouter_chat_sends_data_collection_deny(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake_openrouter_key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    llm_client = _reload_llm_client()
    seen = {}

    class FakeCompletions:
        def create(self, **kwargs):
            seen.update(kwargs)
            return _fake_openai_response(content="Noted.")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    llm_client._client = FakeClient()
    llm_client.chat_with_usage([{"role": "user", "content": "hello"}], extra_body={"provider": {"order": ["deepseek"]}})
    assert seen["extra_body"]["provider"]["data_collection"] == "deny"
    assert seen["extra_body"]["provider"]["order"] == ["deepseek"]
    assert "qwen/qwen3.7-flash" in seen["extra_body"]["models"]
