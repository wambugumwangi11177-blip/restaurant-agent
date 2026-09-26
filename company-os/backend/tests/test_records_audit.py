import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.kernel.models import AuditLog, Event


def test_crud_writes_audit_and_events(client, make_workspace, db):
    w = make_workspace("acme")
    t = client.post("/api/v1/records/task", headers=w["h"], json={"title": "Draft SOW", "priority": "high"})
    assert t.status_code == 201
    tid = t.json()["id"]
    u = client.patch(f"/api/v1/records/task/{tid}", headers=w["h"], json={"status": "done"})
    assert u.json()["completed_at"] is not None
    assert client.patch(f"/api/v1/records/task/{tid}", headers=w["h"], json={"status": "open"}).json()["completed_at"] is None
    assert client.delete(f"/api/v1/records/task/{tid}", headers=w["h"]).status_code == 204

    actions = [a.action for a in db.query(AuditLog).filter(AuditLog.entity_type == "task").order_by(AuditLog.id)]
    assert actions == ["record.create", "record.update", "record.update", "record.delete"]
    update = db.query(AuditLog).filter(AuditLog.action == "record.update").order_by(AuditLog.id).first()
    assert update.changes["status"] == {"from": "open", "to": "done"}
    events = [e.type for e in db.query(Event).filter(Event.entity_type == "task").order_by(Event.id)]
    assert events == ["record.created", "record.updated", "record.updated", "record.deleted"]


def test_person_pii_never_enters_audit(client, make_workspace, db):
    w = make_workspace("acme")
    p = client.post("/api/v1/records/person", headers=w["h"], json={
        "full_name": "Wanjiku Kamau", "email": "wanjiku@example.co.ke", "phone": "0712345678", "title": "Owner"})
    assert p.status_code == 201
    assert p.json()["phone"] == "254712345678"
    client.patch(f"/api/v1/records/person/{p.json()['id']}", headers=w["h"], json={"email": "w.kamau@example.co.ke"})
    blob = json.dumps([a.changes for a in db.query(AuditLog).all()])
    for secret in ("Wanjiku", "wanjiku@example.co.ke", "w.kamau@example.co.ke", "254712345678", "0712345678"):
        assert secret not in blob
    create = db.query(AuditLog).filter(AuditLog.action == "record.create", AuditLog.entity_type == "person").one()
    assert create.changes["email"] == {"changed": True}
    assert create.changes["title"] == {"from": None, "to": "Owner"}


def test_audit_log_is_append_only_in_the_database(client, make_workspace, db):
    make_workspace("acme")
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_log SET action = 'tampered'"))
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_log"))
    db.rollback()


def test_validation_rejects_unknown_fields_and_types(client, make_workspace):
    w = make_workspace("acme")
    assert client.post("/api/v1/records/task", headers=w["h"], json={"title": "x", "colour": "red"}).status_code == 422
    assert client.post("/api/v1/records/task", headers=w["h"], json={"title": "x", "status": "maybe"}).status_code == 422
    assert client.post("/api/v1/records/spaceship", headers=w["h"], json={"title": "x"}).status_code == 404
    assert client.post("/api/v1/records/task", headers=w["h"], json={"title": "x", "assignee_user_id": 99999}).status_code == 422


def test_links(client, make_workspace):
    w = make_workspace("acme")
    org = client.post("/api/v1/records/organization", headers=w["h"], json={"name": "Vibanda"}).json()
    person = client.post("/api/v1/records/person", headers=w["h"], json={"full_name": "Manager"}).json()
    body = {"from_type": "person", "from_id": person["id"], "to_type": "organization", "to_id": org["id"], "relation": "works_at"}
    assert client.post("/api/v1/links", headers=w["h"], json=body).status_code == 201
    assert client.post("/api/v1/links", headers=w["h"], json=body).status_code == 409
    self_link = {**body, "to_type": "person", "to_id": person["id"]}
    assert client.post("/api/v1/links", headers=w["h"], json=self_link).status_code == 422
    links = client.get(f"/api/v1/records/organization/{org['id']}/links", headers=w["h"]).json()
    assert len(links) == 1 and links[0]["relation"] == "works_at"
    client.delete(f"/api/v1/records/person/{person['id']}", headers=w["h"])
    assert client.get(f"/api/v1/records/organization/{org['id']}/links", headers=w["h"]).json() == []


def test_search_filter(client, make_workspace):
    w = make_workspace("acme")
    for name in ("Vibanda", "Mama Oliech", "Java House"):
        client.post("/api/v1/records/organization", headers=w["h"], json={"name": name})
    names = [o["name"] for o in client.get("/api/v1/records/organization", headers=w["h"], params={"q": "vib"}).json()]
    assert names == ["Vibanda"]
