"""
WhatsApp short-term conversation memory (Phase 6, 2026-07-12).

Flag-gated (FEATURE_CONVERSATION_MEMORY): off = stateless (unchanged), on =
recent turns are loaded into the LLM context and new turns persisted.
"""

from types import SimpleNamespace

import models
from ai.whatsapp import orchestrator


def _end_turn(text="Here you go."):
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
        model="fake-model",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def _restaurant(db):
    r = models.Restaurant(id=1, tenant_id=None, name="Mem Bistro", address="x")
    db.add(r); db.commit()
    return r


def test_flag_off_is_stateless(db_session, monkeypatch):
    monkeypatch.delenv("FEATURE_CONVERSATION_MEMORY", raising=False)
    _restaurant(db_session)

    captured = {}
    from ai import llm_client
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "chat_with_tools",
                        lambda **kw: (captured.__setitem__("messages", kw["messages"]), _end_turn())[1])

    orchestrator.handle_natural_language(db_session, 1, "how were sales?")

    # Only the current message, no history.
    assert len(captured["messages"]) == 1
    # Nothing persisted.
    assert db_session.query(models.ConversationTurn).count() == 0


def test_flag_on_loads_history_and_persists(db_session, monkeypatch):
    monkeypatch.setenv("FEATURE_CONVERSATION_MEMORY", "true")
    _restaurant(db_session)

    # Seed one prior exchange.
    db_session.add(models.ConversationTurn(restaurant_id=1, role="user", content="earlier question"))
    db_session.add(models.ConversationTurn(restaurant_id=1, role="assistant", content="earlier answer"))
    db_session.commit()

    captured = {}
    from ai import llm_client
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "chat_with_tools",
                        lambda **kw: (captured.__setitem__("messages", kw["messages"]), _end_turn("Sales were steady."))[1])

    orchestrator.handle_natural_language(db_session, 1, "and this week?")

    sent = captured["messages"]
    # History (2 seeded) is prepended, current message last.
    assert [m["content"] for m in sent[:2]] == ["earlier question", "earlier answer"]
    assert sent[-1]["content"] == "<owner_message>\nand this week?\n</owner_message>"

    # The new exchange was persisted: 2 seeded + user + assistant = 4.
    turns = db_session.query(models.ConversationTurn).order_by(models.ConversationTurn.id).all()
    assert len(turns) == 4
    assert turns[-2].role == "user" and turns[-2].content == "and this week?"
    assert turns[-1].role == "assistant" and turns[-1].content == "Sales were steady."
