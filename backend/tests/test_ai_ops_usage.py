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
                          prompt_version="2026-07-11.v1", input_tokens=100, output_tokens=50),
        models.TokenUsage(restaurant_id=restaurant_id, llm_model="openai/gpt-oss-120b",
                          prompt_version="2026-07-11.v1", input_tokens=200, output_tokens=80),
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

    # Prompt versioning: current version reported + per-version token breakdown.
    assert body["llm"]["current_prompt_version"] is not None
    assert body["llm"]["by_prompt_version"]["2026-07-11.v1"]["calls"] == 2

    agents = {a["agent"]: a for a in body["agents"]}
    assert agents["pricing"]["runs"] == 3
    assert agents["pricing"]["success_rate_pct"] == 66.7   # 2 of 3
    assert agents["pricing"]["p50_ms"] is not None
    assert agents["pricing"]["p95_ms"] is not None

    assert "grounding" in body
    # No evaluated predictions seeded → drift alarm reports insufficient_data,
    # never a false all-clear.
    assert body["quality_drift"]["status"] == "insufficient_data"


def test_quality_drift_flags_degrading_agent(db_session):
    from datetime import timedelta
    from ai.evaluation.tracker import get_quality_drift
    from time_utils import utcnow

    restaurant, _ = _tenant_user_restaurant(db_session, "drift")
    now = utcnow()

    def _pred(days_ago, err):
        # prediction_date is only bookkeeping here; evaluated_at drives the
        # recent-vs-prior split and error_pct is the signal.
        return models.AgentPrediction(
            restaurant_id=restaurant.id, agent_name="revenue_forecaster",
            prediction_type="daily_revenue", prediction_date=(now - timedelta(days=days_ago)).date(),
            predicted_value=1000, actual_value=1000, error_pct=err,
            evaluated_at=now - timedelta(days=days_ago),
        )

    # Window is 30d, split at the 15d midpoint. Prior half (20-24d ago): tight
    # errors. Recent half (2-4d ago): much worse.
    db_session.add_all([_pred(24, 4.0), _pred(22, 5.0), _pred(20, 6.0),
                        _pred(4, 30.0), _pred(3, 32.0), _pred(2, 34.0)])
    db_session.commit()

    drift = get_quality_drift(db_session, restaurant.id, days=30)
    assert drift["status"] == "drift_detected"
    flagged = {d["agent"] for d in drift["drifting"]}
    assert "revenue_forecaster" in flagged


def test_ai_usage_is_tenant_scoped(client, db_session):
    restaurant_a, token_a = _tenant_user_restaurant(db_session, "a")
    restaurant_b, _ = _tenant_user_restaurant(db_session, "b")
    _seed_ai_activity(db_session, restaurant_b.id)   # activity belongs to B only

    # A sees none of B's usage.
    r = client.get("/api/v1/ai/usage", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    assert r.json()["llm"]["calls"] == 0
    assert r.json()["agents"] == []
