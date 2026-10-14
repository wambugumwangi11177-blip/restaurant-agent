"""Company OS Kernel: tiers, approval, earned autonomy, kill switch, agents, API."""
import json
from datetime import timedelta

import pytest

import auth
import models
from ai.company_os import agents, kernel
from time_utils import utcnow


@pytest.fixture
def op(db_session):
    t = models.Tenant(name="Ops"); db_session.add(t); db_session.commit()
    u = models.User(tenant_id=t.id, email="op@e.com", hashed_password=auth.get_password_hash("x"),
                    role=models.Role.SUPERADMIN, token_version=0, is_active=True)
    db_session.add(u); db_session.commit()
    return u


@pytest.fixture
def probe_tools():
    ran = []
    kernel.register("t_read", kernel.READ)(lambda db, p: ran.append(("read", p)) or {})
    kernel.register("t_int", kernel.INTERNAL)(lambda db, p: ran.append(("int", p)) or {})
    kernel.register("t_ext", kernel.EXTERNAL)(lambda db, p: ran.append(("ext", p)) or {})
    kernel.register("t_res", kernel.RESTRICTED)(lambda db, p: ran.append(("res", p)) or {})
    yield ran
    for n in ("t_read", "t_int", "t_ext", "t_res"):
        kernel._REGISTRY.pop(n, None)


def test_tiers_gate_execution(db_session, probe_tools):
    assert kernel.propose(db_session, "a", "t_read", {}, "r").status == "executed"
    assert kernel.propose(db_session, "a", "t_int", {}, "i").status == "executed"
    assert kernel.propose(db_session, "a", "t_ext", {}, "e").status == "pending"
    assert kernel.propose(db_session, "a", "t_res", {}, "x").status == "pending"
    assert [k for k, _ in probe_tools] == ["read", "int"]


def test_external_earns_autonomy_after_20_unedited_approvals(db_session, op, probe_tools):
    for i in range(kernel.AUTONOMY_THRESHOLD):
        p = kernel.propose(db_session, "a", "t_ext", {"i": i}, "e")
        assert p.status == "pending"
        kernel.decide(db_session, p.id, True, op)
    auto = kernel.propose(db_session, "a", "t_ext", {"i": 99}, "e")
    assert auto.status == "executed" and auto.auto_executed is True


def test_edit_resets_streak_and_blocks_autonomy(db_session, op, probe_tools):
    for i in range(19):
        kernel.decide(db_session, kernel.propose(db_session, "a", "t_ext", {"i": i}, "e").id, True, op)
    p = kernel.propose(db_session, "a", "t_ext", {"i": 19}, "e")
    kernel.decide(db_session, p.id, True, op, edited_payload={"i": "changed"})
    assert db_session.get(models.CompanyToolAutonomy, "t_ext").streak == 0
    assert kernel.propose(db_session, "a", "t_ext", {}, "e").status == "pending"


def test_reject_demotes_earned_autonomy(db_session, op, probe_tools, monkeypatch):
    db_session.add(models.CompanyToolAutonomy(tool="t_ext", streak=20, autonomous=True))
    db_session.commit()
    monkeypatch.setenv("FEATURE_COMPANY_OS_AUTONOMY", "false")   # forces a pending proposal
    p = kernel.propose(db_session, "a", "t_ext", {}, "e")
    assert p.status == "pending"
    kernel.decide(db_session, p.id, False, op)
    monkeypatch.delenv("FEATURE_COMPANY_OS_AUTONOMY")
    assert db_session.get(models.CompanyToolAutonomy, "t_ext").autonomous is False
    assert kernel.propose(db_session, "a", "t_ext", {}, "e").status == "pending"


def test_restricted_never_earns_autonomy(db_session, op, probe_tools):
    for i in range(25):
        kernel.decide(db_session, kernel.propose(db_session, "a", "t_res", {"i": i}, "x").id, True, op)
    assert kernel.propose(db_session, "a", "t_res", {}, "x").status == "pending"


