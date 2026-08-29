"""
Sprint 5 of the fraud-detection/tiered-approval build: tiered PO
auto-approval in ai/workflows/engine.py, plus the h_create_purchase_order fix
that routes every workflow-created PO through the same approve_and_send path
routers/purchase_orders.py's manual endpoint uses (previously it wrote
status="SENT" directly, skipping the supplier notification and audit log).

Fixture mirrors tests/test_workflow_engine.py's `stocked` fixture exactly
(same restaurant/item/supplier shape) so behavior is directly comparable.
"""

import models
from ai import workflows
from ai.workflows.engine import MIN_CLOSED_ORDERS_FOR_TRUST, AUTO_APPROVE_RELIABILITY_MIN
import pytest


@pytest.fixture
def stocked(db_session):
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=None, name="WF", address="x"))
    db.add(models.InventoryItem(id=1, restaurant_id=1, item_name="Chicken",
                                quantity=1.0, unit="kg", low_stock_threshold=10))
    db.add(models.Supplier(id=1, restaurant_id=1, name="Supplier A", is_active=True))
    db.commit()
    return db


def _add_closed_orders(db, supplier_id, restaurant_id, count, status="DELIVERED"):
    for i in range(count):
        db.add(models.PurchaseOrder(
            restaurant_id=restaurant_id, supplier_id=supplier_id,
            quantity_ordered=1, unit="kg", status=status,
        ))
    db.commit()


# ── New, unproven supplier (default reliability_score=100.0) never auto-approves ──

def test_new_supplier_with_no_history_still_requires_approval(stocked):
    """This is the regression this sprint had to guard against: a brand-new
    Supplier row defaults to reliability_score=100.0, which must NOT read as
    'trusted' — trust requires an actual track record."""
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    assert run["status"] == "awaiting"   # still pauses — no shortcut for an unproven supplier


# ── Reliability-derived trust, once there's a track record ─────────────────

def test_reliable_supplier_with_track_record_auto_approves(stocked):
    supplier = stocked.query(models.Supplier).filter_by(id=1).first()
    supplier.reliability_score = AUTO_APPROVE_RELIABILITY_MIN + 5
    stocked.commit()
    _add_closed_orders(stocked, supplier.id, 1, MIN_CLOSED_ORDERS_FOR_TRUST)

    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    assert run["status"] == "awaiting"   # pauses on Wait for delivery, not on approval

    by_name = {s["name"]: s for s in run["steps"]}
    assert by_name["Owner approves order"]["status"] == "done"
    assert by_name["Owner approves order"]["output"]["auto"] is True
    assert by_name["Create purchase order"]["status"] == "done"
    assert by_name["Wait for delivery"]["status"] == "awaiting"

    po = stocked.query(models.PurchaseOrder).filter_by(
        restaurant_id=1
    ).order_by(models.PurchaseOrder.id.desc()).first()
    assert po is not None
    assert po.status == "SENT"   # went through approve_and_send, not left PENDING


def test_unreliable_supplier_with_track_record_still_requires_approval(stocked):
    supplier = stocked.query(models.Supplier).filter_by(id=1).first()
    supplier.reliability_score = AUTO_APPROVE_RELIABILITY_MIN - 10
    stocked.commit()
    _add_closed_orders(stocked, supplier.id, 1, MIN_CLOSED_ORDERS_FOR_TRUST)

    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    assert run["status"] == "awaiting"
    by_name = {s["name"]: s for s in run["steps"]}
    assert by_name["Owner approves order"]["status"] == "awaiting"


def test_high_reliability_but_insufficient_history_still_requires_approval(stocked):
    supplier = stocked.query(models.Supplier).filter_by(id=1).first()
    supplier.reliability_score = 99.0
    stocked.commit()
    _add_closed_orders(stocked, supplier.id, 1, MIN_CLOSED_ORDERS_FOR_TRUST - 1)  # one short

    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    assert run["status"] == "awaiting"
    by_name = {s["name"]: s for s in run["steps"]}
    assert by_name["Owner approves order"]["status"] == "awaiting"


# ── Explicit owner override always wins ─────────────────────────────────────

def test_explicit_requires_approval_false_auto_approves_even_with_no_history(stocked):
    """An owner's explicit trust override bypasses the cold-start guard too —
    that's the point of an EXPLICIT override, unlike the derived path."""
    supplier = stocked.query(models.Supplier).filter_by(id=1).first()
    supplier.requires_approval = False
    stocked.commit()

    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    by_name = {s["name"]: s for s in run["steps"]}
    assert by_name["Owner approves order"]["status"] == "done"
    assert by_name["Owner approves order"]["output"]["auto"] is True


def test_explicit_requires_approval_true_overrides_high_reliability(stocked):
    """Owner explicitly does NOT trust this supplier — even a perfect score
    and long history must not auto-approve."""
    supplier = stocked.query(models.Supplier).filter_by(id=1).first()
    supplier.requires_approval = True
    supplier.reliability_score = 100.0
    stocked.commit()
    _add_closed_orders(stocked, supplier.id, 1, MIN_CLOSED_ORDERS_FOR_TRUST + 5)

    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    assert run["status"] == "awaiting"
    by_name = {s["name"]: s for s in run["steps"]}
    assert by_name["Owner approves order"]["status"] == "awaiting"


# ── Human approval path still carries the real approver through ────────────

def test_human_approval_attributes_approved_by_to_the_real_user(stocked):
    run = workflows.start_workflow(stocked, 1, "low_stock_reorder")
    workflows.resume(stocked, run["id"], decision="approve", approved_by="manager@restaurant.com")

    po = stocked.query(models.PurchaseOrder).filter_by(restaurant_id=1).first()
    assert po is not None
    assert po.status == "SENT"

    audit = stocked.query(models.AgentAuditLog).filter_by(
        restaurant_id=1, action_type="purchase_order_sent",
    ).first()
    assert audit is not None
    assert audit.approved_by == "manager@restaurant.com"


def test_auto_approval_writes_its_own_audit_log_entry(stocked):
    supplier = stocked.query(models.Supplier).filter_by(id=1).first()
    supplier.requires_approval = False
    stocked.commit()

    workflows.start_workflow(stocked, 1, "low_stock_reorder")

    auto_audit = stocked.query(models.AgentAuditLog).filter_by(
        restaurant_id=1, action_type="purchase_order_auto_approved",
    ).first()
    assert auto_audit is not None
    assert auto_audit.approved_by == "auto:supplier_trust"

    sent_audit = stocked.query(models.AgentAuditLog).filter_by(
        restaurant_id=1, action_type="purchase_order_sent",
    ).first()
    assert sent_audit is not None
    assert sent_audit.approved_by == "auto:supplier_trust"
