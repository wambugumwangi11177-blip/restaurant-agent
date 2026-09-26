"""Departments 3 (Delivery) and 4 (Support)."""

from datetime import date, datetime, timedelta, timezone

from app.departments.delivery import github_commits, project_status
from app.departments.support import parse_sla
from app.kernel.models import Event, Notification
from tests.conftest import llm_turn


class _Resp:
    def __init__(self, status, data):
        self.status_code, self._d = status, data

    def json(self):
        return self._d


def _commits(url, params, headers, timeout):
    assert url == "https://api.github.com/repos/acme/vibanda-app/commits" and "since" in params
    return _Resp(200, [{"sha": "abcdef1234", "commit": {"message": "Fix KDS timer\n\nlong body", "author": {"date": "2026-09-25T10:00:00Z"}}}])


def test_project_rules_and_status(client, make_workspace, db):
    w = make_workspace("acme")
    h = w["h"]
    bad = client.post("/api/v1/records/project", headers=h, json={"title": "x", "start_on": "2026-10-01", "end_on": "2026-09-01"})
    assert bad.status_code == 422
    assert client.post("/api/v1/records/project", headers=h, json={"title": "x", "github_repo": "not a repo"}).status_code == 422
    pr = client.post("/api/v1/records/project", headers=h, json={"title": "Vibanda POS", "status": "active", "github_repo": "acme/vibanda-app"}).json()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    m1 = client.post("/api/v1/records/milestone", headers=h, json={"project_id": pr["id"], "title": "KDS live", "due_on": yesterday}).json()
    client.post("/api/v1/records/milestone", headers=h, json={"project_id": pr["id"], "title": "Reports", "due_on": "2099-01-01"})
    done = client.patch(f"/api/v1/records/milestone/{m1['id']}", headers=h, json={"status": "done"}).json()
    assert done["completed_on"] is not None
    te = client.post("/api/v1/records/time_entry", headers=h, json={"project_id": pr["id"], "worked_on": date.today().isoformat(), "minutes": 90}).json()
    assert te["user_id"] == w["user"].id
    client.post("/api/v1/records/change_request", headers=h, json={"project_id": pr["id"], "title": "Add M-Pesa tips", "cost_minor": 2500000})
    text = project_status(db, w["ws"].id, pr["id"], getter=_commits)
    assert "Milestones: 1/2 done" in text and "✔ KDS live" in text and "→ next: Reports" in text
    assert "1.5 h" in text and "Add M-Pesa tips [requested] cost KES 25,000.00" in text
    assert "1 commit(s) on acme/vibanda-app" in text and "Fix KDS timer (abcdef1)" in text
    rows = client.get("/api/v1/reports/delivery.projects", headers=h).json()["rows"]
    assert rows[0][1:] == ["Vibanda POS", "active", "1/2", 0, "1.5"]


def test_github_unavailable_is_explained():
    out = github_commits("acme/private", datetime.now(timezone.utc), getter=lambda *a, **k: _Resp(404, {}))
    assert out == "GitHub returned 404 (private repo needs GITHUB_TOKEN)"


def test_status_reporter_agent_and_overdue_brief(client, make_workspace, monkeypatch):
    w = make_workspace("acme")
    pr = client.post("/api/v1/records/project", headers=w["h"], json={"title": "P"}).json()
    client.post("/api/v1/records/milestone", headers=w["h"], json={"project_id": pr["id"], "title": "Late one", "due_on": "2020-01-01"})
    r = client.post("/api/v1/agents/status_reporter/run", headers=w["h"], json={"input": f"project {pr['id']}"}).json()
    assert "⚠ overdue: Late one" in r["output"]
    assert "overdue milestone: Late one" in client.get("/api/v1/reports/command.brief", headers=w["h"]).json()["summary"]


def test_contractor_can_log_time_but_not_delete(client, make_workspace, add_member):
    w = make_workspace("acme")
    con = add_member(w["h"], "contractor", "dev@acme.example.com")
    pr = client.post("/api/v1/records/project", headers=w["h"], json={"title": "P"}).json()
    te = client.post("/api/v1/records/time_entry", headers=con, json={"project_id": pr["id"], "worked_on": "2026-09-01", "minutes": 60})
    assert te.status_code == 201
    assert client.delete(f"/api/v1/records/time_entry/{te.json()['id']}", headers=con).status_code == 403


# ── Support ──────────────────────────────────────────────────────────────────

