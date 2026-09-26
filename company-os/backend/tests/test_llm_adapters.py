"""Provider adapters: request shape and response normalisation, with the network
replaced by stubs. Guards the parts of llm.py a scripted fake can't reach."""

import copy
from types import SimpleNamespace

import pytest

from app.kernel.agents import llm

TOOLS = [llm.ToolSpec(name="search_memory", description="d", input_schema={"type": "object", "properties": {}})]


class _Resp:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, str(data)

    def json(self):
        return self._data


def test_openai_compatible_roundtrip(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(openrouter_api_key="k", groq_api_key="", llm_timeout_seconds=5))
    sent = []
    replies = [
        {"model": "m1", "usage": {"prompt_tokens": 11, "completion_tokens": 3},
         "choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
             {"id": "c1", "type": "function", "function": {"name": "search_memory", "arguments": '{"query": "x"}'}}]}}]},
        {"model": "m1", "usage": {"prompt_tokens": 20, "completion_tokens": 5},
         "choices": [{"finish_reason": "stop", "message": {"content": "done"}}]},
    ]

    def fake_post(url, json, headers, timeout):
        sent.append((url, copy.deepcopy(json), headers))
        return _Resp(200, replies.pop(0))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    conv = llm.OpenAICompatConversation("openrouter", "sys", "hello", TOOLS, "medium")
    t1 = conv.send()
    assert t1.stop_reason == "tool_use" and t1.tool_uses[0].input == {"query": "x"} and t1.input_tokens == 11
    conv.add_tool_results([("c1", "result text", False)])
    t2 = conv.send()
    assert (t2.stop_reason, t2.text) == ("end_turn", "done")

    url, body, headers = sent[1]
    assert url.startswith("https://openrouter.ai/")
    assert headers["Authorization"] == "Bearer k"
    assert body["tools"][0]["function"]["name"] == "search_memory"
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert body["messages"][2]["tool_calls"][0]["id"] == "c1"
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": "result text"}


def test_openai_compatible_http_error(monkeypatch):
    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(openrouter_api_key="k", groq_api_key="", llm_timeout_seconds=5))
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: _Resp(429, {"error": "rate"}))
    with pytest.raises(llm.LLMError, match="429"):
        llm.OpenAICompatConversation("openrouter", "s", "u", [], "low").send()


def _block(**kw):
    return SimpleNamespace(**kw)


def test_anthropic_request_shape_refusal_and_replay(monkeypatch):
    import anthropic

    monkeypatch.setattr(llm, "get_settings", lambda: SimpleNamespace(anthropic_api_key="k", llm_timeout_seconds=5))
    for k in ("ANTHROPIC_MODEL", "ANTHROPIC_MODEL_HIGH"):
        monkeypatch.delenv(k, raising=False)
    calls = []
    thinking = _block(type="thinking", thinking="", signature="sig")
    responses = [
        SimpleNamespace(model="claude-opus-5", stop_reason="tool_use", usage=SimpleNamespace(input_tokens=50, output_tokens=9),
                        content=[thinking, _block(type="tool_use", id="tu1", name="search_memory", input={"query": "q"})]),
        SimpleNamespace(model="claude-opus-5", stop_reason="refusal", usage=SimpleNamespace(input_tokens=5, output_tokens=0),
                        stop_details=SimpleNamespace(category="cyber"), content=[]),
    ]

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

    class FakeClient:
        def __init__(self, **kw):
            self.beta = SimpleNamespace(messages=FakeMessages())

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    conv = llm.AnthropicConversation("sys", "question", TOOLS, "high")
    t1 = conv.send()
    assert t1.tool_uses[0].name == "search_memory" and t1.stop_reason == "tool_use"
    conv.add_tool_results([("tu1", "found", False)])
    t2 = conv.send()
    assert t2.stop_reason == "refusal" and "cyber" in t2.detail

    first = calls[0]
    assert first["model"] == "claude-opus-5"
    assert first["fallbacks"] == "default" and first["betas"] == ["server-side-fallback-2026-07-01"]
    assert first["output_config"] == {"effort": "high"}
    assert "thinking" not in first  # adaptive by default on Opus 5; never sent as disabled
    msgs = calls[1]["messages"]
    assert msgs[1]["content"][0] is thinking  # full assistant content replayed unchanged
    assert msgs[2]["content"][0] == {"type": "tool_result", "tool_use_id": "tu1", "content": "found", "is_error": False}
