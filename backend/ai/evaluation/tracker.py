"""
backend/ai/evaluation/tracker.py
──────────────────────────────────
Agent execution observability (Layer 12) + prediction tracking (Layer 10)
+ audit logging (Layer 15).

Three tools in one module:

1. @track_execution  — decorator: wraps any agent function and records
   execution time, success/failure to AgentExecution table.

2. record_prediction / evaluate_prediction — record a forecast before
   the fact, then fill in the actual outcome afterward.

3. write_audit_log — immutable governance record for every AI action
   that changes data.

Usage:

  from ai.evaluation.tracker import track_execution, record_prediction, write_audit_log

  @track_execution("pricing_intelligence", "get_pricing_intelligence")
  def get_pricing_intelligence(db, restaurant_id):
      ...

  # Record a revenue forecast
  pred_id = record_prediction(db, restaurant_id, "revenue_forecaster",
                              "daily_revenue", date(2024,6,15),
                              predicted=120000, ci_low=105000, ci_high=135000)

  # Next day, fill in the actual
  evaluate_prediction(db, pred_id, actual=117000)

  # Record a price change governance entry
  write_audit_log(db, restaurant_id, "price_changed", "pricing_intelligence",
                  entity_type="menu_item", entity_id=42,
                  before={"price": 500}, after={"price": 600},
                  reasoning="Surge demand detected, velocity_ratio=1.45",
                  approved_by="owner@restaurant.com")
"""

import time
import json
import logging
import functools
from datetime import date
from typing import Callable
from sqlalchemy.orm import Session
import models
from time_utils import utcnow

logger = logging.getLogger("ai.evaluation")


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 12: EXECUTION OBSERVABILITY DECORATOR
# ─────────────────────────────────────────────────────────────────────────────

