"""The approval gate: nothing EXTERNAL runs without a founder-approved proposal
whose final arguments match exactly."""

import pytest

from app.kernel.agents.tools import TOOLS, ApprovalRequired, ToolContext, execute_tool
from app.kernel.models import ChannelMessage, Feedback, Notification, Proposal, ToolCall
from app.kernel.tenancy import Principal

EMAIL = {"to": "client@vibanda.example.com", "subject": "Weekly update", "body": "All green this week."}


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_send(to, subject, body):
        calls.append((to, subject, body))
        return "<msg-1@test>"

    monkeypatch.setattr("app.kernel.channels.email.send", fake_send)
    return calls


def _principal(w) -> Principal:
    return Principal(user_id=w["user"].id, workspace_id=w["ws"].id, role="founder")


def test_proposal_then_approval_executes_exactly_once(client, make_workspace, add_member, sent, db):
    w = make_workspace("acme")
    staff = add_member(w["h"], "staff", "staff@acme.example.com")
    r = client.post("/api/v1/approvals", headers=staff, json={"tool": "send_email", "args": EMAIL})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["status"] == "pending"
    assert sent == []  # proposing sends nothing

    note = db.query(Notification).filter(Notification.user_id == w["user"].id).one()
    assert note.title == "Approval needed" and "Weekly update" in note.body

    assert client.post(f"/api/v1/approvals/{pid}/decide", headers=staff, json={"verdict": "approve"}).status_code == 403
    d = client.post(f"/api/v1/approvals/{pid}/decide", headers=w["h"], json={"verdict": "approve"})
    assert d.status_code == 200 and d.json()["status"] == "executed"
    assert sent == [(EMAIL["to"], EMAIL["subject"], EMAIL["body"])]
    assert db.query(ChannelMessage).filter(ChannelMessage.direction == "out").count() == 1
    assert db.query(Feedback).filter(Feedback.target_id == pid).one().verdict == "approved"

    again = client.post(f"/api/v1/approvals/{pid}/decide", headers=w["h"], json={"verdict": "approve"})
    assert again.status_code == 409
    assert len(sent) == 1


def test_external_tool_without_approval_only_creates_a_proposal(make_workspace, sent, db):
    w = make_workspace("acme")
    ctx = ToolContext(db=db, principal=_principal(w))
    out = execute_tool(ctx, "send_email", dict(EMAIL))
    assert out["status"] == "pending_approval"
    assert sent == []
    with pytest.raises(ApprovalRequired):
        TOOLS["send_email"].handler(ctx, dict(EMAIL))  # second, independent check inside the handler
    assert sent == []


def test_approval_id_must_match_an_approved_proposal_with_identical_args(make_workspace, sent, db):
    w = make_workspace("acme")
    ctx = ToolContext(db=db, principal=_principal(w))
    pending_id = execute_tool(ctx, "send_email", dict(EMAIL))["proposal_id"]

    forged = ToolContext(db=db, principal=_principal(w), approval_id=pending_id)
    assert execute_tool(forged, "send_email", dict(EMAIL))["status"] == "denied"  # still pending

    p = db.get(Proposal, pending_id)
    p.status, p.final_args = "approved", dict(EMAIL)
    db.flush()
    tampered = {**EMAIL, "to": "attacker@evil.example.com"}
    assert execute_tool(forged, "send_email", tampered)["status"] == "denied"
    assert execute_tool(forged, "send_whatsapp", {"to": "0712345678", "body": "x"})["status"] == "denied"
    assert sent == []
    assert db.query(ToolCall).filter(ToolCall.status == "denied").count() == 3


def test_other_workspace_cannot_use_an_approval(make_workspace, sent, db):
    a = make_workspace("alpha")
    b = make_workspace("beta")
    pid = execute_tool(ToolContext(db=db, principal=_principal(a)), "send_email", dict(EMAIL))["proposal_id"]
    p = db.get(Proposal, pid)
    p.status, p.final_args = "approved", dict(EMAIL)
    db.flush()
    out = execute_tool(ToolContext(db=db, principal=_principal(b), approval_id=pid), "send_email", dict(EMAIL))
    assert out["status"] == "denied" and sent == []


