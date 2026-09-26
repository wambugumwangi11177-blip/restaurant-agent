"""Owner OS persistence, retries, source gates, and tenant boundaries."""
from datetime import timedelta
import importlib.util
from pathlib import Path

import auth
import models
from tests.test_overview_scope import scoped_owner  # noqa: F401
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def test_owner_conversations_preferences_retries_and_tenant_scope(client, db_session, scoped_owner, monkeypatch):
    from ai import llm_client

    owner, headers = scoped_owner
    monkeypatch.setattr(llm_client, "is_available", lambda: False)

    assert client.get("/api/v1/ai/os/preferences", headers=headers).json() == {"default_area": None}
    saved_preference = client.put("/api/v1/ai/os/preferences", headers=headers, json={"default_area": "health"})
    assert saved_preference.status_code == 200
    assert client.get("/api/v1/ai/os/preferences", headers=headers).json() == {"default_area": "health"}

    created = client.post("/api/v1/ai/os/conversations", headers=headers, json={"title": "Stock question"})
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    payload = {
        "question": "What will run out soon?", "answer_mode": "analysis", "topic": "stock",
        "conversation_id": conversation_id, "client_message_id": "owner-message-1234",
    }
    first = client.post("/api/v1/ai/chat", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["answer_type"] == "restaurant_analysis"
    assert first.json()["data_availability"] == "needs_source_verification"
    assert "clean reconciliation" in first.json()["answer_text"].lower()
    assert "Selected stock" not in first.text

    retried = client.post("/api/v1/ai/chat", headers=headers, json=payload)
    assert retried.status_code == 200, retried.text
    assert retried.json()["answer_text"] == first.json()["answer_text"]
    assert db_session.query(models.OwnerOSMessage).filter_by(conversation_id=conversation_id).count() == 2
    assert client.get(f"/api/v1/ai/os/conversations/{conversation_id}", headers=headers).json()["messages"]

    sibling_owner = models.User(
        tenant_id=owner.tenant_id, active_restaurant_id=owner.active_restaurant_id,
        email="another-owner@example.com", hashed_password="unused", role=models.Role.ADMIN,
    )
    db_session.add(sibling_owner)
    db_session.commit()
    sibling_headers = {"Authorization": f"Bearer {auth.create_access_token({'sub': sibling_owner.email})}"}
    hidden = client.get(f"/api/v1/ai/os/conversations/{conversation_id}", headers=sibling_headers)
    assert hidden.status_code == 404
    assert client.get("/api/v1/ai/os/preferences", headers=sibling_headers).json() == {"default_area": None}
    expired_headers = {"Authorization": f"Bearer {auth.create_access_token({'sub': owner.email}, expires_delta=timedelta(seconds=-1))}"}
    assert client.get("/api/v1/ai/os/preferences", headers=expired_headers).status_code == 401


def test_planned_area_question_never_runs_an_unrelated_handler(client, db_session, scoped_owner, monkeypatch):
    from ai import llm_client
    from routers import ai_ask

    _, headers = scoped_owner
    monkeypatch.setattr(llm_client, "is_available", lambda: False)
    monkeypatch.setitem(ai_ask._HANDLERS, "ops", lambda *_: (_ for _ in ()).throw(AssertionError("unrelated ops handler called")))
    response = client.post("/api/v1/ai/chat", headers=headers, json={
        "question": "Which supplier is most reliable?", "answer_mode": "analysis", "topic": "suppliers",
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_type"] == "planned_feature"
    assert body["data_availability"] == "planned_feature"
    assert "not available yet" in body["answer_text"].lower()
    assert body["grounded"]["data"]["availability"] == "planned_feature"

    design = client.post("/api/v1/ai/chat", headers=headers, json={
        "question": "Please change the front end layout on the Home page to make the daily summary easier to scan. password=should-not-leak",
        "answer_mode": "auto",
    })
    assert design.status_code == 200, design.text
    proposal = design.json()["proposal"]
    assert proposal["status"] == "proposal_not_applied"
    assert proposal["affected_page"] == "Home"
    assert proposal["can_apply"] is False
    assert proposal["layout"] and proposal["controls"] and proposal["mobile_behavior"]
    assert "should-not-leak" not in design.text
    saved_design = db_session.query(models.OwnerOSMessage).filter_by(role="user").order_by(models.OwnerOSMessage.id.desc()).first()
    assert saved_design and "should-not-leak" not in saved_design.content


def test_owner_os_migration_is_safe_after_model_create_all():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    migration_path = Path(__file__).parents[1] / "alembic/versions/049_add_owner_os_workspace.py"
    spec = importlib.util.spec_from_file_location("owner_os_workspace_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert {"owner_os_conversations", "owner_os_messages", "owner_os_preferences"}.issubset(
            set(inspect(connection).get_table_names())
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert not {"owner_os_conversations", "owner_os_messages", "owner_os_preferences"}.intersection(
            set(inspect(connection).get_table_names())
        )
    engine.dispose()
