"""
Orchestrator token metering writes to the dedicated token_usage table (its own
session), and does NOT pollute agent_messages (the outbound log / dashboard feed).
"""

from types import SimpleNamespace
import models
from ai.whatsapp import orchestrator


def _fake_end_turn_response():
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="Sales are looking good today.")],
        model="fake-model",
        usage=SimpleNamespace(input_tokens=123, output_tokens=45),
    )


def test_metering_writes_token_usage_not_agent_messages(db_session, monkeypatch):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    db_session.add(r)
    db_session.commit()

    from ai import llm_client
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "chat_with_tools", lambda **kwargs: _fake_end_turn_response())

    reply = orchestrator.handle_natural_language(db_session, 1, "how are things going?")
    assert "good" in reply.lower()

    usage_rows = db_session.query(models.TokenUsage).all()
    assert len(usage_rows) == 1
    assert usage_rows[0].input_tokens == 123
    assert usage_rows[0].output_tokens == 45
    assert usage_rows[0].llm_model == "fake-model"

    # Must not have written a metering row into the outbound-message log.
    metering_msgs = db_session.query(models.AgentMessage).filter(
        models.AgentMessage.message_type == "orchestrator_turn"
    ).all()
    assert metering_msgs == []
