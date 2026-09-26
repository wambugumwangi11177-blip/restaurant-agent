"""Phase 10 (plans, limits, departments, signup, platform admin) and the
execution scripts that departments rely on (job runner, CSV importer)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import get_settings
from app.kernel.models import AuditLog, Notification, Workspace
from app.security import totp_now
from tests.conftest import STRONG_PASSWORD

EXEC = Path(__file__).resolve().parents[2] / "execution"


@pytest.fixture
def settings_override(monkeypatch):
    def apply(**kw):
        from dataclasses import replace

        new = replace(get_settings(), **kw)
        for mod in ("app.config", "app.api.platform"):
            monkeypatch.setattr(f"{mod}.get_settings", lambda: new)
        return new

    return apply


def test_limits_are_enforced(client, make_workspace, db):
    w = make_workspace("acme")
    ws = db.get(Workspace, w["ws"].id)
    ws.seat_limit, ws.monthly_agent_run_limit = 1, 1
    db.commit()
    r = client.post("/api/v1/members", headers=w["h"], json={"email": "x@acme.example.com", "full_name": "X", "role": "staff", "password": STRONG_PASSWORD})
    assert r.status_code == 402 and "Seat limit" in r.text
    assert client.post("/api/v1/agents/echo/run", headers=w["h"], json={"input": "1"}).status_code == 200
    r = client.post("/api/v1/agents/echo/run", headers=w["h"], json={"input": "2"})
    assert r.status_code == 402 and "agent-run limit" in r.text
    usage = client.get("/api/v1/workspace/usage", headers=w["h"]).json()
    assert (usage["seats_used"], usage["seat_limit"], usage["agent_runs_this_month"]) == (1, 1, 1)


def test_disabled_departments_disappear(client, make_workspace, db):
    w = make_workspace("acme")
    ws = db.get(Workspace, w["ws"].id)
    ws.enabled_departments = ["command", "sales"]
    db.commit()
    assert [d["key"] for d in client.get("/api/v1/departments", headers=w["h"]).json()] == ["command", "sales"]
    assert client.get("/api/v1/records/invoice", headers=w["h"]).status_code == 404
    assert client.get("/api/v1/reports/finance.runway", headers=w["h"]).status_code == 404
    assert client.post("/api/v1/jobs/sla_check/run", headers=w["h"]).status_code == 404
    names = {t["name"] for t in client.get("/api/v1/records-types", headers=w["h"]).json()}
    assert "deal" in names and "invoice" not in names and "task" in names


def test_platform_admin_requires_listing_and_mfa(client, make_workspace, settings_override, db):
    w = make_workspace("acme", email="ops@acme.example.com")
    assert client.get("/api/v1/platform/workspaces", headers=w["h"]).status_code == 403
    settings_override(platform_admin_emails=["ops@acme.example.com"])
    r = client.get("/api/v1/platform/workspaces", headers=w["h"])
    assert r.status_code == 403 and "two-factor" in r.text
    secret = client.post("/api/v1/auth/mfa/setup", headers=w["h"]).json()["secret"]
    client.post("/api/v1/auth/mfa/enable", headers=w["h"], json={"code": totp_now(secret)})
    assert client.get("/api/v1/platform/workspaces", headers=w["h"]).status_code == 200

    new = client.post("/api/v1/platform/workspaces", headers=w["h"], json={
        "slug": "cafe-one", "name": "Cafe One", "founder_email": "owner@cafeone.example.com", "founder_name": "Owner",
        "founder_password": STRONG_PASSWORD, "plan": "standard", "seat_limit": 5, "enabled_departments": ["command", "support"]})
    assert new.status_code == 201, new.text
    wid = new.json()["id"]
    bad = client.patch(f"/api/v1/platform/workspaces/{wid}", headers=w["h"], json={"enabled_departments": ["hr-magic"]})
    assert bad.status_code == 422
    ok = client.patch(f"/api/v1/platform/workspaces/{wid}", headers=w["h"], json={"monthly_agent_run_limit": 50})
    assert ok.json()["monthly_agent_run_limit"] == 50
    assert db.query(AuditLog).filter(AuditLog.action == "platform.plan_change", AuditLog.workspace_id == wid).count() == 1
    owner = client.post("/api/v1/auth/login", json={"email": "owner@cafeone.example.com", "password": STRONG_PASSWORD}).json()["access_token"]
    oh = {"Authorization": f"Bearer {owner}"}
    assert client.get("/api/v1/platform/workspaces", headers=oh).status_code == 403  # founders can't raise their own limits
    assert [d["key"] for d in client.get("/api/v1/departments", headers=oh).json()] == ["command", "support"]


def test_signup_off_by_default_then_guarded(client, make_workspace, settings_override):
    body = {"slug": "newco", "name": "NewCo", "email": "me@newco.example.com", "full_name": "Me", "password": STRONG_PASSWORD}
    assert client.post("/api/v1/signup", json=body).status_code == 404
    settings_override(allow_signup=True, signup_seat_limit=2, signup_monthly_agent_run_limit=10, signup_departments=["command"])
    r = client.post("/api/v1/signup", json=body)
    assert r.status_code == 201 and r.json()["plan"] == "trial"
    make_workspace("acme", email="victim@acme.example.com")
    hijack = client.post("/api/v1/signup", json={**body, "slug": "evil", "email": "victim@acme.example.com"})
    assert hijack.status_code == 422 and "already exists" in hijack.text
    assert client.post("/api/v1/signup", json={**body, "slug": "weak", "email": "w@x.example.com", "password": "short"}).status_code == 422


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(EXEC / script), *args], capture_output=True, text=True,
                          env={**os.environ}, cwd=str(EXEC.parent), timeout=120)


def test_job_runner_script(client, make_workspace, db):
    make_workspace("acme")
    out = _run("run_jobs.py", "--list")
    assert out.returncode == 0 and "daily_brief" in out.stdout and "sla_check" in out.stdout
    out = _run("run_jobs.py", "daily_brief", "--workspace", "acme")
    assert out.returncode == 0, out.stderr
    assert "acme: brief delivered in-app to 1 founder(s)" in out.stdout
    db.expire_all()
    assert db.query(Notification).filter(Notification.title == "Your daily brief").count() == 1
    assert db.query(AuditLog).filter(AuditLog.action == "job.run").one().changes["manual"] is False


def test_csv_importer_maps_columns_and_reports_bad_rows(client, make_workspace, tmp_path):
    w = make_workspace("acme")
    csv_file = tmp_path / "statement.csv"
    csv_file.write_text("Receipt No.,Completion Time,Paid In,Details\n"
                        "QAB1CD2EF3,26/09/2026 10:15:00,\"1,500.00\",Payment from client\n"
                        "QAB1CD2EF4,27/09/2026 11:00:00,abc,bad amount\n", encoding="utf-8")
    common = ["--workspace", "acme", "--type", "payment", "--csv", str(csv_file), "--money-major",
              "--date-format", "%d/%m/%Y %H:%M:%S", "--map", "Receipt No.=reference,Paid In=amount_minor,Completion Time=received_on"]
    dry = _run("import_records.py", *common, "--dry-run")
    assert "Would import 1 row(s); 1 rejected." in dry.stdout and "line 3" in dry.stderr
    assert client.get("/api/v1/records/payment", headers=w["h"]).json() == []
    real = _run("import_records.py", *common)
    assert "Imported 1 row(s); 1 rejected." in real.stdout
    pay = client.get("/api/v1/records/payment", headers=w["h"]).json()[0]
    assert (pay["reference"], pay["amount_minor"], pay["received_on"], pay["currency"]) == ("QAB1CD2EF3", 150000, "2026-09-26", "KES")
