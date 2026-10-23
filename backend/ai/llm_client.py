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
  3. Neither set -> is_available() returns False; callers say AI is unavailable
     rather than substituting a canned paragraph.

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
import logging
import os
from types import SimpleNamespace

logger = logging.getLogger("ai.llm_client")


def _block_get(block, key):
    """Read a field from a content block that may be a dict or an object
    (Anthropic SDK block or our normalized SimpleNamespace)."""
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# OpenRouter is the owner's chat/report gateway and takes priority over Anthropic/Groq.
# Defaults are paid-routing flash models. Do not default to ":free" models: some of
# those providers train on prompts. data_collection is denied on every OpenRouter call.
_OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
_DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-v4-flash"
_OPENROUTER_FALLBACK_MODEL = os.getenv("OPENROUTER_FALLBACK_MODEL", "qwen/qwen3.7-flash")
_OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", _DEFAULT_OPENROUTER_MODEL)
_OPENROUTER_MODEL_LOW = os.getenv("OPENROUTER_MODEL_LOW", _DEFAULT_OPENROUTER_MODEL)
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

_PROVIDER = ("openrouter" if _OPENROUTER_API_KEY
             else "anthropic" if _ANTHROPIC_API_KEY
             else "groq" if _GROQ_API_KEY
             else None)

# ── Model tiers ──────────────────────────────────────────────────────────────
# Callers pick a tier by task complexity; we resolve it to a concrete model for
# whichever provider is active. This is the main cost lever: cheap models do the
# routine narration (a dashboard refresh fires a handful of LOW calls), and the
# expensive model is reserved for genuine cross-domain strategy (HIGH). Every
# entry is env-overridable so the mapping can be tuned per deployment without a
# code change. The whole table auto-upgrades from Groq to Claude the moment an
# ANTHROPIC_API_KEY is set — no caller changes needed (see module docstring).
TIER_LOW, TIER_MEDIUM, TIER_HIGH = "low", "medium", "high"
# The creative (stochastic) layer's own tier (ADR 0007): defaults to the medium
# model on every provider so nothing changes until an operator points
# *_MODEL_CREATIVE at a model chosen for voice rather than for cost.
TIER_CREATIVE = "creative"

_MODEL_TIERS = {
    "openrouter": {
        TIER_LOW:    _OPENROUTER_MODEL_LOW,
        TIER_MEDIUM: _OPENROUTER_MODEL,
        TIER_HIGH:   os.getenv("OPENROUTER_MODEL_HIGH", _OPENROUTER_MODEL),
        TIER_CREATIVE: os.getenv("OPENROUTER_MODEL_CREATIVE", _OPENROUTER_MODEL),
    },
    "anthropic": {
        TIER_LOW:    os.getenv("ANTHROPIC_MODEL_LOW",    "claude-haiku-4-5-20251001"),
        TIER_MEDIUM: os.getenv("ANTHROPIC_MODEL_MEDIUM", _ANTHROPIC_MODEL),
        TIER_HIGH:   os.getenv("ANTHROPIC_MODEL_HIGH",   "claude-opus-4-8"),
        TIER_CREATIVE: os.getenv("ANTHROPIC_MODEL_CREATIVE", os.getenv("ANTHROPIC_MODEL_MEDIUM", _ANTHROPIC_MODEL)),
    },
    "groq": {
        # Groq has no equivalent to a big frontier model, so MEDIUM/HIGH both
        # map to the largest configured model; only LOW drops to a smaller,
        # faster one. When ANTHROPIC_API_KEY is added this table stops being
        # used at all — the anthropic row above takes over.
        # LOW default updated 2026-08-22: llama-3.1-8b-instant was decommissioned
        # by Groq (404 model_not_found on every call — all narration silently
        # failed); gpt-oss-20b is the current small/fast tier (verified live).
        TIER_LOW:    os.getenv("GROQ_MODEL_LOW",    "openai/gpt-oss-20b"),
        TIER_MEDIUM: os.getenv("GROQ_MODEL_MEDIUM", _GROQ_MODEL),
        TIER_HIGH:   os.getenv("GROQ_MODEL_HIGH",   _GROQ_MODEL),
        TIER_CREATIVE: os.getenv("GROQ_MODEL_CREATIVE", os.getenv("GROQ_MODEL_MEDIUM", _GROQ_MODEL)),
    },
}


