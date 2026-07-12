"""
Decision Intelligence — the ranking math and the cross-agent adapters.

The ranking is the thing an owner reads as "do this first", so its ordering must
be deterministic, bounded, and biased the way the docstring promises: quantified
money-makers beat equal-footing unquantified items; higher confidence, lower
risk, and lower effort all raise a decision.
"""

from datetime import timedelta

import models
from time_utils import utcnow
from ai.decisions.model import Decision
from ai.decisions import ranking, get_ranked_decisions


def _d(**kw) -> Decision:
    base = dict(
        agent="a", category="c", action="do x", rationale="because",
        confidence_pct=70, risk=2, difficulty=2,
    )
    base.update(kw)
    return Decision(**base)


# ── model invariants ──────────────────────────────────────────────────────────

def test_decision_clamps_out_of_range_inputs():
    d = _d(confidence_pct=250, risk=9, difficulty=0)
    assert d.confidence_pct == 100
    assert d.risk == 5
    assert d.difficulty == 1


def test_quantified_flag_tracks_impact():
    assert _d(impact_cents_month=5000).quantified is True
    assert _d(impact_cents_month=None).quantified is False


def test_to_dict_star_meters():
    d = _d(risk=4, difficulty=1)
    row = d.to_dict()
    assert row["risk_stars"] == 4
    assert row["ease_stars"] == 5   # 6 - difficulty


# ── scoring / ordering ─────────────────────────────────────────────────────────

def test_score_is_bounded_zero_to_one():
    for conf in (0, 50, 100):
        for risk in (1, 3, 5):
            for diff in (1, 3, 5):
                for impact in (None, 0, 1000, 10**9):
                    s = ranking.score(_d(confidence_pct=conf, risk=risk,
                                         difficulty=diff, impact_cents_month=impact))
                    assert 0.0 <= s <= 1.0


def test_quantified_beats_equal_unquantified():
    """Two identical decisions except one has real monthly impact — it ranks first."""
    with_money = _d(impact_cents_month=ranking.IMPACT_REFERENCE_CENTS)
    without = _d(impact_cents_month=None)
    ranked = ranking.rank([without, with_money])
    assert ranked[0]["impact_cents_month"] == ranking.IMPACT_REFERENCE_CENTS
    assert ranked[0]["rank"] == 1


def test_lower_risk_and_effort_rank_higher_all_else_equal():
    safe_easy = _d(risk=1, difficulty=1)
    risky_hard = _d(risk=5, difficulty=5)
    ranked = ranking.rank([risky_hard, safe_easy])
    assert ranked[0]["risk"] == 1 and ranked[0]["difficulty"] == 1


def test_ranking_is_deterministic_and_ranks_are_1_based():
    ds = [_d(confidence_pct=c) for c in (40, 90, 60)]
    r1 = ranking.rank(ds)
    r2 = ranking.rank(ds)
    assert [x["priority_score"] for x in r1] == [x["priority_score"] for x in r2]
    assert [x["rank"] for x in r1] == [1, 2, 3]


def test_impact_stars_scale():
    assert ranking.impact_stars(None) == 0
    assert ranking.impact_stars(0) == 0
    assert 1 <= ranking.impact_stars(1000) <= 5
    assert ranking.impact_stars(ranking.IMPACT_REFERENCE_CENTS * 10) == 5


# ── end-to-end adapter integration against a real (SQLite) DB ──────────────────

def _seed_restaurant_with_below_floor_item(db):
    """A restaurant with one item priced below the 40% margin floor + enough
    order history to trigger a deterministic REPRICE decision from pricing."""
    db.add(models.Restaurant(id=1, tenant_id=None, name="Kibanda", address="x"))
    # cost 900 on price 1000 → 10% margin, far below the 40% floor → REPRICE.
    db.add(models.MenuItem(id=1, restaurant_id=1, name="ThinBurger",
                           price=1000, cost_price=900, category="main"))
    db.commit()
    # Need >= MIN_ORDERS_FOR_VELOCITY (5) orders for the item to be analysed.
    for i in range(8):
        o = models.Order(
            restaurant_id=1, status=models.OrderStatus.SERVED,
            payment_method=models.PaymentMethod.CASH, is_paid=True,
            total=1000, created_at=utcnow() - timedelta(days=i + 1),
        )
        db.add(o)
        db.flush()
        db.add(models.OrderItem(order_id=o.id, menu_item_id=1, quantity=1, unit_price=1000))
    db.commit()


def test_collect_decisions_surfaces_a_pricing_reprice(db_session):
    _seed_restaurant_with_below_floor_item(db_session)
    payload = get_ranked_decisions(db_session, 1)

    assert payload["summary"]["total_decisions"] >= 1
    pricing = [d for d in payload["decisions"] if d["category"] == "pricing"]
    assert pricing, "expected a pricing decision for the below-floor item"
    top = pricing[0]
    assert top["agent"] == "pricing_intelligence"
    assert top["quantified"] is True          # pricing carries a monetary impact
    assert top["entity_type"] == "menu_item"
    assert 0 <= top["priority_score"] <= 100


def test_empty_restaurant_yields_no_decisions_without_crashing(db_session):
    db_session.add(models.Restaurant(id=1, tenant_id=None, name="Empty", address="x"))
    db_session.commit()
    payload = get_ranked_decisions(db_session, 1)
    assert payload["summary"]["total_decisions"] == 0
    assert payload["decisions"] == []
