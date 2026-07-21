"""
backend/ai/llm_client.py
─────────────────────────────
Single choke point for LLM calls, used by Phase 2 orchestrator
(ai/whatsapp/orchestrator.py) and any future Phase 3 AI modules.

Provider selection (checked in this order):
  1. ANTHROPIC_API_KEY set -> Claude (native tool-use, prompt caching).
  2. GROQ_API_KEY set -> Groq, via its OpenAI-compatible endpoint. This is
     the provider actually available in this project's .env today — the
     original project plan's own docs describe "Groq + Twilio + ReAct loop,"
     and no ANTHROPIC_API_KEY has ever been configured. Anthropic support is
     kept as a drop-in upgrade path (uncomment in requirements.txt "when
     client has paid" — see that file's comment), not the assumed default.
  3. Neither set -> is_available() returns False; callers degrade gracefully
     (see ai/whatsapp/orchestrator.py's fallback message).

Both providers are normalized to the same response shape in chat_with_tools()
so callers never need to know which one is active: response.stop_reason
("tool_use" | "end_turn"), response.content (list of blocks with .type in
{"text", "tool_use"}), response.model, response.usage.{input_tokens,output_tokens}.
This mirrors Anthropic's native shape since that was the first provider
implemented — Groq/OpenAI responses are translated into it, not the reverse.

Headroom (https://github.com/headroomlabs-ai/headroom) compression is
Anthropic-path-only for now (matches its current commented-out state in
requirements.txt — "uncomment when client has paid").
"""

import json
import os
from types import SimpleNamespace


def _block_get(block, key):
    """Read a field from a content block that may be a dict or an object
    (Anthropic SDK block or our normalized SimpleNamespace)."""
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
_HEADROOM_ENABLED = os.getenv("HEADROOM_ENABLED", "true").lower() == "true"
_HEADROOM_PROXY_URL = os.getenv("HEADROOM_PROXY_URL", "")
_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
_GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Bound every LLM call: without a timeout a slow/hung provider ties up the
# request (and, on a single gunicorn worker, starves all other traffic). Both
# the Anthropic and OpenAI SDKs retry transient errors idempotently with
# backoff, so a small max_retries is safe here (unlike a message send). Both are
# env-tunable.
_LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
_LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

_PROVIDER = "anthropic" if _ANTHROPIC_API_KEY else ("groq" if _GROQ_API_KEY else None)

# ── Model tiers ──────────────────────────────────────────────────────────────
# Callers pick a tier by task complexity; we resolve it to a concrete model for
# whichever provider is active. This is the main cost lever: cheap models do the
# routine narration (a dashboard refresh fires a handful of LOW calls), and the
# expensive model is reserved for genuine cross-domain strategy (HIGH). Every
# entry is env-overridable so the mapping can be tuned per deployment without a
# code change. The whole table auto-upgrades from Groq to Claude the moment an
# ANTHROPIC_API_KEY is set — no caller changes needed (see module docstring).
TIER_LOW, TIER_MEDIUM, TIER_HIGH = "low", "medium", "high"

_MODEL_TIERS = {
    "anthropic": {
        TIER_LOW:    os.getenv("ANTHROPIC_MODEL_LOW",    "claude-haiku-4-5-20251001"),
        TIER_MEDIUM: os.getenv("ANTHROPIC_MODEL_MEDIUM", _ANTHROPIC_MODEL),
        TIER_HIGH:   os.getenv("ANTHROPIC_MODEL_HIGH",   "claude-opus-4-8"),
    },
    "groq": {
        # Groq has no equivalent to a big frontier model, so MEDIUM/HIGH both
        # map to the largest configured model; only LOW drops to a smaller,
        # faster one. When ANTHROPIC_API_KEY is added this table stops being
        # used at all — the anthropic row above takes over.
        TIER_LOW:    os.getenv("GROQ_MODEL_LOW",    "llama-3.1-8b-instant"),
        TIER_MEDIUM: os.getenv("GROQ_MODEL_MEDIUM", _GROQ_MODEL),
        TIER_HIGH:   os.getenv("GROQ_MODEL_HIGH",   _GROQ_MODEL),
    },
}


