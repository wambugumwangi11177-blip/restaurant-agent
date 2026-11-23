"""Approval reminder escalation schedule."""
from datetime import timedelta

import models
from services.approval_workflow import _due_at_for_stage, ensure_reminder_row, process_due_reminders, resolve_reminder
from tests.test_storekeeper_foundation import _tenant
from time_utils import utcnow


def test_reminder_stages_fire_in_order(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "rem@eleven.leviii")
    created = utcnow() - timedelta(hours=3)
    row = models.ApprovalReminder(
        restaurant_id=restaurant.id,
        kind="waste",
        entity_id=99,
        actor_staff_role="owner",
        stage=1,
        created_at=created,
    )
    db_session.add(row)
    db_session.commit()
    assert _due_at_for_stage(created, 2) <= utcnow()
    process_due_reminders(db_session, restaurant.id)
    db_session.refresh(row)
    assert row.stage >= 2
    resolve_reminder(db_session, restaurant.id, "waste", 99)
    db_session.refresh(row)
    assert row.resolved_at is not None


def test_ensure_creates_immediate_stage(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "rem2@eleven.leviii")
    row = ensure_reminder_row(db_session, restaurant.id, "waste", 1, None)
    assert row.stage >= 1