def _default_model() -> str:
    """The active provider's default model for the OpenAI-compatible branches,
    used when a caller passes neither an explicit `model` nor a `tier`.

    Must be provider-aware: Groq and OpenRouter have different id namespaces, so
    the previous unconditional `_GROQ_MODEL` fallback sent "openai/gpt-oss-120b"
    to OpenRouter (404). Reachable today via ai/whatsapp/orchestrator.py, which
    calls chat_with_tools() with neither argument."""
    return _OPENROUTER_MODEL if _PROVIDER == "openrouter" else _GROQ_MODEL


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


def _report_llm_failure(message: str, exc: BaseException | None = None) -> None:
    """Log an LLM failure and send it to Sentry when the SDK is configured.

    capture_exception is a no-op until sentry_sdk.init has run, so tests and
    local runs without a DSN still get the warning.
    """
    logger.warning("%s", message)
    try:
        import sentry_sdk
        if exc is not None:
            sentry_sdk.capture_exception(exc)
        else:
            sentry_sdk.capture_message(message)
    except Exception:
        logger.debug("sentry capture skipped", exc_info=True)


class LLMNoAnswer(RuntimeError):
    """The provider spent the call and returned no answer. Not an empty reply."""


def _reasoning_enabled() -> bool | None:
    """OpenRouter reasoning switch. Unset matches OPENROUTER_REASONING=off.

    deepseek/deepseek-v4-flash reasons by default and can spend max_tokens on
    that trace, returning content=null and finish_reason=length. Off sends
    reasoning.enabled=false. on/true turns it on. any other value omits the field.
    """
    raw = os.getenv("OPENROUTER_REASONING", "off").strip().lower()
    if raw in {"off", "false", "0", "disabled", "no"}:
        return False
    if raw in {"on", "true", "1", "enabled", "yes"}:
        return True
    return None


def _openrouter_extra(extra_body: dict | None, model: str) -> dict:
    """OpenRouter request extras: deny prompt training, skip reasoning, name a fallback."""
    body = dict(extra_body or {})
    provider = dict(body.get("provider") or {})
    provider["data_collection"] = "deny"
    body["provider"] = provider
    if "reasoning" not in body:
        enabled = _reasoning_enabled()
        if enabled is not None:
            body["reasoning"] = {"enabled": enabled}
    chain: list[str] = []
    for name in (model, *(body.get("models") or []), _OPENROUTER_FALLBACK_MODEL):
        if name and name not in chain:
            chain.append(name)
    if len(chain) > 1:
        body["models"] = chain
    return body


def _budget_spent_without_answer(text: str, finish_reason: str | None, tool_calls=None) -> bool:
    """content is null and the token budget was used up. That is a failed call, not a blank answer."""
    return not (text or "").strip() and not tool_calls and finish_reason == "length"


