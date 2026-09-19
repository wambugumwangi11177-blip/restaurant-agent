"""Stage five: did the advice the owner took actually pay off?

AttentionDecision recorded the click and was read in exactly one place — the
filter that hides the card. run_feedback_cycle measured forecasts, not
decisions. So the system learned whether its revenue prediction was right and
nothing about whether its recommendations were worth taking.

ai/orchestrator/executive.py:on_recommendation_approved has said since it was
written that "at day 7 and day 14, the evaluation agent checks if revenue from
that item improved". Its body writes a memory entry and an audit log. Nothing
was scheduled and nothing was measured.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

import models
from time_utils import utcnow
from ai.evaluation.outcomes import (
    record_decision_outcome, evaluate_due_decision_outcomes,
    DECISION_IMPACT, COMPARISON_DAYS,
)


@pytest.fixture
def rid(db_session):
    db = db_session
    db.add(models.Tenant(id=1300, name="Outcome tenant"))
    db.flush()
    db.add(models.Restaurant(id=1301, tenant_id=1300, name="Outcome test"))
    db.commit()
    return 1301


def _item(db, rid, price=10000, cost=4000):
    item = models.MenuItem(restaurant_id=rid, name="Measured Dish",
                           price=price, cost_price=cost, category="Main")
    db.add(item)
    db.commit()
    return item


def _sales(db, rid, item, qty_per_day, days_ago_from, days_ago_to, unit_price=None):
    for day in range(days_ago_to, days_ago_from):
        order = models.Order(restaurant_id=rid, total=qty_per_day * item.price,
                             is_paid=True, status=models.OrderStatus.SERVED,
                             created_at=utcnow() - timedelta(days=day))
        db.add(order)
        db.flush()
        db.add(models.OrderItem(order_id=order.id, menu_item_id=item.id,
                                quantity=qty_per_day,
                                unit_price=unit_price or item.price))
    db.commit()


def _card(item, impact=500000):
    return {
        "id": "d-test01", "title": "Reprice: set Measured Dish to KES 130",
        "agent": "pricing_intelligence", "entity_type": "menu_item",
        "entity_id": item.id, "impact_cents_month": impact,
    }


# ── Recording ────────────────────────────────────────────────────────────────

def test_approving_a_measurable_card_records_what_was_claimed(db_session, rid):
    item = _item(db_session, rid)
    _sales(db_session, rid, item, 5, COMPARISON_DAYS, 1)

    pred_id = record_decision_outcome(db_session, rid, _card(item), "approved")
    assert pred_id is not None

    pred = db_session.query(models.AgentPrediction).filter_by(id=pred_id).one()
    assert pred.prediction_type == DECISION_IMPACT
    assert pred.predicted_value == 500000
    assert pred.actual_value is None, "not scoreable until the horizon passes"
    meta = json.loads(pred.metadata_json)
    assert meta["menu_item_id"] == item.id
    assert meta["baseline_profit_cents"] > 0


def test_rejecting_records_nothing_to_score(db_session, rid):
    item = _item(db_session, rid)
    assert record_decision_outcome(db_session, rid, _card(item), "rejected") is None
    assert record_decision_outcome(db_session, rid, _card(item), "later") is None


def test_advice_with_no_countable_outcome_is_not_scored(db_session, rid):
    """"Check the beef usage against the recipes" happens in a store room and
    leaves no row. Counting it as a miss would punish an agent for the shape of
    its advice rather than its quality."""
    card = {"id": "d-x", "title": "Check Beef usage against the recipes",
            "agent": "stock_custody", "entity_type": "inventory_item",
            "entity_id": 1, "impact_cents_month": 300000}
    assert record_decision_outcome(db_session, rid, card, "approved") is None


def test_an_uncosted_item_is_not_scored(db_session, rid):
    """No cost price means no measurable margin — scoring against a phantom
    100% margin would teach the ranking the wrong lesson."""
    item = _item(db_session, rid, cost=0)
    assert record_decision_outcome(db_session, rid, _card(item), "approved") is None


def test_an_unquantified_card_is_not_scored(db_session, rid):
    item = _item(db_session, rid)
    assert record_decision_outcome(
        db_session, rid, _card(item, impact=None), "approved") is None


# ── Scoring ──────────────────────────────────────────────────────────────────

def test_a_matured_decision_is_scored_against_what_happened(db_session, rid):
    item = _item(db_session, rid)
    _sales(db_session, rid, item, 5, COMPARISON_DAYS, 1)
    pred_id = record_decision_outcome(db_session, rid, _card(item), "approved")

    # Pull the horizon into the past so it is due.
    pred = db_session.query(models.AgentPrediction).filter_by(id=pred_id).one()
    pred.prediction_date = (utcnow() - timedelta(days=1)).date()
    meta = json.loads(pred.metadata_json)
    meta["decided_at"] = (utcnow() - timedelta(days=14)).isoformat()
    pred.metadata_json = json.dumps(meta)
    db_session.commit()

    assert evaluate_due_decision_outcomes(db_session, rid) == 1
    db_session.expire_all()
    scored = db_session.query(models.AgentPrediction).filter_by(id=pred_id).one()
    assert scored.actual_value is not None
    assert scored.error_pct is not None
    assert scored.evaluated_at is not None


def test_an_unmatured_decision_is_left_alone(db_session, rid):
    item = _item(db_session, rid)
    _sales(db_session, rid, item, 5, COMPARISON_DAYS, 1)
    record_decision_outcome(db_session, rid, _card(item), "approved")

    assert evaluate_due_decision_outcomes(db_session, rid) == 0


def test_scoring_is_not_repeated(db_session, rid):
    item = _item(db_session, rid)
    _sales(db_session, rid, item, 5, COMPARISON_DAYS, 1)
    pred_id = record_decision_outcome(db_session, rid, _card(item), "approved")
    pred = db_session.query(models.AgentPrediction).filter_by(id=pred_id).one()
    pred.prediction_date = (utcnow() - timedelta(days=1)).date()
    meta = json.loads(pred.metadata_json)
    meta["decided_at"] = (utcnow() - timedelta(days=14)).isoformat()
    pred.metadata_json = json.dumps(meta)
    db_session.commit()

    assert evaluate_due_decision_outcomes(db_session, rid) == 1
    assert evaluate_due_decision_outcomes(db_session, rid) == 0


# ── The loop closes ──────────────────────────────────────────────────────────

def test_a_scored_decision_moves_the_agent_s_reliability(db_session, rid):
    """The point of measuring. agent_reliability feeds _apply_reliability in
    ai/decisions/__init__.py, so an agent whose advice does not pay off is
    trusted less in the next ranking."""
    from ai.evaluation.feedback import agent_reliability, RELIABILITY_FULL

    assert agent_reliability(db_session, rid, "pricing_intelligence") == RELIABILITY_FULL

    # A decision that claimed KES 5,000/month and delivered nothing.
    item = _item(db_session, rid)
    _sales(db_session, rid, item, 5, COMPARISON_DAYS, 1)
    pred_id = record_decision_outcome(db_session, rid, _card(item), "approved")
    pred = db_session.query(models.AgentPrediction).filter_by(id=pred_id).one()
    pred.prediction_date = (utcnow() - timedelta(days=1)).date()
    meta = json.loads(pred.metadata_json)
    meta["decided_at"] = (utcnow() - timedelta(days=14)).isoformat()
    pred.metadata_json = json.dumps(meta)
    db_session.commit()
    evaluate_due_decision_outcomes(db_session, rid)

    assert agent_reliability(db_session, rid, "pricing_intelligence") < RELIABILITY_FULL


def test_the_daily_cycle_scores_decisions_too(db_session, rid):
    from ai.evaluation.learning import run_learning_cycle

    item = _item(db_session, rid)
    _sales(db_session, rid, item, 5, COMPARISON_DAYS, 1)
    pred_id = record_decision_outcome(db_session, rid, _card(item), "approved")
    pred = db_session.query(models.AgentPrediction).filter_by(id=pred_id).one()
    pred.prediction_date = (utcnow() - timedelta(days=1)).date()
    meta = json.loads(pred.metadata_json)
    meta["decided_at"] = (utcnow() - timedelta(days=14)).isoformat()
    pred.metadata_json = json.dumps(meta)
    db_session.commit()

    assert run_learning_cycle(db_session)["decisions_scored"] == 1
