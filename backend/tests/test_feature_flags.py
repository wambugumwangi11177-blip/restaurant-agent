"""
Feature flags (Phase 7, 2026-07-12): env-driven, fail-safe defaults, and the
ai_narration kill-switch actually stops LLM narration.
"""

import feature_flags
from ai.reasoning import narrator


def test_registered_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("FEATURE_AI_NARRATION", raising=False)
    monkeypatch.delenv("FEATURE_CONVERSATION_MEMORY", raising=False)
    assert feature_flags.is_enabled("ai_narration") is True          # default on
    assert feature_flags.is_enabled("conversation_memory") is False   # default off


def test_env_override_truthy_and_falsy(monkeypatch):
    for val in ("true", "1", "YES", "on"):
        monkeypatch.setenv("FEATURE_CONVERSATION_MEMORY", val)
        assert feature_flags.is_enabled("conversation_memory") is True
    for val in ("false", "0", "no", "off", "garbage"):
        monkeypatch.setenv("FEATURE_CONVERSATION_MEMORY", val)
        assert feature_flags.is_enabled("conversation_memory") is False


def test_unregistered_flag_uses_supplied_default(monkeypatch):
    monkeypatch.delenv("FEATURE_NOPE", raising=False)
    assert feature_flags.is_enabled("nope") is False
    assert feature_flags.is_enabled("nope", default=True) is True


def test_all_flags_and_details_shape():
    flags = feature_flags.all_flags()
    assert "ai_narration" in flags and isinstance(flags["ai_narration"], bool)
    details = feature_flags.flag_details()
    assert all({"name", "enabled", "description"} <= set(d) for d in details)


def test_ai_narration_killswitch_stops_narration(monkeypatch):
    """With the switch off, narrate() returns None even when a provider is 'up'."""
    from ai import llm_client
    narrator._cache.clear()
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    # Would raise if the LLM were actually called — proves we short-circuit first.
    monkeypatch.setattr(llm_client, "chat_with_usage",
                        lambda **k: (_ for _ in ()).throw(AssertionError("LLM must not be called")))

    monkeypatch.setenv("FEATURE_AI_NARRATION", "false")
    assert narrator.narrate({"summary": {}}, "profit") is None


def test_flags_endpoint_returns_state(client, db_session, monkeypatch):
    import auth
    import models
    tenant = models.Tenant(name="FlagCo")
    db_session.add(tenant); db_session.commit()
    user = models.User(tenant_id=tenant.id, email="flag@e.com",
                       hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN)
    db_session.add(user)
    db_session.add(models.Restaurant(tenant_id=tenant.id, name="R", address="x"))
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})

    r = client.get("/api/v1/flags/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "ai_narration" in r.json()["flags"]
