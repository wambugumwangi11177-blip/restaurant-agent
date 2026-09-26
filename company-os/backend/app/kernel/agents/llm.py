"""
app/kernel/agents/llm.py
────────────────────────
Provider-neutral LLM conversation, adapted from restaurant-agent's
backend/ai/llm_client.py (same provider order, same graceful degradation).

Provider order (first key present wins): OpenRouter -> Anthropic -> Groq.
  - OpenRouter is the gateway the founder chose for restaurant-agent on
    2026-09-12; its default ":free" models were verified live there.
  - Anthropic goes through the official `anthropic` SDK. Every tier defaults
    to claude-opus-5 (per the Claude API reference; downgrading the model for
    cost is an owner decision — set ANTHROPIC_MODEL_<TIER> to do it). Tiers
    map to `effort` instead, which is the documented cost lever. Refusals are
    handled, with server-side `fallbacks: "default"` enabled.
  - OpenRouter and Groq are OpenAI-compatible and called with httpx.
No key set -> is_available() is False and LLM agents report `llm_unavailable`.

The runtime only sees the `Conversation` interface below, so which provider
is active never leaks into agent code.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import httpx

from app.config import get_settings

logger = logging.getLogger("kernel.llm")

TIER_LOW, TIER_MEDIUM, TIER_HIGH = "low", "medium", "high"


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict


@dataclass
class Turn:
    text: str
    tool_uses: list[ToolUse]
    stop_reason: str  # end_turn | tool_use | pause_turn | refusal | max_tokens | error
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    detail: str | None = None


class Conversation(Protocol):
    model: str

    def send(self) -> Turn: ...

    def add_tool_results(self, results: list[tuple[str, str, bool]]) -> None:
        """results: (tool_use_id, content, is_error), all in one message."""


class LLMError(RuntimeError):
    pass


# ── Model selection ──────────────────────────────────────────────────────────

def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def model_for(provider: str, tier: str) -> str:
    tier = tier if tier in (TIER_LOW, TIER_MEDIUM, TIER_HIGH) else TIER_MEDIUM
    if provider == "anthropic":
        return _env(f"ANTHROPIC_MODEL_{tier.upper()}", _env("ANTHROPIC_MODEL", "claude-opus-5"))
    if provider == "openrouter":
        big = _env("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
        small = _env("OPENROUTER_MODEL_LOW", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
        return small if tier == TIER_LOW else _env(f"OPENROUTER_MODEL_{tier.upper()}", big)
    if provider == "groq":
        big = _env("GROQ_MODEL", "openai/gpt-oss-120b")
        return _env("GROQ_MODEL_LOW", "openai/gpt-oss-20b") if tier == TIER_LOW else big
    raise LLMError(f"unknown provider {provider!r}")


def provider() -> str | None:
    return get_settings().llm_provider


def is_available() -> bool:
    return provider() is not None


# ── Cost model ───────────────────────────────────────────────────────────────
# USD per million tokens (input, output). Anthropic rates are first-party list
# prices from the Claude API reference (cached 2026-06-24). Any model not
# listed is charged at the conservative UNKNOWN rate so the daily spend cap
# errs toward stopping early, never toward overspending. Override or extend
# with MODEL_PRICES_JSON='{"model-id": [in, out], ...}'.
_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_UNKNOWN_PRICE = (5.0, 25.0)


def _prices() -> dict[str, tuple[float, float]]:
    extra = os.environ.get("MODEL_PRICES_JSON")
    if not extra:
        return _PRICES
    try:
        parsed = {k: (float(v[0]), float(v[1])) for k, v in json.loads(extra).items()}
    except (ValueError, TypeError, IndexError, AttributeError):
        logger.warning("MODEL_PRICES_JSON is not valid; ignoring it")
        return _PRICES
    return {**_PRICES, **parsed}


def cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> Decimal:
    if model and model.endswith(":free"):
        return Decimal("0")
    p_in, p_out = _prices().get(model or "", _UNKNOWN_PRICE)
    usd = (input_tokens * p_in + output_tokens * p_out) / 1_000_000
    return Decimal(str(round(usd, 6)))


# ── Anthropic (official SDK) ─────────────────────────────────────────────────

_EFFORT = {TIER_LOW: "low", TIER_MEDIUM: "medium", TIER_HIGH: "high"}


class AnthropicConversation:
    def __init__(self, system: str, user_text: str, tools: list[ToolSpec], tier: str):
        import anthropic

        s = get_settings()
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=s.llm_timeout_seconds, max_retries=2)
        self.model = model_for("anthropic", tier)
        self._effort = _EFFORT.get(tier, "medium")
        self._system = system
        self._tools = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
        self._messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]

    def send(self) -> Turn:
        a = self._anthropic
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=16000,
            system=self._system,
            messages=self._messages,
            output_config={"effort": self._effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if self._tools:
            kwargs["tools"] = self._tools
        try:
            resp = self._client.beta.messages.create(**kwargs)
        except a.RateLimitError as e:
            raise LLMError(f"rate limited by Anthropic: {e.message}") from e
        except a.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError(f"could not reach Anthropic: {e}") from e

        usage = resp.usage
        base = dict(model=resp.model, input_tokens=usage.input_tokens or 0, output_tokens=usage.output_tokens or 0)
        if resp.stop_reason == "refusal":
            category = getattr(getattr(resp, "stop_details", None), "category", None)
            return Turn(text="", tool_uses=[], stop_reason="refusal", detail=f"category={category}", **base)

        # Append the full content (incl. thinking blocks) so the next turn replays it unchanged.
        self._messages.append({"role": "assistant", "content": resp.content})
        text = "".join(b.text for b in resp.content if b.type == "text")
        uses = [ToolUse(id=b.id, name=b.name, input=dict(b.input or {})) for b in resp.content if b.type == "tool_use"]
        return Turn(text=text, tool_uses=uses, stop_reason=resp.stop_reason or "end_turn", **base)

    def add_tool_results(self, results: list[tuple[str, str, bool]]) -> None:
        self._messages.append({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": content, "is_error": is_error}
                for tid, content, is_error in results
            ],
        })


# ── OpenAI-compatible (OpenRouter, Groq) ─────────────────────────────────────

_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
}


@dataclass
class OpenAICompatConversation:
    provider_name: str
    system: str
    user_text: str
    tools: list[ToolSpec]
    tier: str
    model: str = ""
    _messages: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.model = model_for(self.provider_name, self.tier)
        self._messages = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": self.user_text},
        ]

    def _key(self) -> str:
        s = get_settings()
        return s.openrouter_api_key if self.provider_name == "openrouter" else s.groq_api_key

    def send(self) -> Turn:
        payload: dict[str, Any] = {"model": self.model, "messages": self._messages, "max_tokens": 4096}
        if self.tools:
            payload["tools"] = [
                {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}}
                for t in self.tools
            ]
        try:
            r = httpx.post(
                _BASE_URLS[self.provider_name],
                json=payload,
                headers={"Authorization": f"Bearer {self._key()}", "X-Title": "Company OS"},
                timeout=get_settings().llm_timeout_seconds,
            )
        except httpx.HTTPError as e:
            raise LLMError(f"could not reach {self.provider_name}: {e}") from e
        if r.status_code >= 400:
            raise LLMError(f"{self.provider_name} API error {r.status_code}: {r.text[:300]}")
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        usage = data.get("usage") or {}
        raw_calls = msg.get("tool_calls") or []
        uses: list[ToolUse] = []
        for call in raw_calls:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"__invalid_json__": fn.get("arguments")}
            uses.append(ToolUse(id=call.get("id", ""), name=fn.get("name", ""), input=args if isinstance(args, dict) else {}))
        assistant: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
        if raw_calls:
            assistant["tool_calls"] = raw_calls
        self._messages.append(assistant)
        finish = choice.get("finish_reason")
        stop = "tool_use" if uses else ("max_tokens" if finish == "length" else "end_turn")
        return Turn(
            text=msg.get("content") or "",
            tool_uses=uses,
            stop_reason=stop,
            model=data.get("model") or self.model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )

    def add_tool_results(self, results: list[tuple[str, str, bool]]) -> None:
        for tid, content, is_error in results:
            self._messages.append({"role": "tool", "tool_call_id": tid, "content": ("ERROR: " if is_error else "") + content})


def start_conversation(system: str, user_text: str, tools: list[ToolSpec], tier: str = TIER_MEDIUM) -> Conversation:
    p = provider()
    if p is None:
        raise LLMError("no LLM provider configured")
    if p == "anthropic":
        return AnthropicConversation(system, user_text, tools, tier)
    return OpenAICompatConversation(p, system, user_text, tools, tier)
