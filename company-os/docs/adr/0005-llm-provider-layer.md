# ADR 0005 — Provider-neutral LLM layer; Anthropic via official SDK

**Status:** Accepted, 2026-09-26

## Decision
- The runtime depends only on the `Conversation` interface in `app/kernel/agents/llm.py`.
- Provider order is the same as restaurant-agent: OpenRouter, then Anthropic, then Groq. The first provider with a key set wins.
- **Anthropic** calls go through the official `anthropic` SDK. Every tier defaults to `claude-opus-5`, and tiers map to `output_config.effort` (low / medium / high), which is the documented cost lever. Moving to a cheaper model is a founder decision, made via `ANTHROPIC_MODEL_<TIER>`. Server-side `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) is on. `stop_reason: "refusal"` is handled before content is read. The full assistant content, including thinking blocks, is replayed unchanged between turns.
- **OpenRouter and Groq** are OpenAI-compatible and called with `httpx`.
- **Cost:** Anthropic list prices come from the Claude API reference. `:free` models cost 0. Unknown models are charged at a conservative $5/$25 per million tokens, so the daily cap errs toward stopping. Prices can be overridden with `MODEL_PRICES_JSON`.
- **Daily cap:** `DAILY_LLM_SPEND_CAP_USD` (default $5) per workspace. Runs stop with status `spend_capped`.
- **No key set:** LLM agents report `llm_unavailable`, or run their deterministic fallback when they have one.

## Consequences
- No provider lock-in, and no SDK in the OpenAI-compatible path.
- Groq model prices are not in the table, so they bill at the conservative default until `MODEL_PRICES_JSON` is set.
