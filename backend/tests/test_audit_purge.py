"""
main.py's _run_audit_log_purge_job — audit remediation, Tier 2 item 6.

AgentAuditLog was append-only with no purge job despite
docs/compliance-matrix.md documenting a "90-day rolling" DPA policy against
it. This proves the job deletes rows strictly older than 90 days and leaves
everything within the window untouched.
"""

from datetime import timedelta

import models
from time_utils import utcnow
from main import _run_audit_log_purge_job


def _make_restaurant(db_session):
    tenant = models.Tenant(name="Purge Test Tenant")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Purge Test Restaurant")
    db_session.add(restaurant)
    db_session.commit()
    return restaurant


def _make_log(db_session, restaurant_id, age_days):
    row = models.AgentAuditLog(
        restaurant_id=restaurant_id,
        action_type="price_changed",
        agent_name="pricing_intelligence",
        created_at=utcnow() - timedelta(days=age_days),
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_purge_deletes_rows_older_than_90_days_keeps_the_rest(db_session):
    restaurant = _make_restaurant(db_session)
    # Capture ids before running the job — it deletes via its own session, and
    # SQLAlchemy's expire_on_commit would otherwise try (and fail) to refresh
    # an already-deleted instance's attributes from db_session afterward.
    old_id = _make_log(db_session, restaurant.id, age_days=91).id
    boundary_id = _make_log(db_session, restaurant.id, age_days=89).id
    recent_id = _make_log(db_session, restaurant.id, age_days=1).id

    _run_audit_log_purge_job()

    remaining_ids = {r.id for r in db_session.query(models.AgentAuditLog).all()}
    assert old_id not in remaining_ids
    assert boundary_id in remaining_ids
    assert recent_id in remaining_ids


def test_purge_is_a_no_op_when_nothing_is_old_enough(db_session):
    restaurant = _make_restaurant(db_session)
    _make_log(db_session, restaurant.id, age_days=10)

    _run_audit_log_purge_job()  # must not raise, must not delete

    assert db_session.query(models.AgentAuditLog).count() == 1


def test_purge_does_not_crash_on_empty_table(db_session):
    _run_audit_log_purge_job()  # no restaurants, no rows — must not raise
    assert db_session.query(models.AgentAuditLog).count() == 0