def test_edit_on_approval_sends_the_edited_version(client, make_workspace, sent, db):
    w = make_workspace("acme")
    pid = client.post("/api/v1/approvals", headers=w["h"], json={"tool": "send_email", "args": EMAIL}).json()["id"]
    edited = {**EMAIL, "body": "All green this week. Invoice attached."}
    bad = client.post(f"/api/v1/approvals/{pid}/decide", headers=w["h"],
                      json={"verdict": "approve", "edited_args": {**edited, "bcc": "x"}})
    assert bad.status_code == 422
    d = client.post(f"/api/v1/approvals/{pid}/decide", headers=w["h"], json={"verdict": "approve", "edited_args": edited})
    assert d.json()["status"] == "executed" and d.json()["edited"] is True
    assert sent == [(edited["to"], edited["subject"], edited["body"])]
    assert db.query(Feedback).filter(Feedback.target_id == pid).one().verdict == "edited"


def test_rejection_requires_a_reason_and_is_recorded(client, make_workspace, sent, db):
    w = make_workspace("acme")
    pid = client.post("/api/v1/approvals", headers=w["h"], json={"tool": "send_email", "args": EMAIL}).json()["id"]
    assert client.post(f"/api/v1/approvals/{pid}/decide", headers=w["h"], json={"verdict": "reject"}).status_code == 422
    d = client.post(f"/api/v1/approvals/{pid}/decide", headers=w["h"],
                    json={"verdict": "reject", "reason": "Wrong tone for this client"})
    assert d.json()["status"] == "rejected"
    fb = db.query(Feedback).filter(Feedback.target_id == pid).one()
    assert (fb.verdict, fb.reason) == ("rejected", "Wrong tone for this client")
    assert sent == []


def test_unconfigured_channel_fails_visibly(client, make_workspace, db):
    w = make_workspace("acme")  # SMTP is not configured in tests
    pid = client.post("/api/v1/approvals", headers=w["h"], json={"tool": "send_email", "args": EMAIL}).json()["id"]
    d = client.post(f"/api/v1/approvals/{pid}/decide", headers=w["h"], json={"verdict": "approve"})
    assert d.json()["status"] == "failed"
    assert "SMTP is not configured" in d.json()["error"]
    titles = [n.title for n in db.query(Notification).filter(Notification.user_id == w["user"].id)]
    assert "An approved action failed" in titles


def test_propose_rejects_non_external_tools_and_bad_args(client, make_workspace):
    w = make_workspace("acme")
    assert client.post("/api/v1/approvals", headers=w["h"], json={"tool": "create_task", "args": {"title": "x"}}).status_code == 422
    assert client.post("/api/v1/approvals", headers=w["h"], json={"tool": "send_email", "args": {"to": "x"}}).status_code == 422


def test_autonomy_is_earned_and_reset_by_edits(client, make_workspace, sent):
    w = make_workspace("acme")
    assert client.put("/api/v1/approvals-policies/send_email", headers=w["h"],
                      json={"auto_approve_enabled": True, "streak_threshold": 2}).status_code == 422
    assert client.put("/api/v1/approvals-policies/create_task", headers=w["h"],
                      json={"auto_approve_enabled": True, "streak_threshold": 5}).status_code == 404
    client.put("/api/v1/approvals-policies/send_email", headers=w["h"],
               json={"auto_approve_enabled": True, "streak_threshold": 5})

    def propose_and(verdict: str | None, **extra) -> dict:
        p = client.post("/api/v1/approvals", headers=w["h"], json={"tool": "send_email", "args": EMAIL}).json()
        if verdict:
            client.post(f"/api/v1/approvals/{p['id']}/decide", headers=w["h"], json={"verdict": verdict, **extra})
        return p

    for _ in range(4):
        assert propose_and("approve")["status"] == "pending"
    edited = propose_and("approve", edited_args={**EMAIL, "body": "changed"})
    assert edited["status"] == "pending"
    policy = next(p for p in client.get("/api/v1/approvals-policies", headers=w["h"]).json() if p["tool"] == "send_email")
    assert policy["current_streak"] == 0  # the edit reset it

    for _ in range(5):
        propose_and("approve")
    auto = propose_and(None)
    assert auto["status"] == "executed" and auto["auto_approved"] is True
    assert len(sent) == 4 + 1 + 5 + 1
