"""
backend/ai/cost_model.py
──────────────────────────
Money conversion for LLM token usage (Phase 5). TokenUsage records token COUNTS;
this turns them into dollars (and approximate KES) so the AI-Ops view can show
"today's AI cost" and, alongside roi/savings, cost-vs-profit-generated.

Prices are public list prices per 1,000,000 tokens, USD, and are DELIBERATELY a
static table here (not a live billing API) — they change rarely and an owner
wants a stable estimate, not a to-the-cent invoice. Every entry is documented and
env-overridable. Model ids are matched by substring so a provider-returned id
("openai/gpt-oss-120b", "claude-haiku-4-5-20251001", "llama-3.1-8b-instant")
resolves without an exact-string table.

Honest about scope: this is an ESTIMATE. Unknown models fall back to a
conservative default rather than reporting zero (which would understate spend).
"""

from __future__ import annotations

import os

# (input_usd_per_mtok, output_usd_per_mtok). Substring-matched against the model
# id, longest match wins. Approximate public list prices.
_PRICE_PER_MTOK: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus":   (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku":  (1.0, 5.0),
    # Groq (OpenAI-compatible) — inference-optimized, cheap
    "gpt-oss-120b":  (0.15, 0.60),
    "llama-3.3-70b": (0.59, 0.79),
    "llama-3.1-8b":  (0.05, 0.08),
    "llama-3.1-70b": (0.59, 0.79),
}

# Conservative fallback for an unrecognized model (better to slightly over- than
# under-estimate spend). Tunable.
_DEFAULT_PRICE = (
    float(os.getenv("LLM_DEFAULT_INPUT_USD_PER_MTOK", "1.0")),
    float(os.getenv("LLM_DEFAULT_OUTPUT_USD_PER_MTOK", "3.0")),
)

# USD→KES for the approximate local-currency view. Env-tunable; rates move.
USD_TO_KES = float(os.getenv("USD_TO_KES", "129.0"))


def _price_for(model: str | None) -> tuple[float, float]:
    if not model:
        return _DEFAULT_PRICE
    m = model.lower()
    best: tuple[str, tuple[float, float]] | None = None
    for key, price in _PRICE_PER_MTOK.items():
        if key in m and (best is None or len(key) > len(best[0])):
            best = (key, price)
    return best[1] if best else _DEFAULT_PRICE


def cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    """USD cost of one call (or aggregate) at list prices for `model`."""
    in_tok = max(0, input_tokens)
    out_tok = max(0, output_tokens)
    in_price, out_price = _price_for(model)
    return (in_tok / 1_000_000) * in_price + (out_tok / 1_000_000) * out_price


def cost_kes_cents(model: str | None, input_tokens: int, output_tokens: int) -> int:
    """Approximate cost in KES cents (integer, to match the money convention)."""
    return int(round(cost_usd(model, input_tokens, output_tokens) * USD_TO_KES * 100))