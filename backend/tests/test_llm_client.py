"""
LLM client provider selection and Groq response normalization. Mocked HTTP
boundary only — no real network/tokens spent in CI. The real live-API
round-trip (directives/012_agentic_roadmap.md) was verified by hand once
with a real Groq key against a throwaway local database; this suite is the
permanent regression coverage for the same code path.
"""

import importlib
import json
from types import SimpleNamespace


def _reload_llm_client():
    from ai import llm_client
    importlib.reload(llm_client)
    return llm_client


def test_no_provider_configured_is_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    llm_client = _reload_llm_client()
    assert llm_client.is_available() is False


def test_groq_selected_when_only_groq_key_present(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
    llm_client = _reload_llm_client()
    assert llm_client._PROVIDER == "groq"
    assert llm_client.is_available() is True


def test_anthropic_preferred_when_both_keys_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake_anthropic_key")
    monkeypatch.setenv("GROQ_API_KEY", "fake_groq_key")
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
