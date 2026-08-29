"""
backend/ai/decisions/ranking.py
─────────────────────────────────
Deterministic ranking of `Decision`s. No LLM, no randomness — the same set of
decisions always ranks the same way, so the "Best recommendation" the owner sees
is reproducible and defensible.

The score blends four signals the owner actually weighs when deciding what to do
first: how much money it moves, how sure we are, how risky it is, and how hard it
is to pull off. Weights are explicit and sum to 1, so the score is bounded in
[0,1] by construction (not by a clamp) and each component's influence is legible.

Impact is log-scaled against a reference of KES 100,000/month of monthly impact:
a linear scale would let one huge pricing number dwarf every operational fix,
whereas diminishing returns match how an owner reads "big / medium / small."
Unquantified decisions (impact_cents_month is None) contribute 0 to the impact
term rather than a fabricated value — they can still rank well on confidence,
low risk and low effort, but a quantified money-maker of equal footing outranks
them, which is the correct bias.
"""

from __future__ import annotations

import math

from .model import Decision, RISK_MAX, DIFFICULTY_MAX

# KES 100,000 per month, in cents. A decision at/above this reference scores ~1.0
# on the impact component; smaller impacts scale down with diminishing returns.
IMPACT_REFERENCE_CENTS = 100_000 * 100

# Weights sum to 1.0 → score is intrinsically bounded in [0, 1].
W_IMPACT = 0.45
W_CONFIDENCE = 0.25
W_RISK = 0.15
W_EASE = 0.15


def _norm_impact(impact_cents_month: int | None) -> float:
    """Map a monthly-impact figure to [0,1] on a log scale. None/≤0 → 0."""
    if not impact_cents_month or impact_cents_month <= 0:
        return 0.0
    return min(1.0, math.log1p(impact_cents_month) / math.log1p(IMPACT_REFERENCE_CENTS))


def _inverse_ordinal(value: int, max_value: int) -> float:
    """Map a 1..max ordinal to [1..0] — 1 (best) → 1.0, max (worst) → 0.0."""
    if max_value <= 1:
        # Only one possible value; treat it as the best (no penalty).
        return 1.0
    return 1.0 - (value - 1) / (max_value - 1)


def score(decision: Decision) -> float:
    """Composite desirability of a decision, in [0, 1]."""
    return (
        W_IMPACT * _norm_impact(decision.impact_cents_month)
        + W_CONFIDENCE * (decision.confidence_pct / 100.0)
        + W_RISK * _inverse_ordinal(decision.risk, RISK_MAX)
        + W_EASE * _inverse_ordinal(decision.difficulty, DIFFICULTY_MAX)
    )


def impact_stars(impact_cents_month: int | None) -> int:
    """1..5 star rating of monetary impact (0 for unquantified), for the UI."""
    if not impact_cents_month or impact_cents_month <= 0:
        return 0
    return max(1, min(5, round(_norm_impact(impact_cents_month) * 5)))


def rank(decisions: list[Decision]) -> list[dict]:
    """
    Rank decisions best-first and return UI-ready dicts.

    Each returned dict is `Decision.to_dict()` plus:
      priority_score : 0..100 int (the composite score, scaled)
      impact_stars   : 0..5
      rank           : 1-based position

    Ties break on raw monetary impact, then confidence — deterministic ordering
    so the list never reshuffles between identical inputs.
    """
    scored = [(score(d), d) for d in decisions]
    scored.sort(
        key=lambda pair: (
            pair[0],
            pair[1].impact_cents_month or 0,
            pair[1].confidence_pct,
        ),
        reverse=True,
    )

    out: list[dict] = []
    for i, (s, d) in enumerate(scored, start=1):
        row = d.to_dict()
        row["priority_score"] = round(s * 100)
        row["impact_stars"] = impact_stars(d.impact_cents_month)
        row["rank"] = i
        out.append(row)
    return out