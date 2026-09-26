from app.kernel.rbac import role_has


def test_other_workspace_records_are_invisible(client, make_workspace):
    a = make_workspace("alpha")
    b = make_workspace("beta")
    task = client.post("/api/v1/records/task", headers=a["h"], json={"title": "Alpha secret"}).json()

    assert client.get(f"/api/v1/records/task/{task['id']}", headers=b["h"]).status_code == 404
    assert client.patch(f"/api/v1/records/task/{task['id']}", headers=b["h"], json={"title": "pwned"}).status_code == 404
    assert client.delete(f"/api/v1/records/task/{task['id']}", headers=b["h"]).status_code == 404
    assert client.get("/api/v1/records/task", headers=b["h"]).json() == []
    note = client.post("/api/v1/records/note", headers=b["h"], json={"title": "beta note"}).json()
    link = client.post("/api/v1/links", headers=b["h"], json={
        "from_type": "note", "from_id": note["id"], "to_type": "task", "to_id": task["id"]})
    assert link.status_code == 404
    assert client.get(f"/api/v1/records/task/{task['id']}", headers=a["h"]).json()["title"] == "Alpha secret"


def test_other_workspace_memory_and_audit_are_invisible(client, make_workspace):
    a = make_workspace("alpha")
    b = make_workspace("beta")
    client.post("/api/v1/memory/documents", headers=a["h"], json={"title": "Pricing", "content": "Our zebra plan costs 900."})
    assert client.get("/api/v1/memory/search", headers=b["h"], params={"q": "zebra plan"}).json()["results"] == []
    assert client.get("/api/v1/memory/documents", headers=b["h"]).json() == []
    audit_b = client.get("/api/v1/audit", headers=b["h"]).json()
    assert all(row["entity_type"] != "document" for row in audit_b)


def test_role_permissions(client, make_workspace, add_member):
    w = make_workspace("acme")
    advisor = add_member(w["h"], "advisor", "adv@acme.example.com")
    contractor = add_member(w["h"], "contractor", "con@acme.example.com")
    staff = add_member(w["h"], "staff", "staff@acme.example.com")

    assert client.get("/api/v1/records/task", headers=advisor).status_code == 200
    assert client.post("/api/v1/records/task", headers=advisor, json={"title": "x"}).status_code == 403
    t = client.post("/api/v1/records/task", headers=contractor, json={"title": "x"})
    assert t.status_code == 201
    assert client.delete(f"/api/v1/records/task/{t.json()['id']}", headers=contractor).status_code == 403
    assert client.get("/api/v1/audit", headers=staff).status_code == 403
    assert client.post("/api/v1/members", headers=staff, json={
        "email": "z@acme.example.com", "full_name": "Z", "role": "founder", "password": "Correct-Horse-9-Battery"}).status_code == 403
    assert client.post("/api/v1/agents/echo/run", headers=advisor, json={"input": "hi"}).status_code == 403


def test_unknown_permission_fails_closed():
    assert role_has("founder", "no.such.permission") is False
    assert role_has("not-a-role", "records.read") is False
