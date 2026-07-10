"""
backend/tests/test_ai_ops_usage.py
──────────────────────────────────────
GET /api/v1/ai/usage — the AIOps surface that aggregates already-metered LLM
token spend, agent latency/reliability, and grounding into a tenant-scoped view.
"""

import auth
import models


def _tenant_user_restaurant(db_session, suffix="a"):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(tenant_id=tenant.id, email=f"o{suffix}@e.com",
                       hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
                       token_version=0)
    db_session.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return restaurant, token


def _seed_ai_activity(db_session, restaurant_id):
    db_session.add_all([
        models.TokenUsage(restaurant_id=restaurant_id, llm_model="llama-3.1-8b-instant",
                          input_tokens=100, output_tokens=50),
        models.TokenUsage(restaurant_id=restaurant_id, llm_model="openai/gpt-oss-120b",
                          input_tokens=200, output_tokens=80),
        models.AgentExecution(restaurant_id=restaurant_id, agent_name="pricing",
                              function_name="get_pricing", success=True, execution_ms=100),
        models.AgentExecution(restaurant_id=restaurant_id, agent_name="pricing",
                              function_name="get_pricing", success=True, execution_ms=300),
        models.AgentExecution(restaurant_id=restaurant_id, agent_name="pricing",
                              function_name="get_pricing", success=False, execution_ms=200),
    ])
    db_session.commit()


def test_ai_usage_aggregates_tokens_latency_and_reliability(client, db_session):
    restaurant, token = _tenant_user_restaurant(db_session)
    _seed_ai_activity(db_session, restaurant.id)

    r = client.get("/api/v1/ai/usage", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()

    assert body["llm"]["calls"] == 2
    assert body["llm"]["input_tokens"] == 300
    assert body["llm"]["output_tokens"] == 130
    assert set(body["llm"]["by_model"]) == {"llama-3.1-8b-instant", "openai/gpt-oss-120b"}

    agents = {a["agent"]: a for a in body["agents"]}
    assert agents["pricing"]["runs"] == 3
    assert agents["pricing"]["success_rate_pct"] == 66.7   # 2 of 3
    assert agents["pricing"]["p50_ms"] is not None
    assert agents["pricing"]["p95_ms"] is not None

    assert "grounding" in body


def test_ai_usage_is_tenant_scoped(client, db_session):
    restaurant_a, token_a = _tenant_user_restaurant(db_session, "a")
    restaurant_b, _ = _tenant_user_restaurant(db_session, "b")
    _seed_ai_activity(db_session, restaurant_b.id)   # activity belongs to B only

    # A sees none of B's usage.
    r = client.get("/api/v1/ai/usage", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    assert r.json()["llm"]["calls"] == 0
    assert r.json()["agents"] == []
