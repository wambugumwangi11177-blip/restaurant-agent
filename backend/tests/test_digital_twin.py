"""
Digital Twin — forward revenue projection with exogenous calendar signals.

The twin must (1) keep the sales-history baseline and the exogenous uplift
SEPARATE and honest, (2) apply a holiday/school factor only on the right dates,
and (3) never produce an absurd projection (factors are clamped). The signal
providers must combine multiplicatively and stay neutral when nothing applies.
"""

from datetime import date, timedelta

import pytest

import models
from time_utils import utcnow
from ai.simulation import forecast_twin
from ai.simulation import signals


# ── signal providers ───────────────────────────────────────────────────────────

def test_holiday_signal_fires_on_a_known_holiday():
    s = signals.demand_signals(date(2026, 12, 25))   # Christmas
    assert s["factor"] > 1.0
    assert any("Christmas" in r for r in s["reasons"])


def test_ordinary_day_is_neutral():
    s = signals.demand_signals(date(2026, 7, 15))    # a plain mid-July Wednesday
    assert s["factor"] == 1.0
    assert s["reasons"] == []
    assert s["confidence"] == 100


def test_approximate_holiday_has_lower_confidence():
    # Madaraka Day (Jun 1) is a fixed holiday outside any school-break window, so
    # its confidence isn't pulled down by a stacked signal — unlike Eid (approx).
    exact = signals.demand_signals(date(2026, 6, 1))
    approx = signals.demand_signals(date(2026, 3, 20))   # Eid (approx.)
    assert approx["confidence"] < exact["confidence"]


def test_factor_is_clamped_to_sane_band():
    # Even if holiday + school break stack, the factor stays within the clamp.
    s = signals.demand_signals(date(2026, 12, 25))   # Christmas AND December school break
    assert signals._FACTOR_MIN <= s["factor"] <= signals._FACTOR_MAX
    assert len(s["reasons"]) >= 1


# ── twin projection ────────────────────────────────────────────────────────────

@pytest.fixture
def revenue_history(db_session):
    """A restaurant with ~30 days of steady revenue so the forecaster has a
    baseline to build on."""
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=None, name="Twin", address="x"))
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


def test_twin_returns_baseline_projected_and_uplift(revenue_history):
    out = forecast_twin(revenue_history, 1, horizon_days=30)
    assert out["available"] is True
    s = out["summary"]
    assert s["baseline_revenue_cents"] > 0
    assert s["projected_revenue_cents"] >= s["baseline_revenue_cents"]   # signals only lift here
    assert s["uplift_cents"] == s["projected_revenue_cents"] - s["baseline_revenue_cents"]
    assert 20 <= s["confidence_pct"] <= 90
    assert len(out["daily"]) == 30


def test_twin_confidence_decays_with_horizon(revenue_history):
    short = forecast_twin(revenue_history, 1, horizon_days=7)["summary"]["confidence_pct"]
    long = forecast_twin(revenue_history, 1, horizon_days=90)["summary"]["confidence_pct"]
    assert short >= long


def test_twin_flags_signal_days(revenue_history):
    out = forecast_twin(revenue_history, 1, horizon_days=90)
    # Over a 90-day window from "today" there is almost certainly at least one
    # holiday or school-break day, each surfaced in contributing_factors.
    assert out["summary"]["signal_days"] == len(out["contributing_factors"])
    for f in out["contributing_factors"]:
        assert f["reasons"]
        assert f["projected_cents"] != f["baseline_cents"]


def test_twin_needs_history(db_session):
    db_session.add(models.Restaurant(id=1, tenant_id=None, name="Empty", address="x"))
    db_session.commit()
    out = forecast_twin(db_session, 1, horizon_days=30)
    assert out["available"] is False
