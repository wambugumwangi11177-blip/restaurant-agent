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
from datetime import datetime, date
from typing import Callable
from sqlalchemy.orm import Session
import models

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
    pred.evaluated_at  = datetime.utcnow()
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
    cutoff = datetime.utcnow() - timedelta(days=days)
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
    Called by: approve_recommendation, send_whatsapp_message, campaign_launch, etc.
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
