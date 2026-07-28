"""
The CEO / Strategy Agent (Phase 3).

Two paths must both hold:
  1. With no LLM provider / feature off (the default in tests), run_strategy
     DEGRADES to a deterministic plan built from the ranked decisions — never an
     error, never a crash.
  2. The final-JSON parser is robust to the ways a smaller model actually
     replies (bare JSON, ```json fences, or prose with an embedded object).

The LLM tool-loop itself is exercised with a stub client so we assert the loop
mechanics (tools fire, trace is recorded, tokens metered, output grounded)
without a network call.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest

import models
from time_utils import utcnow
from ai.orchestrator import strategist


@pytest.fixture
def seeded(db_session):
    db = db_session
    tenant = models.Tenant(name="Strategist Tenant")
    db.add(tenant)
    db.commit()
    db.add(models.Restaurant(id=1, tenant_id=tenant.id, name="Strat", address="x"))
    # one below-floor item → a deterministic REPRICE decision exists
    db.add(models.MenuItem(id=1, restaurant_id=1, name="ThinBurger",
                           price=1000, cost_price=900, category="main"))
    db.commit()
    for d in range(8):
        o = models.Order(restaurant_id=1, status=models.OrderStatus.SERVED,
                         payment_method=models.PaymentMethod.CASH, is_paid=True,
                         total=1000, created_at=utcnow() - timedelta(days=d + 1))
        db.add(o)
        db.flush()
        db.add(models.OrderItem(order_id=o.id, menu_item_id=1, quantity=1, unit_price=1000))
    db.commit()
    return db


# ── parser robustness ──────────────────────────────────────────────────────────

def test_parser_handles_bare_json():
    s = strategist._parse_strategy('{"headline": "do x", "steps": [], "risks": []}')
    assert s["headline"] == "do x"


def test_parser_handles_json_fence():
    s = strategist._parse_strategy('```json\n{"headline": "hi", "steps": []}\n```')
    assert s["headline"] == "hi"
    assert s["risks"] == []          # defaulted


def test_parser_handles_prose_wrapped_json():
    s = strategist._parse_strategy('Here is my plan: {"headline": "grow drinks", "steps": []} thanks')
    assert s["headline"] == "grow drinks"


def test_parser_falls_back_to_text_headline():
    s = strategist._parse_strategy("no json here at all")
    assert "no json" in s["headline"]
    assert s["steps"] == []


# ── deterministic fallback (no LLM configured) ─────────────────────────────────

def test_run_strategy_degrades_without_llm(seeded):
    out = strategist.run_strategy(seeded, 1, "increase monthly profit")
    assert out["available"] is True
    assert out["mode"] == "deterministic"
    assert out["strategy"]["steps"], "expected at least one deterministic step"
    assert "note" in out


def test_run_strategy_rejects_empty_goal(seeded):
    out = strategist.run_strategy(seeded, 1, "   ")
    assert out["available"] is False


# ── LLM path with a stub client ────────────────────────────────────────────────

def test_llm_strategy_runs_tool_loop_and_grounds(seeded, monkeypatch):
    """Stub the provider: turn 1 calls list_decisions, turn 2 returns final JSON.
    Assert the trace records the tool call, tokens are metered, and the plan is
    grounded (an invented number in the model's reply is redacted)."""
    import feature_flags
    monkeypatch.setattr(feature_flags, "is_enabled", lambda flag, default=None: True)

    from ai import llm_client
    monkeypatch.setattr(llm_client, "is_available", lambda: True)

    calls = {"n": 0}

    def fake_chat_with_tools(messages, tools, system="", max_tokens=1024, model=None, tier=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return SimpleNamespace(
                stop_reason="tool_use",
                content=[SimpleNamespace(type="tool_use", id="t1", name="list_decisions", input={})],
                model="stub-model",
                usage=SimpleNamespace(input_tokens=100, output_tokens=20),
            )
        # Second turn: final answer. Include a fabricated "KES 999,999" that is
        # NOT in any tool result → grounding must redact it.
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text='{"headline": "Fix the margin on ThinBurger, worth KES 999,999", "steps": [{"action": "Reprice ThinBurger", "why": "below floor", "expected_impact": "better margin"}], "risks": []}')],
            model="stub-model",
            usage=SimpleNamespace(input_tokens=200, output_tokens=40),
        )

    monkeypatch.setattr(llm_client, "chat_with_tools", fake_chat_with_tools)

    out = strategist.run_strategy(seeded, 1, "raise profit")
    assert out["available"] is True
    assert out["mode"] == "llm"
    assert any(t["tool"] == "list_decisions" for t in out["trace"])
    assert out["tokens"]["input"] == 300 and out["tokens"]["output"] == 60
    # the fabricated figure must have been redacted from the headline
    assert "999,999" not in out["strategy"]["headline"]
    # token usage + audit log were persisted
    assert seeded.query(models.TokenUsage).filter_by(restaurant_id=1).count() >= 1
    assert seeded.query(models.AgentAuditLog).filter_by(action_type="strategy_generated").count() == 1


# ── HTTP route (deterministic path, real app) ──────────────────────────────────

def test_strategy_route_returns_plan(client, db_session):
    import auth
    tenant = models.Tenant(name="Strat Tenant")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(tenant_id=tenant.id, email="ceo@example.com",
                       hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN)
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Strat Grill", address="Nairobi")
    db_session.add_all([user, restaurant])
    db_session.commit()
    headers = {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email})}"}

    resp = client.post("/ai/strategy", headers=headers,
                       json={"goal": "increase monthly profit by KES 50,000"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is True
    assert "strategy" in body and "steps" in body["strategy"]


def test_strategy_route_requires_auth(client):
    resp = client.post("/ai/strategy", json={"goal": "x"})
    assert resp.status_code in (401, 403)
