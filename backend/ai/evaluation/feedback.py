"""
backend/ai/evaluation/feedback.py
───────────────────────────────────
The dedicated self-evaluation feedback loop (Phase 9). Where learning.py CLOSES
the predict→score cycle mechanically, this layer INTERPRETS the results: after a
prediction is scored, it classifies whether it worked and — when it didn't — why
(a calendar effect the baseline couldn't see, or genuine model error). It then
derives a per-agent reliability multiplier that the Decision Intelligence ranking
uses to down-weight agents that have been getting it wrong.

Every agent that records evaluable predictions participates; nothing is
recommended that isn't later scored and fed back here.

Deterministic. No LLM. Cross-references the same offline calendar signals the
Digital Twin uses (ai/simulation/signals.py) to explain misses honestly rather
than always blaming "the model."
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

import models
from time_utils import utcnow
from .tracker import get_agent_accuracy, write_audit_log

logger = logging.getLogger("ai.feedback")

# Reliability multiplier band. A perfectly-accurate agent keeps full weight;
# a poor one is trusted less in ranking, but never zeroed out (it may improve).
RELIABILITY_MIN = 0.6
RELIABILITY_FULL = 1.0


def agent_reliability(db: Session, restaurant_id: int, agent_name: str, days: int = 30) -> float:
    """
    A [RELIABILITY_MIN..1.0] multiplier from the agent's recent forecast accuracy.
    No evaluated history → full trust (1.0): we don't penalise an agent for lack
    of a track record, only for a demonstrably poor one.
    """
    acc = get_agent_accuracy(db, restaurant_id, agent_name, days=days)
    mae = acc.get("mae_pct")
    if not acc.get("prediction_count") or mae is None:
        return RELIABILITY_FULL
    # MAE 0% → 1.0; MAE 40%+ → floor. Linear in between.
    scaled = RELIABILITY_FULL - (mae / 40.0) * (RELIABILITY_FULL - RELIABILITY_MIN)
    return round(max(RELIABILITY_MIN, min(RELIABILITY_FULL, scaled)), 3)


def reliability_summary_text(db: Session, restaurant_id: int, days: int = 30) -> str:
    """
    Render agent_reliability() as text the strategist can actually read,
    instead of it staying a silent multiplier inside decision ranking. Empty
    string when there's no evaluated history yet — nothing to say.
    """
    cutoff = utcnow() - timedelta(days=days)
    agent_names = (
        db.query(models.AgentPrediction.agent_name)
        .filter(
            models.AgentPrediction.restaurant_id == restaurant_id,
            models.AgentPrediction.evaluated_at >= cutoff,
            models.AgentPrediction.actual_value.isnot(None),
        )
        .distinct()
        .all()
    )
    lines = []
    for (agent_name,) in agent_names:
        acc = get_agent_accuracy(db, restaurant_id, agent_name, days=days)
        mae = acc.get("mae_pct")
        if mae is None:
            continue
        reliability = agent_reliability(db, restaurant_id, agent_name, days=days)
        lines.append(f"{agent_name}: {mae:.0f}% avg error last {days}d (reliability {reliability:.2f}).")
    return "\n".join(lines)


def classify_prediction(db: Session, restaurant_id: int, pred: models.AgentPrediction) -> dict:
    """
    Classify one evaluated prediction: worked / acceptable / missed, and — when
    missed — a probable reason. A miss on a day that had a calendar signal
    (holiday, school break) is attributed to that exogenous effect rather than to
    the model, since a plain sales-history forecast can't see it.
    """
    if pred.actual_value is None or pred.error_pct is None:
        return {"prediction_id": pred.id, "verdict": "unscored"}

    if pred.within_ci:
        verdict, reason = "worked", "actual landed within the confidence interval"
    elif pred.error_pct <= 20:
        verdict, reason = "acceptable", f"within {pred.error_pct:.0f}% of forecast"
    else:
        # Was there an exogenous calendar effect on the predicted day?
        from ai.simulation.signals import demand_signals
        sig = demand_signals(pred.prediction_date)
        if sig["reasons"]:
            verdict = "missed"
            reason = f"calendar effect not in baseline: {', '.join(sig['reasons'])}"
        else:
            verdict = "missed"
            reason = f"model error ({pred.error_pct:.0f}% off), no known calendar cause"

    return {
        "prediction_id": pred.id,
        "agent": pred.agent_name,
        "date": pred.prediction_date.isoformat(),
        "predicted": pred.predicted_value,
        "actual": pred.actual_value,
        "error_pct": pred.error_pct,
        "verdict": verdict,
        "reason": reason,
    }


def run_feedback_cycle(db: Session, restaurant_id: int, days: int = 14) -> dict:
    """
    Interpret every recently-scored prediction for one restaurant: classify each,
    summarise by verdict, recompute per-agent reliability, and record a governance
    audit entry. Returns the summary.
    """
    cutoff = utcnow() - timedelta(days=days)
    preds = (
        db.query(models.AgentPrediction)
        .filter(
            models.AgentPrediction.restaurant_id == restaurant_id,
            models.AgentPrediction.evaluated_at >= cutoff,
            models.AgentPrediction.actual_value.isnot(None),
        )
        .all()
    )

    classifications = [classify_prediction(db, restaurant_id, p) for p in preds]
    by_verdict: dict[str, int] = {}
    agents_seen: set[str] = set()
    for c in classifications:
        by_verdict[c["verdict"]] = by_verdict.get(c["verdict"], 0) + 1
        if "agent" in c:
            agents_seen.add(c["agent"])

    reliability = {a: agent_reliability(db, restaurant_id, a, days=30) for a in sorted(agents_seen)}

    if classifications:
        write_audit_log(
            db, restaurant_id, "feedback_cycle", "feedback_loop",
            reasoning=f"Scored {len(classifications)} predictions: {by_verdict}",
            data_sources=["agent_predictions", "simulation.signals"],
            approved_by="ai",
        )

    return {
        "window_days": days,
        "scored": len(classifications),
        "by_verdict": by_verdict,
        "agent_reliability": reliability,
        "classifications": classifications,
    }