def model_for_tier(tier: str | None) -> str | None:
    """
    Resolve a complexity tier ("low"|"medium"|"high") to a concrete model id for
    the active provider. Returns None if no provider is configured or no tier is
    given (callers then fall back to the provider default). Unknown tier names
    fall back to MEDIUM rather than erroring.
    """
    if _PROVIDER is None or tier is None:
        return None
    tiers = _MODEL_TIERS.get(_PROVIDER, {})
    return tiers.get(tier, tiers.get(TIER_MEDIUM))


_client = None


def is_available() -> bool:
    """Check if any LLM provider is configured (used to feature-gate callers)."""
    return _PROVIDER is not None


def _get_client():
    global _client
    if _client is not None:
        return _client

    if _PROVIDER == "anthropic":
        import anthropic
        kwargs = {
            "api_key": _ANTHROPIC_API_KEY,
            "timeout": _LLM_TIMEOUT,
            "max_retries": _LLM_MAX_RETRIES,
        }
        if _HEADROOM_ENABLED and _HEADROOM_PROXY_URL:
            # Proxy mode: Headroom sits between us and Anthropic, compressing
            # request bodies in transit. No other code changes required.
            kwargs["base_url"] = _HEADROOM_PROXY_URL
        _client = anthropic.Anthropic(**kwargs)
    elif _PROVIDER == "groq":
        # Groq exposes an OpenAI-compatible endpoint — reuse the openai SDK
        # rather than adding a second HTTP client dependency.
        from openai import OpenAI
        _client = OpenAI(
            api_key=_GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            timeout=_LLM_TIMEOUT,
            max_retries=_LLM_MAX_RETRIES,
        )
    else:
        raise RuntimeError(
            "No LLM provider configured — set ANTHROPIC_API_KEY or GROQ_API_KEY "
            "in backend/.env to enable LLM features."
        )

    return _client


def _compress_if_library_mode(messages: list[dict]) -> list[dict]:
    """Library-mode compression (Anthropic path only): used only when no proxy URL is configured."""
    if _PROVIDER != "anthropic" or not _HEADROOM_ENABLED or _HEADROOM_PROXY_URL:
        return messages
    try:
        from headroom import compress
    except ImportError:
        return messages
    return [
        {**m, "content": compress(m["content"]) if isinstance(m["content"], str) else m["content"]}
        for m in messages
    ]