def test_kill_switch_forces_draft_only(db_session, probe_tools, monkeypatch):
    db_session.add(models.CompanyToolAutonomy(tool="t_ext", streak=20, autonomous=True))
    db_session.commit()
    monkeypatch.setenv("FEATURE_COMPANY_OS_AUTONOMY", "false")
    assert kernel.propose(db_session, "a", "t_ext", {}, "e").status == "pending"
    assert kernel.propose(db_session, "a", "t_int", {}, "i").status == "pending"
    assert kernel.propose(db_session, "a", "t_read", {}, "r").status == "executed"


def test_failed_tool_is_recorded_and_demotes(db_session, probe_tools):
    kernel.register("t_boom", kernel.EXTERNAL)(lambda db, p: 1 / 0)
    try:
        db_session.add(models.CompanyToolAutonomy(tool="t_boom", streak=20, autonomous=True))
        db_session.commit()
        p = kernel.propose(db_session, "a", "t_boom", {}, "b")
        assert p.status == "failed" and "division" in p.error
        assert db_session.get(models.CompanyToolAutonomy, "t_boom").autonomous is False
    finally:
        kernel._REGISTRY.pop("t_boom", None)


def test_cannot_decide_twice(db_session, op, probe_tools):
    p = kernel.propose(db_session, "a", "t_ext", {}, "e")
    kernel.decide(db_session, p.id, True, op)
    with pytest.raises(ValueError):
        kernel.decide(db_session, p.id, True, op)


def _red_restaurant(db):
    t = models.Tenant(name="Rt"); db.add(t); db.commit()
    r = models.Restaurant(tenant_id=t.id, name="Cafe Red", address="x"); db.add(r)
    owner = models.User(tenant_id=t.id, email="o@e.com", hashed_password="x", role=models.Role.ADMIN,
                        staff_role=models.StaffRole.OWNER, token_version=0, is_active=True)
    db.add(owner); db.commit()
    for _ in range(12):
        db.add(models.Order(restaurant_id=r.id, total=1, created_at=utcnow() - timedelta(days=10)))
    db.commit()
    return r, owner


def test_cycle_off_by_default(db_session):
    assert agents.run_company_cycle(db_session)["ran"] is False


def test_client_success_agent_drafts_checkin_then_sends_on_approval(db_session, op, monkeypatch):
    monkeypatch.setenv("FEATURE_COMPANY_OS", "true")
    r, owner = _red_restaurant(db_session)
    res = agents.run_company_cycle(db_session)
    assert res["ran"] and res["pending"] == 1  # check-in waits; digest auto-ran
    chk = db_session.query(models.CompanyProposal).filter_by(tool="client_checkin").one()
    assert "Cafe Red" in json.loads(chk.payload)["message"]
    assert db_session.query(models.Notification).filter_by(user_id=owner.id).count() == 0
    kernel.decide(db_session, chk.id, True, op)
    assert db_session.query(models.Notification).filter_by(user_id=owner.id).count() == 1
    # cooldown: a second cycle does not draft another check-in
    agents.run_company_cycle(db_session)
    assert db_session.query(models.CompanyProposal).filter_by(tool="client_checkin").count() == 1


def test_api_requires_superadmin_and_approves(client, db_session, op, monkeypatch):
    monkeypatch.setenv("FEATURE_COMPANY_OS", "true")
    _red_restaurant(db_session)
    agents.run_company_cycle(db_session)
    sup = {"Authorization": "Bearer " + auth.create_access_token({"sub": op.email, "ver": 0})}
    t = models.Tenant(name="O2"); db_session.add(t); db_session.commit()
    adm = models.User(tenant_id=t.id, email="adm@e.com", hashed_password="x",
                      role=models.Role.ADMIN, token_version=0, is_active=True)
    db_session.add(adm); db_session.commit()
    adm_h = {"Authorization": "Bearer " + auth.create_access_token({"sub": adm.email, "ver": 0})}
    assert client.get("/company-os/status", headers=adm_h).status_code == 403
    pend = client.get("/company-os/proposals?status=pending", headers=sup).json()
    assert len(pend) == 1
    r = client.post(f"/company-os/proposals/{pend[0]['id']}/approve", headers=sup)
    assert r.status_code == 200 and r.json()["status"] == "executed"
    assert client.post(f"/company-os/proposals/{pend[0]['id']}/approve", headers=sup).status_code == 409
    assert client.get("/company-os/status", headers=sup).json()["tools"]
