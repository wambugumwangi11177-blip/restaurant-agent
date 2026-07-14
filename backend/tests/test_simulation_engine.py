"""
The "what if…" Simulation Engine.

The engine must be deterministic, bounded, and directionally correct: raising a
price lifts per-unit profit but suppresses volume (elasticity < 0); the verdict
must protect the margin floor; a supplier cost rise with the price held must
reduce profit. These are the guarantees an owner is trusting when they read
"Projected profit +KES X — YES".
"""

from datetime import timedelta

import pytest

import models
from time_utils import utcnow
from ai.simulation import run_simulation
from ai.simulation.engine import (
    _effective_elasticity, _satisfaction_delta, _confidence,
    ELASTICITY_MIN, ELASTICITY_MAX, simulate_price_change,
)


# ── pure-function invariants ───────────────────────────────────────────────────

def test_elasticity_is_always_in_bounds_and_negative():
    for ratio in (0.1, 0.5, 1.0, 1.5, 3.0):
        e = _effective_elasticity(ratio)
        assert ELASTICITY_MIN <= e <= ELASTICITY_MAX < 0


def test_hot_items_are_less_price_sensitive_than_slow_ones():
    assert _effective_elasticity(1.6) > _effective_elasticity(0.5)  # closer to 0 = less elastic


def test_satisfaction_proxy_direction_and_bounds():
    assert _satisfaction_delta(20) < 0          # price up → satisfaction down
    assert _satisfaction_delta(-20) > 0         # discount → satisfaction up
    assert _satisfaction_delta(1000) >= -15     # bounded
    assert _satisfaction_delta(-1000) <= 8


def test_confidence_penalises_large_moves_and_thin_history():
    assert _confidence(40, 5) > _confidence(5, 5)         # more history → more confident
    assert _confidence(40, 5) > _confidence(40, 50)       # big move → less confident
    assert 20 <= _confidence(0, 100) <= 90


# ── integration against a real (SQLite) DB ─────────────────────────────────────

@pytest.fixture
def seeded(db_session):
    db_session.add(models.Restaurant(id=1, tenant_id=None, name="Sim", address="x"))
    # price 1000, cost 400 → 60% margin, comfortably above the 40% floor.
    db_session.add(models.MenuItem(id=1, restaurant_id=1, name="Burger",
                                   price=1000, cost_price=400, category="main"))
    db_session.commit()
    # ~2 units/day for 30 days → strong velocity history.
    now = utcnow()
    for d in range(30):
        o = models.Order(
            restaurant_id=1, status=models.OrderStatus.SERVED,
            payment_method=models.PaymentMethod.CASH, is_paid=True,
            total=2000, created_at=now - timedelta(days=d),
        )
        db_session.add(o)
        db_session.flush()
        db_session.add(models.OrderItem(order_id=o.id, menu_item_id=1, quantity=2, unit_price=1000))
    db_session.commit()
    return db_session


def test_price_increase_suppresses_volume(seeded):
    r = run_simulation(seeded, 1, {"type": "price_change", "item_id": 1, "change_pct": 10})
    assert r["available"] is True
    assert r["deltas"]["sales_pct"] < 0                 # elasticity < 0
    assert r["projected"]["margin_pct"] > r["baseline"]["margin_pct"]
    assert r["change"]["new_price"] == 1100


def test_promo_lowers_price_and_lifts_volume(seeded):
    r = run_simulation(seeded, 1, {"type": "promo", "item_id": 1, "discount_pct": 10})
    assert r["change"]["new_price"] == 900
    assert r["deltas"]["sales_pct"] > 0                 # discount → more volume
    assert r["deltas"]["satisfaction_pct_points"] > 0


def test_verdict_blocks_a_change_that_breaks_the_margin_floor(seeded):
    # Drop price to 600 on a 400-cost item → 33% margin, under the 40% floor.
    r = run_simulation(seeded, 1, {"type": "price_change", "item_id": 1, "new_price": 600})
    assert r["projected"]["margin_pct"] < 40
    assert r["verdict"] == "NO"
    assert "floor" in r["verdict_reason"].lower()


def test_cost_rise_with_price_held_reduces_profit(seeded):
    r = run_simulation(seeded, 1, {"type": "cost_change", "item_id": 1, "new_cost": 600})
    assert r["available"] is True
    assert r["deltas"]["profit_cents_month"] < 0
    assert r["projected"]["margin_pct"] < r["baseline"]["margin_pct"]


def test_cost_rise_pass_through_lifts_price_to_hold_margin(seeded):
    r = run_simulation(seeded, 1, {"type": "cost_change", "item_id": 1,
                                   "new_cost": 600, "pass_through": True})
    assert r["available"] is True
    # margin held roughly at the original 60% (price lifted to ~1500).
    assert r["projected"]["margin_pct"] >= 55
    assert r["change"]["new_price"] > 1000


def test_unknown_item_degrades_gracefully(seeded):
    r = run_simulation(seeded, 1, {"type": "price_change", "item_id": 999, "new_price": 1200})
    assert r["available"] is False
    assert "not found" in r["error"].lower()


def test_unknown_type_is_rejected(seeded):
    r = run_simulation(seeded, 1, {"type": "teleport", "item_id": 1})
    assert r["available"] is False
