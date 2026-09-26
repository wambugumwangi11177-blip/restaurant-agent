"""Departments 7 (Marketing), 8 (Product), 9 (People)."""

from datetime import date, timedelta

from app.kernel.models import Note
from tests.conftest import llm_turn

TODAY = date.today()


def test_case_study_requires_consent(client, make_workspace, scripted_llm, db):
    w = make_workspace("acme")
    h = w["h"]
    org = client.post("/api/v1/records/organization", headers=h, json={"name": "Vibanda"}).json()
    pr = client.post("/api/v1/records/project", headers=h, json={"title": "Vibanda POS", "organization_id": org["id"]}).json()
    cs = client.post("/api/v1/records/content_piece", headers=h, json={"title": "Vibanda story", "kind": "case_study", "organization_id": org["id"]}).json()
    assert client.patch(f"/api/v1/records/content_piece/{cs['id']}", headers=h, json={"status": "scheduled"}).status_code == 409

    def run():
        scripted_llm["script"][:] = [
            llm_turn(uses=[("get_project_story", {"project_id": pr["id"]})]),
            llm_turn(uses=[("save_case_study_draft", {"client_name": "Vibanda", "body": "Draft…"})]),
            llm_turn(text="ok"),
        ]
        return client.post("/api/v1/agents/case_study_drafter/run", headers=h, json={"input": str(pr["id"])}).json()

    r = run()
    assert r["tool_calls"][1]["status"] == "error" and "No active consent" in r["tool_calls"][1]["result"]["error"]
    assert db.query(Note).count() == 0
    client.post("/api/v1/records/consent", headers=h, json={"organization_id": org["id"], "title": "Case study 2026", "granted_by": "Amina, MD",
                                                          "granted_on": TODAY.isoformat(), "scope": "Named case study on our website"})
    r = run()
    assert r["tool_calls"][1]["status"] == "ok" and db.query(Note).one().title == "Case study draft: Vibanda"
    first_run_story, second_run_story = scripted_llm["results"][0][1], scripted_llm["results"][2][1]
    assert '"consent": null' in first_run_story and '"start_on": null' in first_run_story  # real nulls, not "None"
    assert '"consent": {"granted_by": "Amina, MD"' in second_run_story
    assert client.patch(f"/api/v1/records/content_piece/{cs['id']}", headers=h, json={"status": "scheduled", "publish_on": (TODAY + timedelta(days=2)).isoformat()}).status_code == 200
    assert client.get("/api/v1/reports/marketing.calendar", headers=h).json()["rows"][0][1] == "Vibanda story"


def test_expired_or_revoked_consent_is_not_active(client, make_workspace):
    from app.departments.marketing import active_consent

    w = make_workspace("acme")
    org = client.post("/api/v1/records/organization", headers=w["h"], json={"name": "X"}).json()
    c = client.post("/api/v1/records/consent", headers=w["h"], json={"organization_id": org["id"], "title": "c", "granted_by": "b",
                                                                  "granted_on": "2020-01-01", "scope": "s", "expires_on": "2021-01-01"}).json()
    rows = client.get("/api/v1/reports/marketing.consents", headers=w["h"]).json()["rows"]
    assert rows[0][3] == "expired"
    client.patch(f"/api/v1/records/consent/{c['id']}", headers=w["h"], json={"expires_on": None, "revoked_on": "2022-01-01"})
    assert client.get("/api/v1/reports/marketing.consents", headers=w["h"]).json()["rows"][0][3] == "revoked"