def track_execution(agent_name: str, function_name: str, triggered_by: str = "api"):
    """
    Decorator that records agent execution timing and success/failure.

    Usage:
        @track_execution("profit_intelligence", "get_profit_intelligence")
        def get_profit_intelligence(db: Session, restaurant_id: int) -> dict:
            ...

    The wrapped function's first argument must be a SQLAlchemy Session (db).
    restaurant_id is extracted from kwargs or the second positional arg.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            db: Session | None = None
            restaurant_id: int | None = None

            # Extract db and restaurant_id from args
            for arg in args:
                if isinstance(arg, Session):
                    db = arg
                elif isinstance(arg, int) and restaurant_id is None:
                    restaurant_id = arg
            restaurant_id = kwargs.get("restaurant_id", restaurant_id)

            try:
                result = func(*args, **kwargs)
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                _record_execution(db, restaurant_id, agent_name, function_name,
                                  success=True, elapsed_ms=elapsed_ms,
                                  records=_count_records(result),
                                  triggered_by=triggered_by)
                return result
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                _record_execution(db, restaurant_id, agent_name, function_name,
                                  success=False, elapsed_ms=elapsed_ms,
                                  error=str(exc), triggered_by=triggered_by)
                logger.error(f"[{agent_name}] {function_name} failed: {exc}")
                raise

        return wrapper
    return decorator


def _record_execution(
    db: Session | None,
    restaurant_id: int | None,
    agent_name: str,
    function_name: str,
    success: bool,
    elapsed_ms: int,
    records: int = 0,
    error: str = "",
    triggered_by: str = "api",
) -> None:
    if db is None:
        return
    try:
        execution = models.AgentExecution(
            restaurant_id     = restaurant_id,
            agent_name        = agent_name,
            function_name     = function_name,
            success           = success,
            execution_ms      = elapsed_ms,
            error_message     = error[:2000] if error else "",
            records_processed = records,
            triggered_by      = triggered_by,
        )
        db.add(execution)
        db.commit()
    except Exception as exc:
        logger.warning(f"[Tracker] Failed to record execution: {exc}")


def _count_records(result) -> int:
    """Best-effort count of records in an agent result."""
    if isinstance(result, dict):
        for key in ("recommendations", "predictions", "item_analyses", "items"):
            if key in result and isinstance(result[key], list):
                return len(result[key])
    if isinstance(result, list):
        return len(result)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 10: PREDICTION TRACKING
# ─────────────────────────────────────────────────────────────────────────────

def record_prediction(
    db: Session,
    restaurant_id: int,
    agent_name: str,
    prediction_type: str,
    prediction_date: date,
    predicted: float,
    ci_low: float | None = None,
    ci_high: float | None = None,
    metadata: dict | None = None,
) -> int:
    """
    Record a prediction before the outcome is known.
    Returns the AgentPrediction.id for later evaluation.
    """
    pred = models.AgentPrediction(
        restaurant_id    = restaurant_id,
        agent_name       = agent_name,
        prediction_type  = prediction_type,
        prediction_date  = prediction_date,
        predicted_value  = predicted,
        predicted_ci_low = ci_low,
        predicted_ci_high = ci_high,
        metadata_json    = json.dumps(metadata or {}),
    )
    db.add(pred)
    db.commit()
    db.refresh(pred)
    return pred.id


def evaluate_prediction(
    db: Session,
    prediction_id: int,
    actual: float,
) -> dict:
    """
    Fill in the actual outcome for a recorded prediction.
    Computes error% and whether actual fell within the CI.
    """
    pred = db.query(models.AgentPrediction).filter(
        models.AgentPrediction.id == prediction_id
    ).first()
    if not pred:
        return {"error": "Prediction not found"}

    error_pct = abs(actual - pred.predicted_value) / max(abs(pred.predicted_value), 1) * 100
    within_ci = None
    if pred.predicted_ci_low is not None and pred.predicted_ci_high is not None:
        within_ci = pred.predicted_ci_low <= actual <= pred.predicted_ci_high

    pred.actual_value  = actual
    pred.error_pct     = round(error_pct, 2)
    pred.within_ci     = within_ci
    pred.evaluated_at  = utcnow()
    db.commit()

    return {
        "agent_name":      pred.agent_name,
        "predicted":       pred.predicted_value,
        "actual":          actual,
        "error_pct":       pred.error_pct,
        "within_ci":       within_ci,
        "verdict":         "good" if error_pct <= 10 else ("acceptable" if error_pct <= 20 else "poor"),
    }


def get_agent_accuracy(db: Session, restaurant_id: int, agent_name: str, days: int = 30) -> dict:
    """
    Compute accuracy metrics for an agent over the last N days.
    Returns mean absolute error%, % within CI, prediction count.
    """
    from datetime import timedelta
    cutoff = utcnow() - timedelta(days=days)
    preds = db.query(models.AgentPrediction).filter(
        models.AgentPrediction.restaurant_id == restaurant_id,
        models.AgentPrediction.agent_name    == agent_name,
        models.AgentPrediction.evaluated_at  >= cutoff,
        models.AgentPrediction.actual_value  != None,
    ).all()

    if not preds:
        return {"agent_name": agent_name, "prediction_count": 0, "mae_pct": None}

    errors      = [p.error_pct for p in preds if p.error_pct is not None]
    mae         = round(sum(errors) / len(errors), 2) if errors else None
    within_ci   = [p for p in preds if p.within_ci is True]
    ci_coverage = round(len(within_ci) / len(preds) * 100, 1)

    return {
        "agent_name":        agent_name,
        "prediction_count":  len(preds),
        "mae_pct":           mae,
        "ci_coverage_pct":   ci_coverage,
        "quality":           "good" if mae and mae <= 10 else ("acceptable" if mae and mae <= 20 else "poor"),
        "days_analyzed":     days,
    }


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 15: AI GOVERNANCE AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────

def write_audit_log(
    db: Session,
    restaurant_id: int,
    action_type: str,
    agent_name: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    before: dict | None = None,
    after: dict | None = None,
    reasoning: str = "",
    data_sources: list | None = None,
    approved_by: str = "system",
    recommendation_id: int | None = None,
) -> None:
    """
    Write an immutable governance record for an AI action that changed data.
    Called by: approve_recommendation, send_whatsapp_message, the executive
    orchestrator's event handlers, etc.
    """
    try:
        log = models.AgentAuditLog(
            restaurant_id     = restaurant_id,
            action_type       = action_type,
            agent_name        = agent_name,
            entity_type       = entity_type,
            entity_id         = entity_id,
            before_state      = json.dumps(before or {}),
            after_state       = json.dumps(after or {}),
            reasoning         = reasoning[:5000],
            data_sources      = json.dumps(data_sources or []),
            approved_by       = approved_by,
            recommendation_id = recommendation_id,
        )
        db.add(log)
        db.commit()
    except Exception as exc:
        logger.error(f"[AuditLog] Failed to write audit record: {exc}")


def _percentile(sorted_values: list[int], pct: int) -> int | None:
    """Nearest-rank percentile of a pre-sorted list. None if empty."""
    if not sorted_values:
        return None
    k = max(0, min(len(sorted_values) - 1, round((pct / 100.0) * len(sorted_values) + 0.5) - 1))
    return sorted_values[k]


def get_ai_ops_summary(db: Session, restaurant_id: int, days: int = 30) -> dict:
    """
    AIOps surface for one tenant: LLM token spend (by model), agent latency
    (p50/p95) and success rate, and the grounding trust rate. All of this was
    already captured (token_usage, agent_executions, the grounding verifier) but
    never exposed — this aggregates it read-only for a dashboard/alerting. See
    directives / the production-readiness roadmap's AIOps (G3) item.
    """
    from datetime import timedelta
    cutoff = utcnow() - timedelta(days=days)

    # ── LLM token spend ──────────────────────────────────────────────────────
    usage = (
        db.query(models.TokenUsage)
        .filter(models.TokenUsage.restaurant_id == restaurant_id,
                models.TokenUsage.created_at >= cutoff)
        .all()
    )
    total_in = total_out = 0
    by_model: dict[str, dict] = {}
    by_prompt_version: dict[str, dict] = {}
    for u in usage:
        ti, to = (u.input_tokens or 0), (u.output_tokens or 0)
        total_in += ti
        total_out += to
        m = by_model.setdefault(u.llm_model or "unknown",
                                {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        m["calls"] += 1
        m["input_tokens"] += ti
        m["output_tokens"] += to
        # Prompt-version breakdown: a jump in tokens/call against a new version is
        # the signal a prompt change got more expensive. Rows written before the
        # column existed report as "unknown".
        pv = by_prompt_version.setdefault(u.prompt_version or "unknown",
                                          {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        pv["calls"] += 1
        pv["input_tokens"] += ti
        pv["output_tokens"] += to

    # ── Agent latency + reliability ──────────────────────────────────────────
    execs = (
        db.query(models.AgentExecution)
        .filter(models.AgentExecution.restaurant_id == restaurant_id,
                models.AgentExecution.created_at >= cutoff)
        .all()
    )
    per_agent: dict[str, dict] = {}
    for e in execs:
        a = per_agent.setdefault(e.agent_name, {"runs": 0, "failures": 0, "latencies": []})
        a["runs"] += 1
        if not e.success:
            a["failures"] += 1
        if e.execution_ms is not None:
            a["latencies"].append(e.execution_ms)

    agents = []
    for name, d in sorted(per_agent.items()):
        lat = sorted(d["latencies"])
        agents.append({
            "agent": name,
            "runs": d["runs"],
            "success_rate_pct": round(100 * (d["runs"] - d["failures"]) / d["runs"], 1) if d["runs"] else None,
            "p50_ms": _percentile(lat, 50),
            "p95_ms": _percentile(lat, 95),
        })

    # ── Output grounding (process-wide; honest about scope) ──────────────────
    try:
        from ai.reasoning.narrator import get_trust_stats, PROMPT_VERSION
        grounding = get_trust_stats()
        current_prompt_version = PROMPT_VERSION
    except Exception:
        grounding = {"grounding_enabled": True}
        current_prompt_version = None

    # ── Money conversion (Phase 5): token counts → dollars, per model + total ─
    from ai.cost_model import cost_usd, USD_TO_KES
    total_cost_usd = 0.0
    for model_name, m in by_model.items():
        c = round(cost_usd(model_name, m["input_tokens"], m["output_tokens"]), 4)
        m["cost_usd"] = c
        total_cost_usd += c
    total_cost_usd = round(total_cost_usd, 4)
    cost_per_response = round(total_cost_usd / len(usage), 4) if usage else 0.0

    # Cost vs. profit-generated — the "is the AI paying for itself" line. Profit
    # comes from roi/savings.money_captured (approved pricing recs), kept as its
    # own already-audited figure; never blended into the token cost.
    money_captured_cents = 0
    try:
        from ai.roi.savings import get_roi_savings
        money_captured_cents = get_roi_savings(db, restaurant_id).get(
            "money_captured", {}).get("monthly_impact_cents", 0)
    except Exception:  # noqa: BLE001
        pass

    return {
        "window_days": days,
        "llm": {
            "calls": len(usage),
            "input_tokens": total_in,
            "output_tokens": total_out,
            "current_prompt_version": current_prompt_version,
            "by_model": by_model,
            "by_prompt_version": by_prompt_version,
            "cost_usd": total_cost_usd,
            "cost_kes_cents": int(round(total_cost_usd * USD_TO_KES * 100)),
            "cost_per_response_usd": cost_per_response,
        },
        "economics": {
            "llm_cost_usd": total_cost_usd,
            "llm_cost_kes_cents": int(round(total_cost_usd * USD_TO_KES * 100)),
            "profit_generated_cents": money_captured_cents,
            "note": "Profit is from approved pricing recommendations (roi/savings); "
                    "never summed with token cost.",
        },
        "agents": agents,
        "scorecards": get_agent_scorecards(db, restaurant_id, days=days),
        "grounding": grounding,
        "quality_drift": get_quality_drift(db, restaurant_id, days=days),
    }


def get_agent_scorecards(db: Session, restaurant_id: int, days: int = 30) -> list[dict]:
    """
    Per-agent scorecard for the AI-Ops view: forecast accuracy (for agents that
    record+evaluate predictions) and the owner acceptance rate (for pricing,
    from approved vs rejected recommendations). Deterministic aggregation of
    already-recorded data — nothing new is computed about the business here.
    """
    from datetime import timedelta
    cutoff = utcnow() - timedelta(days=days)

    # Which agents have evaluated predictions in the window → accuracy per agent.
    agent_names = [
        r[0] for r in db.query(models.AgentPrediction.agent_name)
        .filter(models.AgentPrediction.restaurant_id == restaurant_id,
                models.AgentPrediction.evaluated_at >= cutoff)
        .distinct().all()
    ]
    cards: list[dict] = []
    for name in sorted(agent_names):
        acc = get_agent_accuracy(db, restaurant_id, name, days=days)
        cards.append({
            "agent": name,
            "prediction_count": acc.get("prediction_count", 0),
            "mae_pct": acc.get("mae_pct"),
            "ci_coverage_pct": acc.get("ci_coverage_pct"),
            "quality": acc.get("quality"),
        })

    # Pricing acceptance rate: approved / (approved + rejected) in the window.
    approved = db.query(models.PricingRecommendation).filter(
        models.PricingRecommendation.restaurant_id == restaurant_id,
        models.PricingRecommendation.status == "APPROVED",
        models.PricingRecommendation.actioned_at >= cutoff,
    ).count()
    rejected = db.query(models.PricingRecommendation).filter(
        models.PricingRecommendation.restaurant_id == restaurant_id,
        models.PricingRecommendation.status == "REJECTED",
        models.PricingRecommendation.actioned_at >= cutoff,
    ).count()
    decided = approved + rejected
    if decided:
        cards.append({
            "agent": "pricing_intelligence",
            "acceptance_rate_pct": round(100 * approved / decided, 1),
            "approved": approved,
            "rejected": rejected,
        })

    return cards


def get_quality_drift(db: Session, restaurant_id: int, days: int = 30,
                      min_samples: int = 3, drift_threshold_pct: float = 10.0) -> dict:
    """
    Quality-drift alarm for the forecasting agents. Compares each agent's
    prediction error in the RECENT half of the window against the PRIOR half; if
    the mean absolute error worsened by more than `drift_threshold_pct` points
    (with enough samples on both sides to be meaningful), it is flagged as
    drifting so an operator can investigate before owners lose trust in a number.

    Honest about scope: it can only judge agents that record predictions AND get
    them evaluated against actuals (revenue/reservation forecasters). Agents with
    too little evaluated history report status "insufficient_data", never a false
    all-clear. Returns {status, checked_agents, drifting[], stable[]}.
    """
    from datetime import timedelta
    now = utcnow()
    window_start = now - timedelta(days=days)
    midpoint = now - timedelta(days=days / 2)

    preds = (
        db.query(models.AgentPrediction)
        .filter(models.AgentPrediction.restaurant_id == restaurant_id,
                models.AgentPrediction.evaluated_at >= window_start,
                models.AgentPrediction.actual_value != None,  # noqa: E711
                models.AgentPrediction.error_pct != None)     # noqa: E711
        .all()
    )

    by_agent: dict[str, dict] = {}
    for p in preds:
        bucket = by_agent.setdefault(p.agent_name, {"recent": [], "prior": []})
        half = "recent" if p.evaluated_at >= midpoint else "prior"
        bucket[half].append(p.error_pct)

    drifting, stable, insufficient = [], [], []
    for name, halves in sorted(by_agent.items()):
        recent, prior = halves["recent"], halves["prior"]
        if len(recent) < min_samples or len(prior) < min_samples:
            insufficient.append(name)
            continue
        recent_mae = round(sum(recent) / len(recent), 2)
        prior_mae = round(sum(prior) / len(prior), 2)
        delta = round(recent_mae - prior_mae, 2)
        entry = {
            "agent": name,
            "recent_mae_pct": recent_mae,
            "baseline_mae_pct": prior_mae,
            "delta_pct": delta,
            "recent_samples": len(recent),
        }
        (drifting if delta > drift_threshold_pct else stable).append(entry)

    if not drifting and not stable:
        status = "insufficient_data"
    else:
        status = "drift_detected" if drifting else "stable"

    return {
        "status": status,
        "threshold_pct": drift_threshold_pct,
        "checked_agents": len(drifting) + len(stable),
        "insufficient_data_agents": insufficient,
        "drifting": drifting,
        "stable": stable,
    }


def get_audit_trail(
    db: Session,
    restaurant_id: int,
    action_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Retrieve audit log entries for the governance dashboard."""
    q = db.query(models.AgentAuditLog).filter(
        models.AgentAuditLog.restaurant_id == restaurant_id
    )
    if action_type:
        q = q.filter(models.AgentAuditLog.action_type == action_type)

    entries = q.order_by(models.AgentAuditLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id":            e.id,
            "action_type":   e.action_type,
            "agent_name":    e.agent_name,
            "entity_type":   e.entity_type,
            "entity_id":     e.entity_id,
            "reasoning":     e.reasoning,
            "approved_by":   e.approved_by,
            "created_at":    e.created_at.isoformat(),
        }
        for e in entries
    ]
