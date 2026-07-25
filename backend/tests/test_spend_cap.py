"""
ai/spend_cap.py — daily LLM spend circuit-breaker (audit remediation, Tier 3
item 7). GET /ai/usage was read-only telemetry with nothing to actually stop a
runaway loop or abusive caller once spend crossed any threshold; this is the
missing enforcement half, reusing TokenUsage (already indexed on
(restaurant_id, created_at)) and cost_model.cost_usd (already converts tokens
to dollars) — no new table.
"""

from fastapi import HTTPException
import pytest

import models
from routers.deps import get_or_create_restaurant
from ai.spend_cap import today_spend_usd, check_spend_cap
from time_utils import utcnow


def _make_tenant_user_restaurant(db_session, name="Spend Test"):
    tenant = models.Tenant(name=name)
    db_session.add(tenant)
    db_session.commit()
    user = models.User(tenant_id=tenant.id, email=f"{name}@example.com", hashed_password="x")
    db_session.add(user)
    db_session.commit()
    restaurant = get_or_create_restaurant(db_session, user)
    return tenant, user, restaurant


def _seed_usage(db_session, restaurant_id, model, input_tokens, output_tokens, when=None):
    row = models.TokenUsage(
        restaurant_id=restaurant_id,
        llm_model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        created_at=when or utcnow(),
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_today_spend_usd_sums_only_todays_rows_for_this_restaurant(db_session):
    _, _, restaurant = _make_tenant_user_restaurant(db_session)
    # Today, this restaurant — counted.
    _seed_usage(db_session, restaurant.id, "claude-haiku", 1_000_000, 0)
    # Yesterday, this restaurant — excluded.
    _seed_usage(
        db_session, restaurant.id, "claude-haiku", 1_000_000, 0,
        when=utcnow().replace(hour=12) - __import__("datetime").timedelta(days=1),
    )
    # Today, a DIFFERENT restaurant — excluded.
    _, _, other_restaurant = _make_tenant_user_restaurant(db_session, name="Other Restaurant")
    _seed_usage(db_session, other_restaurant.id, "claude-haiku", 1_000_000, 0)

    spent = today_spend_usd(db_session, restaurant.id)

    # claude-haiku: $1.0/Mtok input — one qualifying row of 1M input tokens.
    assert round(spent, 2) == 1.0


def test_check_spend_cap_passes_when_under_cap(db_session, monkeypatch):
    monkeypatch.setenv("DAILY_LLM_SPEND_CAP_USD", "20.0")
    import ai.spend_cap as spend_cap
    monkeypatch.setattr(spend_cap, "DAILY_LLM_SPEND_CAP_USD", 20.0)

    _, user, restaurant = _make_tenant_user_restaurant(db_session)
    _seed_usage(db_session, restaurant.id, "claude-haiku", 1_000_000, 0)  # $1.0

    check_spend_cap(user, db_session)  # must not raise


def test_check_spend_cap_raises_429_when_cap_reached(db_session, monkeypatch):
    import ai.spend_cap as spend_cap
    monkeypatch.setattr(spend_cap, "DAILY_LLM_SPEND_CAP_USD", 0.50)

    _, user, restaurant = _make_tenant_user_restaurant(db_session)
    # claude-haiku input: $1.0/Mtok — 1M tokens = $1.00, over the $0.50 cap.
    _seed_usage(db_session, restaurant.id, "claude-haiku", 1_000_000, 0)

    with pytest.raises(HTTPException) as exc_info:
        check_spend_cap(user, db_session)

    assert exc_info.value.status_code == 429
    assert "spend cap" in exc_info.value.detail.lower()
