"""
Orchestrator token metering writes to the dedicated token_usage table (its own
session), and does NOT pollute agent_messages (the outbound log / dashboard feed).
"""

from types import SimpleNamespace
import models
from ai.whatsapp import orchestrator


def _tenant_id(db) -> int:
    tenant = models.Tenant(name="Metering Tenant")
    db.add(tenant)
    db.commit()
    return tenant.id


def _fake_end_turn_response():
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="Sales are looking good today.")],
        model="fake-model",
        usage=SimpleNamespace(input_tokens=123, output_tokens=45),
    )


def test_metering_writes_token_usage_not_agent_messages(db_session, monkeypatch):
    r = models.Restaurant(id=1, tenant_id=_tenant_id(db_session), name="Test Bistro", address="x")
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


def test_pii_scrubbed_before_reaching_llm(db_session, monkeypatch):
    """A phone number in the owner's message must never reach the LLM (P4)."""
    r = models.Restaurant(id=1, tenant_id=_tenant_id(db_session), name="Test Bistro", address="x")
    db_session.add(r)
    db_session.commit()

    captured = {}

    def _capture(**kwargs):
        captured["messages"] = kwargs.get("messages")
        return _fake_end_turn_response()

    from ai import llm_client
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "chat_with_tools", _capture)

    orchestrator.handle_natural_language(
        db_session, 1, "text a promo to 0712345678 and their pin is 4321"
    )

    sent = str(captured["messages"])
    assert "0712345678" not in sent
    assert "4321" not in sent
    assert "[phone]" in sent
