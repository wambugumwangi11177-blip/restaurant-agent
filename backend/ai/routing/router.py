"""
backend/ai/routing/router.py
──────────────────────────────
The routing policy. Given a task (or an explicit set of capability NEEDs), decide
which engine should serve it:

  • forecast / deterministic work  → NO LLM ("engine") — the cheapest routing
    decision there is, and the one the essay's own diagram ends on. Numbers come
    from the deterministic modules; spending an LLM token on them is pure waste.
  • deep reasoning (strategy)      → HIGH tier (Claude Opus when configured).
  • realtime / cheap (narration,
    intent classification)         → LOW tier (fast, cheap model).
  • vision                         → MEDIUM tier + a vision-capable provider.

This sits ON TOP of llm_client's existing tier→model resolution (which already
auto-upgrades Groq→Claude the moment an ANTHROPIC_API_KEY is set), so the router
adds the *policy* (need → tier + preferred provider) without duplicating model
tables. When only one provider is configured, the preferred provider is a hint
recorded for cost attribution; the active provider still serves the call.

Deterministic and side-effect-free — a pure decision function, easy to test and
to log for the Phase 5 cost view.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai import llm_client
from ai.llm_client import TIER_LOW, TIER_MEDIUM, TIER_HIGH


class NEED(str, Enum):
    FORECAST = "forecast"       # deterministic — no LLM
    REASONING = "reasoning"     # cross-domain strategy
    REALTIME = "realtime"       # low latency, cheap
    VISION = "vision"           # image understanding
    CHEAP = "cheap"             # routine narration, classification


# need → (tier, preferred_provider, uses_llm)
_NEED_POLICY: dict[NEED, tuple[str | None, str | None, bool]] = {
    NEED.FORECAST:  (None, "engine", False),
    NEED.REASONING: (TIER_HIGH, "anthropic", True),
    NEED.VISION:    (TIER_MEDIUM, "openai", True),
    NEED.REALTIME:  (TIER_LOW, "groq", True),
    NEED.CHEAP:     (TIER_LOW, None, True),
}

# task name → the dominant capability it needs. New tasks slot in here.
_TASK_NEEDS: dict[str, NEED] = {
    "revenue_forecast": NEED.FORECAST,
    "twin": NEED.FORECAST,
    "simulation": NEED.FORECAST,
    "decisions_ranking": NEED.FORECAST,
    "strategy": NEED.REASONING,
    "narration": NEED.CHEAP,
    "explain": NEED.CHEAP,
    "intent_classification": NEED.REALTIME,
    "menu_photo": NEED.VISION,
}


@dataclass
class Route:
    use_llm: bool
    tier: str | None
    model: str | None            # resolved concrete model, or "engine" when no LLM
    preferred_provider: str | None
    active_provider: str | None
    reason: str

    def to_dict(self) -> dict:
        return {
            "use_llm": self.use_llm, "tier": self.tier, "model": self.model,
            "preferred_provider": self.preferred_provider,
            "active_provider": self.active_provider, "reason": self.reason,
        }


def choose_model(need: NEED | str) -> Route:
    """Resolve a single capability need to a concrete routing decision."""
    if isinstance(need, str):
        try:
            need = NEED(need)
        except ValueError:
            need = NEED.CHEAP   # unknown need → safe, cheap default
    tier, preferred, uses_llm = _NEED_POLICY[need]

    active = getattr(llm_client, "_PROVIDER", None)
    if not uses_llm:
        return Route(False, None, "engine", preferred, active,
                     f"{need.value}: deterministic — no LLM needed")

    model = llm_client.model_for_tier(tier)
    reason = f"{need.value}: {tier} tier"
    if preferred and active and preferred != active:
        reason += f" (prefers {preferred}, serving on {active})"
    return Route(True, tier, model, preferred, active, reason)


def route_task(task: str) -> Route:
    """Resolve a named task to a routing decision via its dominant capability."""
    need = _TASK_NEEDS.get(task, NEED.CHEAP)
    route = choose_model(need)
    route.reason = f"task '{task}' → " + route.reason
    return route
