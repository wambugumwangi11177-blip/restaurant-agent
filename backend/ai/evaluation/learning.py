"""
backend/ai/evaluation/learning.py
────────────────────────────────────
The continuous-learning loop (Phase 5). Closes the "predict → wait → score"
cycle so the forecasting agents get measured against reality and their accuracy
becomes visible (AgentPrediction.error_pct / within_ci → get_agent_accuracy,
get_quality_drift, the AI-Ops scorecards).

Two halves, run daily by the scheduler (main.py):
  1. record_revenue_forecast — snapshot tomorrow's revenue forecast as a
     prediction, BEFORE the fact, with its confidence interval.
  2. evaluate_due_predictions — for any matured daily_revenue prediction whose
     day has now passed, compute the ACTUAL revenue and fill it in.

Deterministic. No LLM. Idempotent: recording twice for the same date is guarded,
and evaluating an already-evaluated prediction is skipped.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from time_utils import utcnow
from .tracker import record_prediction, evaluate_prediction

logger = logging.getLogger("ai.learning")

REVENUE_AGENT = "revenue_forecaster"
DAILY_REVENUE = "daily_revenue"


def actual_revenue_for(db: Session, restaurant_id: int, day: date) -> int:
    """Real paid revenue (cents) for one calendar day — the ground truth we score
    a daily_revenue prediction against."""
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)
    total = (
        db.query(func.coalesce(func.sum(models.Order.total), 0))
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= start,
            models.Order.created_at < end,
        )
        .scalar()
    )
    return int(total or 0)


def record_revenue_forecast(db: Session, restaurant_id: int) -> int | None:
    """
    Record the next forecast day as a prediction. Returns the prediction id, or
    None if there's nothing to record (no forecast, or already recorded for that
    date). Idempotent per (restaurant, date, agent, type).
    """
    from ai.revenue_forecaster import get_revenue_forecast
    data = get_revenue_forecast(db, restaurant_id)
    forecast = data.get("forecast") if isinstance(data, dict) else None
    if not forecast:
        return None

    first = forecast[0]
    try:
        pred_date = datetime.strptime(first["date"], "%Y-%m-%d").date()
    except (KeyError, ValueError):
        return None

    exists = (
        db.query(models.AgentPrediction.id)
        .filter(
            models.AgentPrediction.restaurant_id == restaurant_id,
            models.AgentPrediction.agent_name == REVENUE_AGENT,
            models.AgentPrediction.prediction_type == DAILY_REVENUE,
            models.AgentPrediction.prediction_date == pred_date,
        )
        .first()
    )
    if exists:
        return None

    return record_prediction(
        db, restaurant_id, REVENUE_AGENT, DAILY_REVENUE, pred_date,
        predicted=float(first.get("predicted_revenue", 0)),
        ci_low=float(first.get("confidence_low", 0)),
        ci_high=float(first.get("confidence_high", 0)),
        metadata={"confidence_pct": first.get("confidence_pct")},
    )


def evaluate_due_predictions(db: Session, restaurant_id: int, as_of: date | None = None) -> int:
    """
    Score every matured, not-yet-evaluated daily_revenue prediction for this
    restaurant against actual revenue. Returns how many were evaluated.
    """
    today = as_of or utcnow().date()
    due = (
        db.query(models.AgentPrediction)
        .filter(
            models.AgentPrediction.restaurant_id == restaurant_id,
            models.AgentPrediction.agent_name == REVENUE_AGENT,
            models.AgentPrediction.prediction_type == DAILY_REVENUE,
            models.AgentPrediction.actual_value.is_(None),
            models.AgentPrediction.prediction_date < today,   # the day has passed
        )
        .all()
    )
    evaluated = 0
    for pred in due:
        actual = actual_revenue_for(db, restaurant_id, pred.prediction_date)
        evaluate_prediction(db, pred.id, actual=float(actual))
        evaluated += 1
    return evaluated


def run_learning_cycle(db: Session) -> dict:
    """
    One full cycle across every restaurant: record tomorrow's forecast and score
    any matured predictions. Called by the daily scheduler job. Degrades
    per-restaurant — one failure never stops the others.
    """
    restaurants = db.query(models.Restaurant.id).all()
    recorded = evaluated = 0
    for (rid,) in restaurants:
        try:
            if record_revenue_forecast(db, rid) is not None:
                recorded += 1
            evaluated += evaluate_due_predictions(db, rid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("learning cycle failed for restaurant %s: %s", rid, exc)
    logger.info("learning cycle: recorded=%s evaluated=%s", recorded, evaluated)
    return {"recorded": recorded, "evaluated": evaluated}
