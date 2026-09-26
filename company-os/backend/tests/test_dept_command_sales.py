"""Departments 1 (Command Center) and 2 (Sales)."""

from datetime import date, datetime, timedelta, timezone

from app.departments import ical
from app.departments.command import compose_brief, daily_brief_job
from app.kernel.models import AuditLog, Decision, Notification
from tests.conftest import llm_turn

ICS = """BEGIN:VCALENDAR\r
BEGIN:VEVENT\r
SUMMARY:Vibanda weekly\\, review\r
DTSTART:{utc}\r
LOCATION:Google Meet\r
END:VEVENT\r
BEGIN:VEVENT\r
SUMMARY:Standup\r
DTSTART;TZID=Africa/Nairobi:{local}\r
RRULE:FREQ=DAILY\r
END:VEVENT\r
BEGIN:VEVENT\r
SUMMARY:Old daily sync\r
DTSTART;TZID=Africa/Nairobi:20200101T090000\r
RRULE:FREQ=DAILY\r
END:VEVENT\r
BEGIN:VEVENT\r
SUMMARY:Public holiday\r
DTSTART;VALUE=DATE:{day}\r
END:VEVENT\r
BEGIN:VEVENT\r
SUMMARY:Cancelled thing\r
STATUS:CANCELLED\r
DTSTART:{utc}\r
END:VEVENT\r
BEGIN:VEVENT\r
SUMMARY:A very long title that is\r
  folded onto two lines\r
DTSTART:20200101T000000Z\r
END:VEVENT\r
END:VCALENDAR\r
"""


def _ics(day: date) -> str:
    return ICS.format(utc=f"{day:%Y%m%d}T070000Z", local=f"{day:%Y%m%d}T093000", day=f"{day:%Y%m%d}")


def test_ical_subset():
    day = date(2026, 9, 28)
    events = ical.parse_events(_ics(day))
    assert "A very long title that is folded onto two lines" in [e.summary for e in events]
    assert "Cancelled thing" not in [e.summary for e in events]
    today, skipped = ical.events_on(events, day, "Africa/Nairobi")
    assert [e.summary for e in today] == ["Public holiday", "Standup", "Vibanda weekly, review"]  # 09:30 EAT before 10:00 EAT
    assert today[2].start.astimezone(ical.ZoneInfo("Africa/Nairobi")).hour == 10  # 07:00Z = 10:00 EAT
    assert skipped == 1  # "Old daily sync" recurs but isn't expanded — reported, not hidden


def test_workspace_settings_masked_and_audited_without_values(client, make_workspace, db):
    w = make_workspace("acme")
    assert client.put("/api/v1/workspace/settings", headers=w["h"], json={"nope": 1}).status_code == 422
    url = "https://calendar.example.com/private-abc123/basic.ics"
    assert client.put("/api/v1/workspace/settings", headers=w["h"], json={"calendar_ical_url": url}).status_code == 200
    got = {s["key"]: s for s in client.get("/api/v1/workspace/settings", headers=w["h"]).json()}
    assert got["calendar_ical_url"]["value"] == "••••••" and got["calendar_ical_url"]["is_set"]
    row = db.query(AuditLog).filter(AuditLog.action == "workspace.settings").one()
    assert row.changes == {"keys": ["calendar_ical_url"]} and "private-abc123" not in str(row.changes)
    assert client.put("/api/v1/workspace/settings", headers=w["h"], json={"sales_stale_days": "x"}).status_code == 422


def test_goals_meetings_and_brief(client, make_workspace, db, monkeypatch):
    w = make_workspace("acme")
    g = client.post("/api/v1/records/goal", headers=w["h"], json={
        "title": "Monthly recurring revenue", "metric": "MRR", "baseline_value": 0, "target_value": 200000,
        "current_value": 50000, "status": "at_risk"})
    assert g.status_code == 201, g.text
    rep = client.get("/api/v1/reports/command.goals", headers=w["h"]).json()
    assert rep["rows"][0][5] == "25.0%"
    assert client.post("/api/v1/records/meeting", headers=w["h"], json={"title": "Vibanda check-in"}).status_code == 201

    db.expire_all()
    monkeypatch.setattr("app.departments.command.ical.fetch", lambda url: _ics(datetime.now(ical.ZoneInfo("Africa/Nairobi")).date()))
    client.put("/api/v1/workspace/settings", headers=w["h"], json={"calendar_ical_url": "https://cal.example.com/x.ics"})
    brief = compose_brief(db, w["ws"].id, w["user"].id, fetcher=ical.fetch)
    assert "Vibanda weekly, review" in brief and "Monthly recurring revenue (at_risk)" in brief
    assert "1 recurring event(s) not expanded" in brief


def test_calendar_failure_does_not_break_brief(make_workspace, db):
    w = make_workspace("acme")
    w["ws"].settings = {"calendar_ical_url": "https://cal.example.com/x.ics"}
    db.commit()

    def boom(url):
        raise TimeoutError()

    assert "(calendar unavailable: TimeoutError)" in compose_brief(db, w["ws"].id, w["user"].id, fetcher=boom)


def test_daily_brief_job_notifies_founders(client, make_workspace, db):
    w = make_workspace("acme")
    client.post("/api/v1/records/deal", headers=w["h"], json={"title": "Java House pilot"})  # no next step -> stale
    r = client.post("/api/v1/jobs/daily_brief/run", headers=w["h"])
    assert r.status_code == 200 and "in-app to 1 founder" in r.json()["summary"]
    note = db.query(Notification).filter(Notification.title == "Your daily brief").one()
    assert "Sales follow-ups:" in note.body and "Java House pilot: no next step" in note.body


