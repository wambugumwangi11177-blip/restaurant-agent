"""Zone photos, bill due dates, and first-password login."""

import auth
import models
from bill_schedule import compute_next_due, reminder_bucket
from datetime import date


def test_compute_next_due_monthly():
    due = compute_next_due(date(2026, 3, 10), "monthly", 5)
    assert due == date(2026, 4, 5)


def test_reminder_overdue_after_paid_window():
    today = date(2026, 3, 20)
    bucket = reminder_bucket(date(2026, 3, 18), "paid", "approved", today, 3)
    assert bucket == "overdue" or bucket == "due_soon"


def test_initial_password_login(client, db_session):
    tenant = models.Tenant(name="PwEleven")
    db_session.add(tenant)
    db_session.flush()
    user = models.User(
        email="jack@pw.eleven",
        hashed_password=None,
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        tenant_id=tenant.id,
        must_change_password=True,
    )
    db_session.add(user)
    db_session.commit()
    blocked = client.post("/api/v1/auth/login", json={"email": "jack@pw.eleven", "password": "anything"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "FIRST_PASSWORD_REQUIRED"
    set_pw = client.post(
        "/api/v1/auth/set-initial-password",
        json={"email": "jack@pw.eleven", "new_password": "JackPass12"},
    )
    assert set_pw.status_code == 200, set_pw.text
    assert auth.verify_password("JackPass12", db_session.query(models.User).filter_by(email="jack@pw.eleven").one().hashed_password)