def chat_with_usage(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 1024,
    model: str | None = None,
    tier: str | None = None,
    temperature: float | None = None,
):
    """
    Send a chat completion and return BOTH the reply text and token usage,
    normalized across providers as
    SimpleNamespace(text, model, usage.{input_tokens, output_tokens}).

    Model selection precedence: explicit `model` > `tier` lookup > provider
    default. `temperature` is passed through when set (the reasoning layer uses
    0 for the most deterministic, least-embellished output). Used by the
    reasoning layer, which needs usage back for per-tenant cost metering
    (ai/reasoning/narrator.py).
    """
    client = _get_client()
    resolved = model or model_for_tier(tier)

    if _PROVIDER == "anthropic":
        messages = _compress_if_library_mode(messages)
        kwargs = {
            "model": resolved or _ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        response = client.messages.create(**kwargs)
        text = "".join(block.text for block in response.content if block.type == "text")
        return SimpleNamespace(
            text=text,
            model=response.model,
            usage=SimpleNamespace(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )

    # Groq / OpenAI-compatible
    openai_messages = ([{"role": "system", "content": system}] if system else []) + messages
    kwargs = {
        "model": resolved or _GROQ_MODEL,
        "max_tokens": max_tokens,
        "messages": openai_messages,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    response = client.chat.completions.create(**kwargs)
    return SimpleNamespace(
        text=response.choices[0].message.content or "",
        model=response.model,
        usage=SimpleNamespace(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        ),
    )


def chat(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 1024,
    model: str | None = None,
    tier: str | None = None,
    temperature: float | None = None,
) -> str:
    """
    Send a chat completion through the active provider; returns the reply text.

    messages: [{"role": "user"|"assistant", "content": "..."}]
    Thin wrapper over chat_with_usage() for callers that don't need token counts.
    """
    return chat_with_usage(messages, system, max_tokens, model, tier, temperature).text


def _tools_to_openai_format(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _canonical_messages_to_openai(messages: list[dict]) -> list[dict]:
    """
    Translate the Anthropic-shaped canonical message history (used throughout
    ai/whatsapp/orchestrator.py) into OpenAI/Groq's format. Runs fresh on every
    call since the canonical history accumulates Anthropic-shaped turns
    regardless of which provider is actually active.
    """
    openai_messages = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            openai_messages.append({"role": m["role"], "content": content})
            continue

        # content is a list of Anthropic-style blocks (text / tool_use / tool_result)
        if m["role"] == "assistant":
            text_parts = [_block_get(b, "text") for b in content if _block_get(b, "type") == "text"]
            tool_calls = []
            for b in content:
                if _block_get(b, "type") != "tool_use":
                    continue
                # Preserve the actual arguments the model chose — the tool_use
                # block's `input` (a dict) — instead of dropping them. Harmless
                # for today's zero-arg tools, but correct the moment a tool
                # takes an argument on a multi-turn Groq conversation.
                tool_input = _block_get(b, "input") or {}
                tool_calls.append({
                    "id": _block_get(b, "id"),
                    "type": "function",
                    "function": {
                        "name": _block_get(b, "name"),
                        "arguments": json.dumps(tool_input),
                    },
                })
            msg = {"role": "assistant", "content": " ".join(p for p in text_parts if p) or None}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            openai_messages.append(msg)
        else:
            # user-role tool_result blocks -> one "tool" message per result
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": b["tool_use_id"],
                        "content": b["content"],
                    })
    return openai_messages


def chat_with_tools(
    messages: list[dict],
    tools: list[dict],
    system: str = "",
    max_tokens: int = 1024,
    model: str | None = None,
    tier: str | None = None,
):
    """
    One turn of a tool-calling loop. Returns a response normalized to
    Anthropic's shape regardless of active provider — see module docstring.
    Model selection precedence: explicit `model` > `tier` lookup > default.
    """
    client = _get_client()
    resolved = model or model_for_tier(tier)

    if _PROVIDER == "anthropic":
        messages = _compress_if_library_mode(messages)
        cached_tools = [dict(t) for t in tools]
        if cached_tools:
            cached_tools[-1]["cache_control"] = {"type": "ephemeral"}
        system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if system else []

        kwargs = {
            "model": resolved or _ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": messages,
        }
        # Mirror the Groq branch: omit `tools` entirely for a no-tools turn
        # rather than sending an empty array, for the same reason.
        if cached_tools:
            kwargs["tools"] = cached_tools
        return client.messages.create(**kwargs)

    # Groq / OpenAI-compatible — translate request and response at the boundary
    # so ai/whatsapp/orchestrator.py's loop logic stays provider-agnostic.
    openai_messages = ([{"role": "system", "content": system}] if system else []) + _canonical_messages_to_openai(messages)
    kwargs = {
        "model": resolved or _GROQ_MODEL,
        "max_tokens": max_tokens,
        "messages": openai_messages,
    }
    # Some OpenAI-compatible APIs reject an explicit empty `tools` array (400
    # "must not be empty") rather than treating it the same as omitting the
    # param. Omit it entirely for a no-tools turn (e.g. forcing a strategist
    # loop to conclude) so callers can safely pass tools=[] regardless of
    # provider quirks.
    if tools:
        kwargs["tools"] = _tools_to_openai_format(tools)
    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]

    content = []
    if choice.message.content:
        content.append(SimpleNamespace(type="text", text=choice.message.content))
    for tc in (choice.message.tool_calls or []):
        content.append(SimpleNamespace(
            type="tool_use",
            id=tc.id,
            name=tc.function.name,
            input=json.loads(tc.function.arguments or "{}"),
        ))

    stop_reason = "tool_use" if choice.message.tool_calls else "end_turn"
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        model=response.model,
        usage=SimpleNamespace(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        ),
    )