def test_product_signals_rank_by_clients_then_deal_value(client, make_workspace):
    w = make_workspace("acme")
    h = w["h"]
    a = client.post("/api/v1/records/organization", headers=h, json={"name": "Vibanda"}).json()
    b = client.post("/api/v1/records/organization", headers=h, json={"name": "Java House"}).json()
    ri = client.post("/api/v1/records/roadmap_item", headers=h, json={"title": "M-Pesa tips", "target_quarter": "2026-Q4"}).json()
    assert client.post("/api/v1/records/roadmap_item", headers=h, json={"title": "x", "target_quarter": "Q4"}).status_code == 422
    for org in (a, b):
        client.post("/api/v1/records/feature_request", headers=h, json={"title": "Tips via M-Pesa", "organization_id": org["id"], "roadmap_item_id": ri["id"]})
    client.post("/api/v1/records/feature_request", headers=h, json={"title": "Dark mode", "organization_id": a["id"]})
    client.post("/api/v1/records/deal", headers=h, json={"title": "Java expansion", "organization_id": b["id"], "value_minor": 50000000})
    rows = client.get("/api/v1/reports/product.signals", headers=h).json()["rows"]
    assert rows[0][:4] == ["[roadmap] M-Pesa tips", 2, 2, "KES 500,000.00"] and rows[1][0] == "Dark mode"
    shipped = client.patch(f"/api/v1/records/roadmap_item/{ri['id']}", headers=h, json={"status": "shipped"}).json()
    assert shipped["shipped_on"] is not None


def test_product_signals_without_sales_enabled(client, make_workspace, db):
    w = make_workspace("acme")
    w["ws"].enabled_departments = ["product"]
    db.commit()
    client.post("/api/v1/records/feature_request", headers=w["h"], json={"title": "A"})
    assert client.get("/api/v1/reports/product.signals", headers=w["h"]).json()["rows"][0][3] == "sales not enabled"
    assert client.get("/api/v1/records/deal", headers=w["h"]).status_code == 404


def test_on_and_offboarding(client, make_workspace, add_member):
    w = make_workspace("acme")
    h = w["h"]
    person = client.post("/api/v1/records/person", headers=h, json={"full_name": "Brian Otieno"}).json()
    s = client.post("/api/v1/records/staff_record", headers=h, json={"person_id": person["id"], "title": "Frontend dev", "start_on": TODAY.isoformat()}).json()
    out = client.post("/api/v1/agents/onboarding/run", headers=h, json={"input": str(s["id"])}).json()["output"]
    assert "Added 4 onboarding item(s)" in out and "default list" in out
    again = client.post("/api/v1/agents/onboarding/run", headers=h, json={"input": str(s["id"])}).json()["output"]
    assert "Added 0" in again  # idempotent
    client.post("/api/v1/records/access_grant", headers=h, json={"staff_id": s["id"], "title": "GitHub", "account": "brian-o"})
    client.post("/api/v1/records/access_grant", headers=h, json={"staff_id": s["id"], "title": "Google Workspace", "revoked_on": TODAY.isoformat()})
    out = client.post("/api/v1/agents/offboarding/run", headers=h, json={"input": str(s["id"])}).json()["output"]
    assert "1 access grant(s) to revoke" in out
    items = client.get("/api/v1/records/checklist_item", headers=h, params={"q": "Revoke"}).json()
    assert [i["title"] for i in items] == ["Revoke GitHub (brian-o)"]
    assert client.get(f"/api/v1/records/staff_record/{s['id']}", headers=h).json()["status"] == "offboarding"
    assert client.get("/api/v1/reports/people.access_risk", headers=h).json()["rows"] == [["Brian Otieno", "offboarding", "GitHub", "brian-o"]]
    staff = add_member(h, "staff", "s@acme.example.com")
    assert client.get("/api/v1/records/staff_record", headers=staff).status_code == 403


def test_every_department_is_discoverable_and_every_report_runs(client, make_workspace):
    w = make_workspace("acme")
    depts = client.get("/api/v1/departments", headers=w["h"]).json()
    assert [d["key"] for d in depts] == ["command", "sales", "delivery", "support", "finance", "legal", "marketing", "product", "people"]
    params = {"delivery.status": None}
    for d in depts:
        assert d["record_types"] and d["agents"], d["key"]
        for r in d["reports"]:
            if r["key"] in params:
                continue
            got = client.get(f"/api/v1/reports/{r['key']}", headers=w["h"])
            assert got.status_code == 200, (r["key"], got.text)
            assert set(got.json()) == {"title", "summary", "columns", "rows"}
    types = {t["name"]: t for t in client.get("/api/v1/records-types", headers=w["h"]).json()}
    assert types["invoice"]["fields"] and next(f for f in types["invoice"]["fields"] if f["name"] == "subtotal_minor")["money"]
