"""
backend/ai/workflows/templates.py
───────────────────────────────────
Workflow templates + step handlers (Phase 8).

A template is an ordered list of step specs. A step's `type` drives the executor
(agent_call / human_approval / wait_external / notify — see models.WorkflowStep);
`handler` names a deterministic function run for agent_call / notify steps.

Handlers reuse the existing deterministic agents (inventory predictor, suppliers,
purchase orders, audit log). They must be tolerant of thin/empty data — a step
records what it found and moves on; it never crashes the run.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

import models

logger = logging.getLogger("ai.workflows")


# ── Step handlers (deterministic) ──────────────────────────────────────────────
# Each: (db, restaurant_id, context) -> dict output. May mutate `context` in place
# (it is persisted between steps on the WorkflowRun).

def h_identify_shortages(db: Session, restaurant_id: int, ctx: dict) -> dict:
    from ai.inventory_predictor import get_inventory_predictions
    data = get_inventory_predictions(db, restaurant_id)
    shortages = [
        {"item_id": p.get("item_id") or p.get("id"), "name": p.get("name") or p.get("item_name")}
        for p in data.get("predictions", [])
        if p.get("status") in ("critical", "low", "reorder")
    ]
    ctx["shortages"] = shortages
    return {"shortage_count": len(shortages)}


def h_draft_purchase_order(db: Session, restaurant_id: int, ctx: dict) -> dict:
    shortages = ctx.get("shortages") or []
    supplier = (
        db.query(models.Supplier)
        .filter(models.Supplier.restaurant_id == restaurant_id,
                models.Supplier.is_active == True)  # noqa: E712
        .first()
    )
    if not shortages or supplier is None:
        ctx["draft_po"] = None
        return {"drafted": False, "reason": "no shortages or no active supplier"}
    target = shortages[0]
    draft = {"item_id": target["item_id"], "supplier_id": supplier.id,
             "supplier_name": supplier.name, "quantity": 10}
    ctx["draft_po"] = draft
    return {"drafted": True, **draft}


def h_create_purchase_order(db: Session, restaurant_id: int, ctx: dict) -> dict:
    """
    Runs after the human_approval step has already resolved (approved by a
    human via resume(), or auto-approved by supplier trust — see
    ai/workflows/engine.py::_is_auto_approvable). Creates PENDING then routes
    through reorder_engine.approve_and_send — the SAME single approval/send
    path routers/purchase_orders.py's manual endpoint uses — instead of
    writing status="SENT" directly. That used to skip the supplier WhatsApp
    notification and the audit log entirely (Sprint 5 fix: two approval
    paths existed, only one of them actually notified anyone).
    """
    draft = ctx.get("draft_po")
    if not draft:
        return {"created": False, "reason": "no draft to create"}
    po = models.PurchaseOrder(
        restaurant_id=restaurant_id,
        supplier_id=draft["supplier_id"],
        inventory_item_id=draft.get("item_id"),
        quantity_ordered=draft.get("quantity", 10),
        unit="unit",
        status="PENDING",
    )
    db.add(po)
    db.commit()
    db.refresh(po)
    ctx["po_id"] = po.id

    from ai.reorder import approve_and_send
    approved_by = ctx.get("approved_by") or "workflow"
    approve_and_send(db, po.id, restaurant_id, approved_by)

    return {"created": True, "po_id": po.id, "approved_by": approved_by}


def h_receive_delivery(db: Session, restaurant_id: int, ctx: dict) -> dict:
    po_id = ctx.get("po_id")
    if not po_id:
        return {"received": False}
    po = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.id == po_id,
        models.PurchaseOrder.restaurant_id == restaurant_id,
    ).first()
    if po:
        po.status = "DELIVERED"
        po.quantity_received = po.quantity_ordered
        db.commit()
    return {"received": bool(po)}


def h_notify_owner(db: Session, restaurant_id: int, ctx: dict) -> dict:
    from ai.evaluation.tracker import write_audit_log
    po_id = ctx.get("po_id")
    write_audit_log(
        db, restaurant_id, "workflow_completed", "workflow_engine",
        entity_type="purchase_order", entity_id=po_id,
        reasoning="Low-stock reorder workflow completed.",
        data_sources=["inventory_predictor", "suppliers", "purchase_orders"],
        approved_by="workflow",
    )
    return {"notified": True}


HANDLERS = {
    "identify_shortages": h_identify_shortages,
    "draft_purchase_order": h_draft_purchase_order,
    "create_purchase_order": h_create_purchase_order,
    "receive_delivery": h_receive_delivery,
    "notify_owner": h_notify_owner,
}


# ── Templates ──────────────────────────────────────────────────────────────────

TEMPLATES: dict[str, list[dict]] = {
    # Stock low → draft PO → owner approves → create PO → wait for delivery →
    # update inventory → notify. The canonical long-running agentic process.
    "low_stock_reorder": [
        {"name": "Identify shortages", "type": "agent_call", "handler": "identify_shortages"},
        {"name": "Draft purchase order", "type": "agent_call", "handler": "draft_purchase_order"},
        {"name": "Owner approves order", "type": "human_approval", "handler": None},
        {"name": "Create purchase order", "type": "agent_call", "handler": "create_purchase_order"},
        {"name": "Wait for delivery", "type": "wait_external", "handler": None},
        {"name": "Update inventory", "type": "agent_call", "handler": "receive_delivery"},
        {"name": "Notify owner", "type": "notify", "handler": "notify_owner"},
    ],
}


def template_names() -> list[str]:
    return sorted(TEMPLATES.keys())
