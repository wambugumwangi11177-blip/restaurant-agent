"""The suite must not spend a provider key that arrived from the environment or backend/.env."""
import importlib

import pytest


def test_provider_keys_are_unset_and_a_chat_call_is_refused():
    import os
    from ai import llm_client
    for key in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
        assert not os.environ.get(key)
    assert llm_client.is_available() is False
    with pytest.raises(AssertionError, match="real LLM"):
        llm_client.chat_with_usage([{"role": "user", "content": "hello"}])


def test_reloading_with_a_key_still_refuses_to_build_a_live_client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-must-not-call")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    import ai.llm_client as llm_client
    importlib.reload(llm_client)
    assert llm_client.is_available() is True
    assert llm_client._client is None
    with pytest.raises(AssertionError, match="real LLM"):
        llm_client.chat_with_usage([{"role": "user", "content": "hello"}])
