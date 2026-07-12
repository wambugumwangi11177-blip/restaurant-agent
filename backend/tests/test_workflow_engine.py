"""
Workflow Engine (Phase 8) — durable, multi-step agentic processes.

The engine must: run auto steps until it hits a pause, persist state so a run
survives across calls (proxy for surviving a restart), gate mutating steps behind
a human approval, resume correctly, cancel on rejection, and never leak a run
across tenants.
"""

from datetime import timedelta

import pytest

import models
from time_utils import utcnow
from ai import workflows


@pytest.fixture
def stocked(db_session):
    """A restaurant with a low-stock item + an active supplier so the reorder
    workflow has real work to do."""
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=None, name="WF", address="x"))
    db.add(models.InventoryItem(id=1, restaurant_id=1, item_name="Chicken",
                                quantity=1.0, unit="kg", low_stock_threshold=10))
    db.add(models.Supplier(id=1, restaurant_id=1, name="Supplier A", is_active=True))
    db.commit()
    return db


def test_start_runs_to_first_pause(stocked):
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    assert run["available"] is True
    assert run["status"] == "awaiting"                 # paused on owner approval
    # the two agent steps before the approval have run
    by_name = {s["name"]: s for s in run["steps"]}
    assert by_name["Identify shortages"]["status"] == "done"
    assert by_name["Draft purchase order"]["status"] == "done"
    assert by_name["Owner approves order"]["status"] == "awaiting"


def test_state_is_persisted_between_calls(stocked):
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    run_id = run["id"]
    # a fresh get returns the same awaiting state from the DB, not memory
    again = workflows.get_run(stocked, run_id)
    assert again["status"] == "awaiting"
    assert again["current_step"] == run["current_step"]


def test_approval_advances_and_creates_po_then_pauses_for_delivery(stocked):
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    resumed = workflows.resume(stocked, run["id"], decision="approve")
    # after approval it creates the PO (mutating step) then pauses on wait_external
    assert resumed["status"] == "awaiting"
    by_name = {s["name"]: s for s in resumed["steps"]}
    assert by_name["Create purchase order"]["status"] == "done"
    assert by_name["Wait for delivery"]["status"] == "awaiting"
    # a real PurchaseOrder row was created only AFTER approval
    assert stocked.query(models.PurchaseOrder).filter_by(restaurant_id=1).count() == 1


def test_full_run_completes_and_audits(stocked):
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    workflows.resume(stocked, run["id"], decision="approve")     # approve → create PO → wait
    final = workflows.resume(stocked, run["id"], decision="approve")  # delivery arrived
    assert final["status"] == "completed"
    assert all(s["status"] in ("done", "skipped") for s in final["steps"])
    # the PO was marked delivered and a completion audit log written
    po = stocked.query(models.PurchaseOrder).filter_by(restaurant_id=1).first()
    assert po.status == "DELIVERED"
    assert stocked.query(models.AgentAuditLog).filter_by(action_type="workflow_completed").count() == 1


def test_rejection_cancels_the_run_and_creates_no_po(stocked):
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    rejected = workflows.resume(stocked, run["id"], decision="reject")
    assert rejected["status"] == "cancelled"
    # nothing downstream ran → no purchase order was created
    assert stocked.query(models.PurchaseOrder).filter_by(restaurant_id=1).count() == 0


def test_cannot_resume_a_non_awaiting_run(stocked):
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    workflows.resume(stocked, run["id"], decision="reject")   # now cancelled
    out = workflows.resume(stocked, run["id"], decision="approve")
    assert out["available"] is False


def test_approval_requires_explicit_approve(stocked):
    """An approval step must not advance on an ambiguous decision — only an
    explicit 'approve' proceeds, so no mutating step runs by accident."""
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    out = workflows.resume(stocked, run["id"], decision="maybe")
    assert out["available"] is False
    # the run is untouched — still awaiting approval, no PO created
    state = workflows.get_run(stocked, run["id"])
    assert state["status"] == "awaiting"
    assert stocked.query(models.PurchaseOrder).filter_by(restaurant_id=1).count() == 0


def test_unknown_template_is_rejected(stocked):
    out = workflows.start_workflow(stocked, 1, "does_not_exist")
    assert out["available"] is False


def test_cancel_stops_a_run(stocked):
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    out = workflows.cancel(stocked, run["id"])
    assert out["status"] == "cancelled"
