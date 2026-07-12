"""
backend/ai/decisions/model.py
───────────────────────────────
The `Decision` — a first-class, rankable, explainable unit of advice that every
agent can emit and the CEO/Strategy agent + dashboard consume as one currency.

Why this exists: today each agent (pricing, inventory, supply-chain, labor,
marketing, menu) returns its own differently-shaped "recommendations" list.
Nothing can rank a pricing SURGE against a reorder alert against a win-back
campaign, because they don't share a schema. `Decision` is that shared schema.

Hard rule carried from directives/012_agentic_roadmap.md: this layer NEVER
invents numbers. `impact_cents_month` is only set when the source agent actually
computed a monetary figure; otherwise it stays None ("not quantified") and the
ranking treats it as unquantified rather than fabricating a value. Same for
confidence — it is derived from signals the agent already produced
(recommendation_strength, priority, sample size), never guessed.

All money is integer cents, consistent with the rest of the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# Risk / difficulty are 1..5 ordinal scales, kept explicit (not hidden in a
# formula) so the assumption behind each agent's mapping is auditable.
#   risk       1 = very safe to do          … 5 = could backfire badly
#   difficulty 1 = one click / no effort    … 5 = major operational change
RISK_MIN, RISK_MAX = 1, 5
DIFFICULTY_MIN, DIFFICULTY_MAX = 1, 5


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


@dataclass
class Decision:
    """One actionable recommendation, normalized across every agent."""

    agent: str                       # "pricing_intelligence", "supply_chain", …
    category: str                    # "pricing" | "inventory" | "marketing" | …
    action: str                      # short imperative: "Raise Chicken Burger to KES 650"
    rationale: str                   # plain-language WHY (grounded in real numbers)

    confidence_pct: int              # 0..100, derived from the agent's own signals
    risk: int                        # 1..5 (see scale above)
    difficulty: int                  # 1..5 (see scale above)

    # None = the source agent did not quantify a monetary impact. Never faked.
    impact_cents_month: Optional[int] = None

    data_sources: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)

    # Traceability back to the originating row / entity, when one exists.
    recommendation_id: Optional[int] = None
    entity_type: Optional[str] = None     # "menu_item", "inventory_item", "supplier"
    entity_id: Optional[int] = None

    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.confidence_pct = _clamp(self.confidence_pct, 0, 100)
        self.risk = _clamp(self.risk, RISK_MIN, RISK_MAX)
        self.difficulty = _clamp(self.difficulty, DIFFICULTY_MIN, DIFFICULTY_MAX)
        if self.impact_cents_month is not None:
            self.impact_cents_month = int(self.impact_cents_month)

    @property
    def quantified(self) -> bool:
        """True when the source agent produced a real monetary impact figure."""
        return self.impact_cents_month is not None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quantified"] = self.quantified
        # UI-friendly ordinal stars. Risk/ease are shown as 5-star meters:
        #   ease_stars = 6 - difficulty  (easy things get MORE stars — good)
        #   risk_stars = risk            (risky things get MORE stars — bad)
        d["risk_stars"] = self.risk
        d["ease_stars"] = 6 - self.difficulty
        return d
