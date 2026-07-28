"""
Phase 9 — the self-evaluation feedback loop and autonomous planning.

Feedback must: derive a reliability multiplier that drops for a poor agent and
stays 1.0 for one with no history; classify a miss on a calendar-signal day as an
exogenous effect rather than model error; and feed reliability into the Decision
ranking (a proven-poor agent's decisions get down-weighted). Planning must produce
a monitored week-by-week plan with check-in dates.
"""

from datetime import date, timedelta

import pytest

import models
from time_utils import utcnow
from ai.evaluation import feedback, tracker
from ai.orchestrator import strategist


def _tenant_id(db) -> int:
    tenant = models.Tenant(name="Feedback Tenant")
    db.add(tenant)
    db.commit()
    return tenant.id


@pytest.fixture
def restaurant(db_session):
    db_session.add(models.Restaurant(id=1, tenant_id=_tenant_id(db_session), name="FB", address="x"))
    db_session.commit()
    return db_session


# ── reliability ─────────────────────────────────────────────────────────────────

def test_reliability_is_full_without_history(restaurant):
    assert feedback.agent_reliability(restaurant, 1, "revenue_forecaster") == 1.0


def test_reliability_drops_for_a_poor_agent(restaurant):
    db = restaurant
    # seed several evaluated predictions with large errors → low reliability
    for i in range(4):
        pid = tracker.record_prediction(db, 1, "revenue_forecaster", "daily_revenue",
                                        (utcnow() - timedelta(days=i + 1)).date(),
                                        predicted=100.0)
        tracker.evaluate_prediction(db, pid, actual=200.0)   # 100% error each
    rel = feedback.agent_reliability(db, 1, "revenue_forecaster")
    assert rel == feedback.RELIABILITY_MIN   # capped at the floor for a very poor agent


# ── classification ──────────────────────────────────────────────────────────────

def test_classify_within_ci_is_worked(restaurant):
    db = restaurant
    pid = tracker.record_prediction(db, 1, "revenue_forecaster", "daily_revenue",
                                    (utcnow() - timedelta(days=1)).date(),
                                    predicted=100.0, ci_low=90.0, ci_high=110.0)
    tracker.evaluate_prediction(db, pid, actual=105.0)
    pred = db.query(models.AgentPrediction).get(pid)
    c = feedback.classify_prediction(db, 1, pred)
    assert c["verdict"] == "worked"


def test_classify_big_miss_on_holiday_blames_calendar(restaurant):
    db = restaurant
    # Christmas 2026 is a known holiday signal
    pid = tracker.record_prediction(db, 1, "revenue_forecaster", "daily_revenue",
                                    date(2026, 12, 25), predicted=100.0,
                                    ci_low=95.0, ci_high=105.0)
    tracker.evaluate_prediction(db, pid, actual=300.0)   # 200% miss
    pred = db.query(models.AgentPrediction).get(pid)
    c = feedback.classify_prediction(db, 1, pred)
    assert c["verdict"] == "missed"
    assert "calendar" in c["reason"].lower()


def test_run_feedback_cycle_summarizes_and_audits(restaurant):
    db = restaurant
    pid = tracker.record_prediction(db, 1, "revenue_forecaster", "daily_revenue",
                                    (utcnow() - timedelta(days=1)).date(),
                                    predicted=100.0, ci_low=90.0, ci_high=110.0)
    tracker.evaluate_prediction(db, pid, actual=104.0)
    out = feedback.run_feedback_cycle(db, 1)
    assert out["scored"] == 1
    assert "worked" in out["by_verdict"]
    assert "revenue_forecaster" in out["agent_reliability"]
    assert db.query(models.AgentAuditLog).filter_by(action_type="feedback_cycle").count() == 1


# ── reliability feeds the ranking ────────────────────────────────────────────────

def test_low_reliability_downweights_decisions(db_session):
    """A pricing decision's confidence is scaled down when the pricing agent has a
    poor track record."""
    from datetime import timedelta as td
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=_tenant_id(db), name="R", address="x"))
    db.add(models.MenuItem(id=1, restaurant_id=1, name="ThinBurger", price=1000, cost_price=900, category="m"))
    db.commit()
    for i in range(8):
        o = models.Order(restaurant_id=1, status=models.OrderStatus.SERVED,
                         payment_method=models.PaymentMethod.CASH, is_paid=True,
                         total=1000, created_at=utcnow() - td(days=i + 1))
        db.add(o)
        db.flush()
        db.add(models.OrderItem(order_id=o.id, menu_item_id=1, quantity=1, unit_price=1000))
    db.commit()

    from ai.decisions import get_ranked_decisions
    base = get_ranked_decisions(db, 1, apply_reliability=False)
    base_conf = next(d["confidence_pct"] for d in base["decisions"] if d["category"] == "pricing")

    # give pricing_intelligence a poor prediction record
    for i in range(4):
        pid = tracker.record_prediction(db, 1, "pricing_intelligence", "price_impact",
                                        (utcnow() - td(days=i + 1)).date(), predicted=100.0)
        tracker.evaluate_prediction(db, pid, actual=300.0)

    adj = get_ranked_decisions(db, 1, apply_reliability=True)
    adj_conf = next(d["confidence_pct"] for d in adj["decisions"] if d["category"] == "pricing")
    assert adj_conf < base_conf


# ── planning ─────────────────────────────────────────────────────────────────────

def test_plan_produces_monitored_weeks(db_session):
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=_tenant_id(db), name="P", address="x"))
    db.add(models.MenuItem(id=1, restaurant_id=1, name="ThinBurger", price=1000, cost_price=900, category="m"))
    db.commit()
    for i in range(8):
        o = models.Order(restaurant_id=1, status=models.OrderStatus.SERVED,
                         payment_method=models.PaymentMethod.CASH, is_paid=True,
                         total=1000, created_at=utcnow() - timedelta(days=i + 1))
        db.add(o)
        db.flush()
        db.add(models.OrderItem(order_id=o.id, menu_item_id=1, quantity=1, unit_price=1000))
    db.commit()

    out = strategist.plan(db, 1, "increase profit", horizon_weeks=4)
    assert out["available"] is True
    assert out["horizon_weeks"] == 4
    assert len(out["weeks"]) >= 1
    first = out["weeks"][0]
    assert first["week"] == 1
    assert "check_in_date" in first
    assert "action" in first["decision"]


def test_plan_rejects_empty_goal(restaurant):
    assert strategist.plan(restaurant, 1, "  ")["available"] is False