def test_decision_recorder_creates_proposed_decisions(client, make_workspace, scripted_llm, db):
    w = make_workspace("acme")
    scripted_llm["script"][:] = [
        llm_turn(uses=[("record_decision", {"title": "Price floor", "decision": "No discounts above 10% without founder sign-off"})]),
        llm_turn(text="Recorded 1 decision."),
    ]
    r = client.post("/api/v1/agents/decision_recorder/run", headers=w["h"], json={"input": "we agreed no >10% discounts"}).json()
    assert r["status"] == "succeeded" and r["tool_calls"][0]["status"] == "ok"
    d = db.query(Decision).one()
    assert (d.status, d.title) == ("proposed", "Price floor")


def test_chief_of_staff_agent(client, make_workspace):
    w = make_workspace("acme")
    r = client.post("/api/v1/agents/chief_of_staff/run", headers=w["h"], json={}).json()
    assert r["status"] == "succeeded" and "Calendar today:" in r["output"] and "no calendar connected" in r["output"]


# ── Sales ────────────────────────────────────────────────────────────────────

def test_deal_rules(client, make_workspace):
    w = make_workspace("acme")
    d = client.post("/api/v1/records/deal", headers=w["h"], json={"title": "Vibanda phase 2", "value_minor": 15000000}).json()
    assert d["currency"] == "KES"
    lost = client.patch(f"/api/v1/records/deal/{d['id']}", headers=w["h"], json={"stage": "lost"})
    assert lost.status_code == 422 and "lost_reason" in lost.text
    won = client.patch(f"/api/v1/records/deal/{d['id']}", headers=w["h"], json={"stage": "won"}).json()
    assert won["closed_at"] is not None
    assert client.post("/api/v1/records/deal", headers=w["h"], json={"title": "x", "currency": "kes"}).status_code == 422


def test_stale_rule_and_activity(client, make_workspace, db):
    w = make_workspace("acme")
    h = w["h"]
    future = (date.today() + timedelta(days=5)).isoformat()
    past = (date.today() - timedelta(days=3)).isoformat()
    a = client.post("/api/v1/records/deal", headers=h, json={"title": "A no step"}).json()
    b = client.post("/api/v1/records/deal", headers=h, json={"title": "B overdue", "next_step": "send quote", "next_step_due": past}).json()
    c = client.post("/api/v1/records/deal", headers=h, json={"title": "C healthy", "next_step": "demo", "next_step_due": future}).json()
    client.post("/api/v1/records/deal", headers=h, json={"title": "D won", "stage": "won"})
    act = client.post("/api/v1/records/activity", headers=h, json={"deal_id": c["id"], "kind": "call", "summary": "Agreed demo date"})
    assert act.status_code == 201
    db.expire_all()
    from app.departments.sales import Deal

    assert db.get(Deal, c["id"]).last_activity_at is not None
    rows = client.get("/api/v1/reports/sales.stale", headers=h).json()["rows"]
    assert {r[1]: r[4] for r in rows} == {"A no step": "no next step", "B overdue": f"next step overdue since {past}"}
    out = client.post("/api/v1/agents/pipeline_reviewer/run", headers=h, json={}).json()["output"]
    assert "2 deal(s) need attention" in out and a["title"] in out and b["title"] in out


def test_sales_permissions_and_cross_workspace_refs(client, make_workspace, add_member):
    a = make_workspace("alpha")
    b = make_workspace("beta")
    org_b = client.post("/api/v1/records/organization", headers=b["h"], json={"name": "Beta Co"}).json()
    r = client.post("/api/v1/records/deal", headers=a["h"], json={"title": "x", "organization_id": org_b["id"]})
    assert r.status_code == 422 and "organization_id" in r.text
    con = add_member(a["h"], "contractor", "con@alpha.example.com")
    adv = add_member(a["h"], "advisor", "adv@alpha.example.com")
    assert client.get("/api/v1/records/deal", headers=con).status_code == 403
    assert client.get("/api/v1/records/deal", headers=adv).status_code == 200
    assert client.post("/api/v1/records/deal", headers=adv, json={"title": "x"}).status_code == 403
    assert "sales" not in [d["key"] for d in client.get("/api/v1/departments", headers=con).json()]


def test_pipeline_report_does_not_mix_currencies(client, make_workspace):
    w = make_workspace("acme")
    client.post("/api/v1/records/deal", headers=w["h"], json={"title": "a", "value_minor": 100000})
    client.post("/api/v1/records/deal", headers=w["h"], json={"title": "b", "value_minor": 5000, "currency": "USD"})
    lead = client.get("/api/v1/reports/sales.pipeline", headers=w["h"]).json()["rows"][0]
    assert lead == ["lead", 2, "KES 1,000.00, USD 50.00"]


def test_followup_drafter_proposes_not_sends(client, make_workspace, scripted_llm, db):
    from app.kernel.models import Proposal

    w = make_workspace("acme")
    p = client.post("/api/v1/records/person", headers=w["h"], json={"full_name": "Amina", "email": "amina@vibanda.example.com"}).json()
    d = client.post("/api/v1/records/deal", headers=w["h"], json={"title": "Phase 2", "primary_contact_id": p["id"]}).json()
    scripted_llm["script"][:] = [
        llm_turn(uses=[("get_deal", {"deal_id": d["id"]})]),
        llm_turn(uses=[("send_email", {"to": "amina@vibanda.example.com", "subject": "Phase 2", "body": "Hi Amina, …"})]),
        llm_turn(text="Proposed an email."),
    ]
    r = client.post("/api/v1/agents/followup_drafter/run", headers=w["h"], json={"input": f"deal {d['id']}"}).json()
    assert [t["status"] for t in r["tool_calls"]] == ["ok", "pending_approval"]
    assert db.query(Proposal).one().status == "pending"
    assert '"email": "amina@vibanda.example.com"' in scripted_llm["results"][0][1]
