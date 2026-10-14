"""Department agents: each acts only through the kernel and stays idempotent."""
from datetime import date, timedelta

import pytest

import auth
import models
from ai.company_os import agents, kernel
from ai.company_os.departments import compliance, customer_success, engineering, executive, finance, support
from time_utils import utcnow


@pytest.fixture
def world(db_session, monkeypatch):
    monkeypatch.setenv("FEATURE_COMPANY_OS", "true")
    db = db_session
    ops_t = models.Tenant(name="Ops"); t = models.Tenant(name="Cafe", created_at=utcnow() - timedelta(days=20))
    db.add_all([ops_t, t]); db.commit()
    op = models.User(tenant_id=ops_t.id, email="op@e.com", hashed_password="x", role=models.Role.SUPERADMIN,
                     token_version=0, is_active=True)
    owner = models.User(tenant_id=t.id, email="own@e.com", hashed_password="x", role=models.Role.ADMIN,
                        staff_role=models.StaffRole.OWNER, token_version=0, is_active=True)
    r = models.Restaurant(tenant_id=t.id, name="Cafe", address="x")
    db.add_all([op, owner, r]); db.commit()
    return db, op, owner, r, t


def _notes(db, user):
    return db.query(models.Notification).filter_by(user_id=user.id).all()


def test_support_acks_unanswered_ticket_after_approval_and_escalates_stale(world):
    db, op, owner, r, _ = world
    tk = models.SupportTicket(restaurant_id=r.id, created_by_id=owner.id, subject="Menu broken",
                              created_at=utcnow() - timedelta(days=4))
    db.add(tk); db.commit()
    made = support.run(db)
    ack = [p for p in made if p.tool == "ticket_reply"][0]
    assert ack.status == "pending" and any(p.tool == "operator_alert" for p in made)
    kernel.decide(db, ack.id, True, op)
    assert db.query(models.SupportTicketMessage).filter_by(ticket_id=tk.id).count() == 1
    assert len(_notes(db, owner)) == 1
    assert all(p.tool != "ticket_reply" for p in support.run(db))  # now replied: no second ack


def test_finance_reminds_overdue_once_per_week(world):
    db, op, owner, r, t = world
    db.add(models.Subscription(tenant_id=t.id, plan="pro", status="past_due")); db.commit()
    p = [x for x in finance.run(db) if x.tool == "billing_reminder"]
    assert len(p) == 1 and p[0].status == "pending"
    assert [x for x in finance.run(db) if x.tool == "billing_reminder"] == []
    kernel.decide(db, p[0].id, True, op)
    assert len(_notes(db, owner)) == 1


def test_finance_ignores_free_and_current(world):
    db, _, _, _, t = world
    db.add(models.Subscription(tenant_id=t.id, plan="free", status="active",
                               current_period_end=utcnow() - timedelta(days=5))); db.commit()
    assert [x for x in finance.run(db) if x.tool == "billing_reminder"] == []


def test_onboarding_nudges_unactivated_restaurant(world):
    db, op, owner, r, _ = world
    for _i in range(3):
        db.add(models.Order(restaurant_id=r.id, total=1, created_at=utcnow() - timedelta(days=1)))
    db.commit()
    made = customer_success.onboarding_agent(db)
    assert len(made) == 1 and "3/20" in made[0].summary and made[0].status == "pending"
    assert customer_success.onboarding_agent(db) == []


def test_engineering_warns_on_retiring_model(world, monkeypatch):
    db, *_ = world
    monkeypatch.setenv("ANTHROPIC_MODEL_LOW", "claude-haiku-4-5-20251001")
    made = engineering.run(db, today=date(2026, 10, 14))
    assert any("retires 2026-10-15" in p.summary for p in made)
    assert engineering.run(db, today=date(2026, 10, 14)) == []  # idempotent


def test_compliance_calendar(world, monkeypatch):
    db, *_ = world
    assert [k for k, _t in compliance.due_items(date(2026, 7, 1))] == [
        "restore-2026-07", "finact-2026", "models-2026-07", "ledger-2026-07"]
    assert compliance.due_items(date(2026, 8, 15)) == []
    monkeypatch.setenv("COMPANY_HAS_EMPLOYEES", "true")
    assert [k for k, _t in compliance.due_items(date(2026, 8, 2))] == ["paye-2026-08"]
    monkeypatch.setenv("COMPANY_ANNUAL_DEADLINES", "06-30:annual-return:File annual returns")
    assert compliance.due_items(date(2026, 6, 30))[0][0] == "annual-return-2026"
    assert len(compliance.run(db, today=date(2026, 8, 2))) == 1
    assert compliance.run(db, today=date(2026, 8, 2)) == []


def test_executive_brief_counts_pending_by_department(world):
    db, op, owner, r, _ = world
    kernel.propose(db, "support.ack_agent", "client_checkin",
                   {"restaurant_id": r.id, "message": "x"}, "pending thing", restaurant_id=r.id)
    assert executive.founder_load(db)["by_department"] == {"support": 1}
    brief = executive.run(db)[0]
    assert brief.status == "executed" and len(_notes(db, op)) == 1


def test_one_failing_department_does_not_stop_the_cycle(world, monkeypatch):
    db, *_ = world

    def boom(db, today=None):
        raise RuntimeError("down")
    monkeypatch.setattr(finance, "run", boom)
    res = agents.run_company_cycle(db)
    assert res["ran"] and "finance" in res["department_errors"] and res["executed"] >= 1