def _get_client():
    global _client
    if _client is not None:
        return _client

    if _PROVIDER == "openrouter":
        from openai import OpenAI
        _client = OpenAI(
            api_key=_OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            timeout=_LLM_TIMEOUT,
            max_retries=_LLM_MAX_RETRIES,
            default_headers={
                # OpenRouter attribution headers (recommended by their docs).
                "HTTP-Referer": "https://leviii.restaurant-os.app",
                "X-Title": "LEVIII Restaurant Manager",
            },
        )
    elif _PROVIDER == "anthropic":
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
    extra_body: dict | None = None,
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

        def _anthropic_once():
            response = client.messages.create(**kwargs)
            text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
            return response, text

        try:
            response, text = _anthropic_once()
        except Exception as exc:
            _report_llm_failure(f"Anthropic chat failed: {exc}", exc)
            raise
        if not text.strip():
            _report_llm_failure("Anthropic returned empty content; retrying once")
            try:
                response, text = _anthropic_once()
            except Exception as exc:
                _report_llm_failure(f"Anthropic empty-content retry failed: {exc}", exc)
                raise
            if not text.strip():
                _report_llm_failure("Anthropic returned empty content after one retry")
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
    resolved_model = resolved or _default_model()
    kwargs = {
        "model": resolved_model,
        "max_tokens": max_tokens,
        "messages": openai_messages,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if _PROVIDER == "openrouter":
        kwargs["extra_body"] = _openrouter_extra(extra_body, resolved_model)
    elif extra_body:
        # Provider-specific request fields. Only sent when asked for.
        kwargs["extra_body"] = extra_body

    def _openai_once():
        response = client.chat.completions.create(**kwargs)
        text = ""
        finish_reason = None
        tool_calls = None
        if response.choices:
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            message = choice.message
            if message is not None:
                text = message.content or ""
                tool_calls = getattr(message, "tool_calls", None)
        return response, text, finish_reason, tool_calls

    try:
        response, text, finish_reason, tool_calls = _openai_once()
    except Exception as exc:
        _report_llm_failure(f"LLM chat failed: {exc}", exc)
        raise
    if _budget_spent_without_answer(text, finish_reason, tool_calls):
        _report_llm_failure(
            "LLM returned content=null with finish_reason=length; the token budget was spent before an answer. Retrying once"
        )
        try:
            response, text, finish_reason, tool_calls = _openai_once()
        except Exception as exc:
            _report_llm_failure(f"LLM length-cutoff retry failed: {exc}", exc)
            raise
        if _budget_spent_without_answer(text, finish_reason, tool_calls):
            _report_llm_failure("LLM returned content=null with finish_reason=length after one retry")
            raise LLMNoAnswer("LLM returned no answer (finish_reason=length, content is null)")
    elif not text.strip():
        _report_llm_failure("LLM returned empty content; retrying once")
        try:
            response, text, finish_reason, tool_calls = _openai_once()
        except Exception as exc:
            _report_llm_failure(f"LLM empty-content retry failed: {exc}", exc)
            raise
        if _budget_spent_without_answer(text, finish_reason, tool_calls):
            _report_llm_failure("LLM returned content=null with finish_reason=length after one retry")
            raise LLMNoAnswer("LLM returned no answer (finish_reason=length, content is null)")
        if not text.strip():
            _report_llm_failure("LLM returned empty content after one retry")
    return SimpleNamespace(
        text=text or "",
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
    temperature: float | None = None,
):
    """
    One turn of a tool-calling loop. Returns a response normalized to
    Anthropic's shape regardless of active provider — see module docstring.
    Model selection precedence: explicit `model` > `tier` lookup > default.
    `temperature` is sent only when the caller sets it (the insight loop).
    Other callers keep the provider default.
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
        if temperature is not None:
            kwargs["temperature"] = temperature
        # Mirror the Groq branch: omit `tools` entirely for a no-tools turn
        # rather than sending an empty array, for the same reason.
        if cached_tools:
            kwargs["tools"] = cached_tools
        return client.messages.create(**kwargs)

    # Groq / OpenAI-compatible — translate request and response at the boundary
    # so ai/whatsapp/orchestrator.py's loop logic stays provider-agnostic.
    openai_messages = ([{"role": "system", "content": system}] if system else []) + _canonical_messages_to_openai(messages)
    kwargs = {
        "model": resolved or _default_model(),
        "max_tokens": max_tokens,
        "messages": openai_messages,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    # Some OpenAI-compatible APIs reject an explicit empty `tools` array (400
    # "must not be empty") rather than treating it the same as omitting the
    # param. Omit it entirely for a no-tools turn (e.g. forcing a strategist
    # loop to conclude) so callers can safely pass tools=[] regardless of
    # provider quirks.
    if tools:
        kwargs["tools"] = _tools_to_openai_format(tools)
    if _PROVIDER == "openrouter":
        kwargs["extra_body"] = _openrouter_extra(None, kwargs["model"])

    def _create():
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            _report_llm_failure(f"LLM tool call failed: {exc}", exc)
            raise

    response = _create()
    choice = response.choices[0]
    if _budget_spent_without_answer(
        choice.message.content or "",
        getattr(choice, "finish_reason", None),
        choice.message.tool_calls,
    ):
        _report_llm_failure(
            "LLM tool call returned content=null with finish_reason=length. Retrying once"
        )
        response = _create()
        choice = response.choices[0]
        if _budget_spent_without_answer(
            choice.message.content or "",
            getattr(choice, "finish_reason", None),
            choice.message.tool_calls,
        ):
            _report_llm_failure("LLM tool call returned content=null with finish_reason=length after one retry")
            raise LLMNoAnswer("LLM returned no answer (finish_reason=length, content is null)")

    content = []
    if choice.message.content:
        content.append(SimpleNamespace(type="text", text=choice.message.content))
    for tc in (choice.message.tool_calls or []):
        # Small models occasionally emit malformed tool-argument JSON — one
        # bad call must not crash the whole multi-turn run after its tokens
        # were already spent. Empty args degrade to "no arguments".
        try:
            tool_input = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            logger.warning(
                "malformed tool arguments from model for tool %r — treated as empty",
                getattr(tc.function, "name", "?"),
            )
            tool_input = {}
        content.append(SimpleNamespace(
            type="tool_use",
            id=tc.id,
            name=tc.function.name,
            input=tool_input,
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
