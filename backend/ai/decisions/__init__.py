"""
backend/ai/decisions/
────────────────────────
Decision Intelligence layer. Turns every agent's recommendations into one
ranked, explainable stream of `Decision`s — the shared currency the dashboard
and the CEO/Strategy agent both consume.

Deterministic and additive: no LLM here (narration is attached at the route,
same as every other analytics endpoint), and it only reshapes numbers the agents
already computed — it never recomputes or invents them.
"""

from sqlalchemy.orm import Session

from .model import Decision  # noqa: F401
from .ranking import rank, score, impact_stars  # noqa: F401
from .adapters import collect_decisions  # noqa: F401


def get_ranked_decisions(
    db: Session, restaurant_id: int, sources: list[str] | None = None,
    apply_reliability: bool = True,
) -> dict:
    """
    The full Decision Intelligence payload for one restaurant: every agent's
    recommendations, normalized and ranked best-first, with a headline summary.

    When `apply_reliability` is on (default), each decision's confidence is scaled
    by its source agent's recent forecast reliability (Phase 9 feedback loop), so
    an agent that has been getting it wrong is trusted less in the ranking. Agents
    with no track record keep full confidence — it is a no-op for a new
    restaurant, which is why it never disturbs the deterministic baseline.
    """
    decisions = collect_decisions(db, restaurant_id, sources=sources)
    # Marketplace plugins (Phase 11) contribute to the same ranked stream. Empty
    # by default (no plugins registered) → no effect on the core baseline.
    try:
        from ai.plugins import collect_plugin_decisions
        decisions.extend(collect_plugin_decisions(db, restaurant_id))
    except Exception:  # noqa: BLE001 — a plugin issue never breaks core decisions
        pass
    if apply_reliability:
        _apply_reliability(db, restaurant_id, decisions)
    ranked = rank(decisions)

    quantified = [d for d in ranked if d.get("quantified")]
    total_impact = sum(d["impact_cents_month"] or 0 for d in quantified)

    return {
        "summary": {
            "total_decisions": len(ranked),
            "quantified_decisions": len(quantified),
            "total_monthly_impact_cents": total_impact,
            "top_action": ranked[0]["action"] if ranked else None,
            "by_category": _count_by(ranked, "category"),
        },
        "decisions": ranked,
    }


def _apply_reliability(db: Session, restaurant_id: int, decisions: list) -> None:
    """Scale each decision's confidence by its agent's recent reliability. Cached
    per agent so we compute each agent's accuracy once. Fails safe: any error
    leaves confidences untouched."""
    try:
        from ai.evaluation.feedback import agent_reliability
    except Exception:  # noqa: BLE001
        return
    cache: dict[str, float] = {}
    for d in decisions:
        mult = cache.get(d.agent)
        if mult is None:
            try:
                mult = agent_reliability(db, restaurant_id, d.agent)
            except Exception:  # noqa: BLE001
                mult = 1.0
            cache[d.agent] = mult
        if mult < 1.0:
            d.confidence_pct = int(round(d.confidence_pct * mult))
            d.meta["reliability_multiplier"] = mult


def _count_by(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r.get(key, "other")] = out.get(r.get(key, "other"), 0) + 1
    return out
