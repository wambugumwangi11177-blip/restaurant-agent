"""
Phase 5 — monetary LLM cost, the continuous-learning loop, and agent scorecards.

Cost conversion must resolve real provider model ids and never report zero for an
unknown model. The learning loop must record a forecast as a prediction and later
score it against ACTUAL revenue (error_pct / within_ci populated). Scorecards must
surface accuracy + pricing acceptance rate from already-recorded data.
"""

from datetime import date, timedelta, datetime

import pytest

import models
from time_utils import utcnow
from ai import cost_model
from ai.evaluation import learning, tracker


# ── cost model ──────────────────────────────────────────────────────────────────

def test_cost_resolves_known_models_by_substring():
    # gpt-oss-120b input at 0.15/Mtok, output 0.60/Mtok
    c = cost_model.cost_usd("openai/gpt-oss-120b", 1_000_000, 1_000_000)
    assert round(c, 2) == round(0.15 + 0.60, 2)


def test_cost_prefers_longest_match():
    # "llama-3.1-8b-instant" must match "llama-3.1-8b", not a shorter key
    c = cost_model.cost_usd("llama-3.1-8b-instant", 1_000_000, 0)
    assert round(c, 3) == 0.05


def test_unknown_model_uses_conservative_default_not_zero():
    c = cost_model.cost_usd("some-future-model-x", 1_000_000, 1_000_000)
    assert c > 0


def test_kes_conversion_is_positive_integer_cents():
    cents = cost_model.cost_kes_cents("claude-haiku-4-5", 1_000_000, 500_000)
    assert isinstance(cents, int) and cents > 0


# ── learning loop ───────────────────────────────────────────────────────────────

@pytest.fixture
def restaurant_with_history(db_session):
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=None, name="Learn", address="x"))
    db.add(models.MenuItem(id=1, restaurant_id=1, name="Plate", price=1000, cost_price=400, category="main"))
    db.commit()
    now = utcnow()
    for d in range(35):
        o = models.Order(restaurant_id=1, status=models.OrderStatus.SERVED,
                         payment_method=models.PaymentMethod.CASH, is_paid=True,
                         total=5000, created_at=now - timedelta(days=d))
        db.add(o)
        db.flush()
        db.add(models.OrderItem(order_id=o.id, menu_item_id=1, quantity=5, unit_price=1000))
    db.commit()
    return db


def test_record_revenue_forecast_is_idempotent(restaurant_with_history):
    db = restaurant_with_history
    first = learning.record_revenue_forecast(db, 1)
    assert first is not None
    # a second call for the same forecast date must not create a duplicate
    assert learning.record_revenue_forecast(db, 1) is None
    assert db.query(models.AgentPrediction).filter_by(restaurant_id=1).count() == 1


def test_evaluate_due_predictions_scores_against_actual(db_session):
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=None, name="Learn", address="x"))
    db.commit()
    yesterday = (utcnow() - timedelta(days=1)).date()
    # a matured prediction for yesterday
    pid = tracker.record_prediction(db, 1, learning.REVENUE_AGENT, learning.DAILY_REVENUE,
                                    yesterday, predicted=10000.0, ci_low=8000.0, ci_high=12000.0)
    # actual revenue for yesterday: one KES 110 order
    start = datetime(yesterday.year, yesterday.month, yesterday.day)
    o = models.Order(restaurant_id=1, status=models.OrderStatus.SERVED,
                     payment_method=models.PaymentMethod.CASH, is_paid=True,
                     total=11000, created_at=start + timedelta(hours=12))
    db.add(o)
    db.commit()

    n = learning.evaluate_due_predictions(db, 1)
    assert n == 1
    pred = db.query(models.AgentPrediction).get(pid)
    assert pred.actual_value == 11000.0
    assert pred.error_pct is not None
    assert pred.within_ci is True          # 11000 is within [8000, 12000]


def test_future_prediction_not_yet_due(db_session):
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=None, name="Learn", address="x"))
    db.commit()
    tomorrow = (utcnow() + timedelta(days=1)).date()
    tracker.record_prediction(db, 1, learning.REVENUE_AGENT, learning.DAILY_REVENUE,
                              tomorrow, predicted=10000.0)
    assert learning.evaluate_due_predictions(db, 1) == 0


def test_run_learning_cycle_records_and_evaluates(restaurant_with_history):
    out = learning.run_learning_cycle(restaurant_with_history)
    assert out["recorded"] >= 1


# ── scorecards ──────────────────────────────────────────────────────────────────

def test_scorecards_surface_accuracy_and_acceptance(db_session):
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=None, name="Score", address="x"))
    db.add(models.MenuItem(id=1, restaurant_id=1, name="X", price=1000, cost_price=400, category="m"))
    db.commit()
    # an evaluated prediction → accuracy card
    y = (utcnow() - timedelta(days=2)).date()
    pid = tracker.record_prediction(db, 1, "revenue_forecaster", "daily_revenue", y,
                                    predicted=100.0, ci_low=90.0, ci_high=110.0)
    tracker.evaluate_prediction(db, pid, actual=105.0)
    # one approved + one rejected pricing rec → acceptance rate 50%
    db.add(models.PricingRecommendation(restaurant_id=1, menu_item_id=1, recommendation_type="REPRICE",
                                        current_price=1000, suggested_price=1100, status="APPROVED",
                                        actioned_at=utcnow()))
    db.add(models.PricingRecommendation(restaurant_id=1, menu_item_id=1, recommendation_type="SURGE",
                                        current_price=1000, suggested_price=1200, status="REJECTED",
                                        actioned_at=utcnow()))
    db.commit()

    cards = tracker.get_agent_scorecards(db, 1, days=30)
    by_agent = {c["agent"]: c for c in cards}
    assert "revenue_forecaster" in by_agent
    assert by_agent["revenue_forecaster"]["prediction_count"] == 1
    assert by_agent["pricing_intelligence"]["acceptance_rate_pct"] == 50.0
