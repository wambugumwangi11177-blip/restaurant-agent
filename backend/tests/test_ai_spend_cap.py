"""
AI/LLM spend cap + rate limiting (tech-debt D14). Before this, /ai/* endpoints
metered token spend to TokenUsage but never blocked on it, and carried no rate
limit despite being the only LLM-invoking routes in the platform. These tests
prove: the DB-backed budget calculation actually trips at the cap, narrate()
short-circuits before ever reaching the paid LLM call once blocked, /ai/usage
surfaces the budget, and the rate limiter is actually wired to an LLM route
(not just configured, per this repo's own precedent bug in rate_limit.py).
"""

import models
from ai import spend_guard
from ai.reasoning import narrator


def _register_and_login(client, email="spendcap@example.com"):
    client.post("/api/v1/auth/register", json={
        "email": email, "password": "CorrectHorseBattery1!", "tenant_name": "Spend Cap Co",
    })
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "CorrectHorseBattery1!"})
    return resp.json()["access_token"]


def _seed_usage(db_session, restaurant_id: int, model: str, input_tokens: int, output_tokens: int):
    db_session.add(models.TokenUsage(
        restaurant_id=restaurant_id, llm_model=model,
        input_tokens=input_tokens, output_tokens=output_tokens,
    ))
    db_session.commit()


def test_budget_status_blocks_once_daily_cap_exceeded(db_session, monkeypatch):
    tenant = models.Tenant(name="T1")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R1", address="x")
    db_session.add(restaurant)
    db_session.commit()

    monkeypatch.setattr(spend_guard, "DAILY_CAP_USD", 0.01)
    monkeypatch.setattr(spend_guard, "MONTHLY_CAP_USD", 60.0)

    # Well over $0.01 at claude-sonnet list prices ($3/mtok in, $15/mtok out).
    _seed_usage(db_session, restaurant.id, "claude-sonnet", 10_000, 10_000)

    status = spend_guard.get_budget_status(restaurant.id, db=db_session)
    assert status["blocked"] is True
    assert status["daily_spend_usd"] > status["daily_cap_usd"]


def test_budget_status_not_blocked_under_cap(db_session):
    tenant = models.Tenant(name="T2")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R2", address="x")
    db_session.add(restaurant)
    db_session.commit()

    _seed_usage(db_session, restaurant.id, "claude-haiku", 100, 100)

    status = spend_guard.get_budget_status(restaurant.id, db=db_session)
    assert status["blocked"] is False
    assert status["daily_remaining_usd"] > 0


def test_narrate_short_circuits_before_llm_call_when_blocked(monkeypatch):
    import ai.llm_client as llm_client

    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(spend_guard, "get_budget_status", lambda restaurant_id, db=None: {"blocked": True})

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("chat_with_usage must not be called once the spend cap has blocked the tenant")

    monkeypatch.setattr(llm_client, "chat_with_usage", _fail_if_called)

    result = narrator.narrate({"summary": "x"}, "profit", restaurant_id=1)
    assert result is None


def test_ai_usage_endpoint_surfaces_budget(client, db_session):
    token = _register_and_login(client)
    resp = client.get("/api/v1/ai/usage", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "budget" in body
    for key in ("daily_spend_usd", "daily_cap_usd", "monthly_spend_usd", "monthly_cap_usd", "blocked"):
        assert key in body["budget"]


def test_ai_pricing_rate_limit_returns_429_after_threshold(client, db_session):
    """Rate limit is 20/minute on /ai/pricing (see routers/ai.py)."""
    token = _register_and_login(client, email="ratelimitai@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    statuses = []
    for _ in range(22):
        resp = client.get("/api/v1/ai/pricing?narrate=false", headers=headers)
        statuses.append(resp.status_code)

    assert 429 in statuses