def test_sla_policy_parsing():
    assert parse_sla("urgent=4, high=8") == {"urgent": 4, "high": 8}
    assert parse_sla(None) == {}
    try:
        parse_sla("urgent=soon")
        raise AssertionError("should fail")
    except ValueError:
        pass


def test_no_sla_without_policy_and_resolution_required(client, make_workspace):
    w = make_workspace("acme")
    t = client.post("/api/v1/records/ticket", headers=w["h"], json={"title": "Printer offline", "priority": "urgent"}).json()
    assert t["sla_due_at"] is None  # no invented SLA
    r = client.patch(f"/api/v1/records/ticket/{t['id']}", headers=w["h"], json={"status": "resolved"})
    assert r.status_code == 422
    ok = client.patch(f"/api/v1/records/ticket/{t['id']}", headers=w["h"], json={"status": "resolved", "resolution": "Restarted print server"})
    assert ok.json()["resolved_at"] is not None


def test_sla_breach_alerts_once(client, make_workspace, db):
    from app.departments.support import Ticket

    w = make_workspace("acme")
    client.put("/api/v1/workspace/settings", headers=w["h"], json={"support_sla_hours": "urgent=4,normal=24"})
    t = client.post("/api/v1/records/ticket", headers=w["h"], json={"title": "KDS down", "priority": "urgent"}).json()
    due = datetime.fromisoformat(t["sla_due_at"])
    assert timedelta(hours=3, minutes=59) < due - datetime.now(timezone.utc) <= timedelta(hours=4)
    db.get(Ticket, t["id"]).sla_due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.post("/api/v1/jobs/sla_check/run", headers=w["h"]).json()["summary"] == "1 newly breached ticket(s)"
    assert client.post("/api/v1/jobs/sla_check/run", headers=w["h"]).json()["summary"] == "0 newly breached ticket(s)"
    assert db.query(Event).filter(Event.type == "ticket.sla_breached").count() == 1
    assert db.query(Notification).filter(Notification.title == "SLA breached: KDS down").count() == 1
    assert client.get("/api/v1/reports/support.queue", headers=w["h"]).json()["rows"][0][5] == "breached"


def test_triage_uses_past_resolutions_and_proposes(client, make_workspace, scripted_llm, db):
    from app.kernel.models import Proposal

    w = make_workspace("acme")
    old = client.post("/api/v1/records/ticket", headers=w["h"], json={"title": "Receipt printer not printing"}).json()
    client.patch(f"/api/v1/records/ticket/{old['id']}", headers=w["h"], json={"status": "resolved", "resolution": "Reinstall the ESC/POS driver"})
    p = client.post("/api/v1/records/person", headers=w["h"], json={"full_name": "Owner", "email": "owner@cafe.example.com"}).json()
    new = client.post("/api/v1/records/ticket", headers=w["h"], json={"title": "Printer not printing receipts", "person_id": p["id"]}).json()
    scripted_llm["script"][:] = [
        llm_turn(uses=[("get_ticket", {"ticket_id": new["id"]}), ("search_tickets", {"query": "printer printing receipts"})]),
        llm_turn(uses=[("send_email", {"to": "owner@cafe.example.com", "subject": "Printer", "body": "Please reinstall the driver…"})]),
        llm_turn(text="Drafted."),
    ]
    r = client.post("/api/v1/agents/triage/run", headers=w["h"], json={"input": f"ticket {new['id']}"}).json()
    assert [t["status"] for t in r["tool_calls"]] == ["ok", "ok", "pending_approval"]
    assert "Reinstall the ESC/POS driver" in scripted_llm["results"][1][1]
    assert db.query(Proposal).one().tool_name == "send_email"


def test_incident_scribe_writes_draft_once(client, make_workspace):
    w = make_workspace("acme")
    i = client.post("/api/v1/records/incident", headers=w["h"], json={
        "title": "API outage", "severity": "sev1", "timeline": "10:02 alerts fired\n10:20 rollback"}).json()
    client.patch(f"/api/v1/records/incident/{i['id']}", headers=w["h"], json={"status": "resolved"})
    r1 = client.post("/api/v1/agents/incident_scribe/run", headers=w["h"], json={"input": str(i["id"])}).json()["output"]
    assert "## Root cause\nTODO (human)" in r1 and "10:20 rollback" in r1 and "(saved" in r1
    r2 = client.post("/api/v1/agents/incident_scribe/run", headers=w["h"], json={"input": str(i["id"])}).json()["output"]
    assert "(not saved" in r2
