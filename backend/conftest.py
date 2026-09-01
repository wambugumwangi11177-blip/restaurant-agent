"""Project-wide pytest fixtures and environment sanitization.

LLM provider keys (OPENAI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY) are read
once at module-import time in backend/ai/llm_client.py, so monkeypatch.delenv()
inside a test body is too late — the import has already cached the value.

This conftest unsets those env vars at the process level before any test or
fixture module is imported, so the llm_client tests' assertions on
provider selection / is_available() hold regardless of whether a real key is
inherited from the shell or a .env file used during local development.
"""
import os

# Strip real LLM API keys so tests that assert on provider-selection logic
# aren't poisoned by keys present in the developer's environment.
for _key in ("OPENAI_API_KEY", "GROQ_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ.pop(_key, None)
