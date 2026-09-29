"""Demo Restaurant records its data directly: it never waits on MacSoft.

Vibanda Village keeps its owner views empty until a MacSoft delivery has passed
a clean reconcile. Demo Restaurant is the same owner experience for a restaurant
whose system of record is this app, so its source is reported as "direct" and
its own records are trusted as recorded.
"""
import secrets

import models
from routers.overview import records_directly, source_is_trusted
from tests.test_overview_scope import scoped_owner  # noqa: F401


def test_source_trust_rules():
    assert source_is_trusted({"state": "direct", "reconciled": True})
    assert source_is_trusted({"state": "receiving", "reconciled": True})
    assert not source_is_trusted({"state": "receiving", "reconciled": False})
    assert not source_is_trusted({"state": "awaiting_first_delivery", "reconciled": False})
    assert not source_is_trusted({"state": "unavailable", "reconciled": False})


def test_only_the_demo_tenant_records_directly(db_session):
    demo = models.Tenant(name="Demo Restaurant")
    vibanda = models.Tenant(name="Vibanda Village")
    db_session.add_all([demo, vibanda])
    db_session.commit()
    assert records_directly(db_session, demo.id)
    assert not records_directly(db_session, vibanda.id)
    assert not records_directly(db_session, None)


def test_demo_overview_is_live_without_any_macsoft_delivery(client):
    # No mirror tables, no MacSoft source row, no data: a fresh signup.
    resp = client.post("/api/v1/auth/register", json={
        "email": f"demo{secrets.token_hex(4)}@example.com",
        "password": "CorrectHorseBattery1!", "tenant_name": "Demo Restaurant",
    })
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    body = client.get("/api/v1/overview/today", headers=headers).json()
    provenance = body["data_provenance"]
    assert provenance["source_connection"]["state"] == "direct"
    assert provenance["integration_verified"] is True
    assert "Recorded directly in this system" in provenance["notice"]
    assert body["source_status"]["integration"]["state"] == "direct"
    assert body["restaurant_name"] == "Demo Restaurant"
    assert body["revenue"]["orders"] == 0


def test_demo_owner_os_analyses_recorded_data_without_reconciliation(client, db_session, scoped_owner, monkeypatch):
    from ai import llm_client

    owner, headers = scoped_owner
    db_session.query(models.Tenant).filter_by(id=owner.tenant_id).update({"name": "Demo Restaurant"})
    db_session.commit()
    monkeypatch.setattr(llm_client, "is_available", lambda: False)

    response = client.post("/api/v1/ai/chat", headers=headers, json={
        "question": "What will run out soon?", "answer_mode": "analysis", "topic": "stock",
    })
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["answer_type"] == "restaurant_analysis"
    assert answer["data_availability"] == "available"
    assert "reconciliation" not in (answer["answer_text"] or "").lower()
