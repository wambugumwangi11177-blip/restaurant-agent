"""
backend/routers/purchase_orders.py
──────────────────────────────────────
Purchase order lifecycle (directive 018): list, approve (send to supplier),
receive (reconcile against what was ordered). Drafting itself happens
automatically (ai/reorder.py, triggered by main.py's scheduled job) — this
router is the human-in-the-loop half: nothing reaches a supplier or updates
stock without someone here.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from ai import reorder as reorder_engine

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])

_CAN_APPROVE = (models.StaffRole.MANAGER, models.StaffRole.SUPERVISOR)
_CAN_RECEIVE = (models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER)
# Supervisor must be able to list orders to approve them — was missing here
# even though _CAN_APPROVE already included Supervisor, which meant an
# approver could never actually see what needed approving (verified: the
# frontend's PurchasingWorkspace fetches this endpoint on load and shows a
# hard "forbidden" screen on any 403).
_CAN_READ = (models.StaffRole.MANAGER, models.StaffRole.SUPERVISOR, models.StaffRole.CONTROLLER, models.StaffRole.STOCKKEEPER)


def _po_out(po: models.PurchaseOrder, db: Session) -> dict:
    supplier = db.query(models.Supplier).filter(models.Supplier.id == po.supplier_id).first()
    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == po.inventory_item_id).first() if po.inventory_item_id else None
    return {
        "id": po.id,
        "restaurant_id": po.restaurant_id,
        "supplier_id": po.supplier_id,
        "inventory_item_id": po.inventory_item_id,
        "quantity_ordered": po.quantity_ordered,
        "quantity_received": po.quantity_received,
        "unit": po.unit,
        "cost_per_unit": po.cost_per_unit,
        "total_cost": po.total_cost,
        "status": po.status,
        "ordered_at": po.ordered_at,
        "expected_at": po.expected_at,
        "delivered_at": po.delivered_at,
        "notes": po.notes,
        "supplier_name": supplier.name if supplier else None,
        "item_name": item.item_name if item else None,
    }


@router.get("/", response_model=List[schemas.PurchaseOrderOut])
async def list_purchase_orders(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_READ)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    q = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.restaurant_id == restaurant.id
    )
    if status:
        q = q.filter(models.PurchaseOrder.status == status.upper())
    orders = q.order_by(models.PurchaseOrder.id.desc()).limit(200).all()
    return [_po_out(po, db) for po in orders]


@router.post("/{po_id}/approve", response_model=schemas.PurchaseOrderOut)
async def approve_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_APPROVE)),
):
    """The approval gate — nothing is sent to a supplier without this."""
    restaurant = get_or_create_restaurant(db, current_user)
    try:
        po = reorder_engine.approve_and_send(db, po_id, restaurant.id, current_user.email)
    except reorder_engine.PurchaseOrderError as exc:
        status_code = 404 if str(exc) == "Purchase order not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc))
    return _po_out(po, db)


@router.post("/{po_id}/receive", response_model=schemas.PurchaseOrderOut)
async def receive_purchase_order(
    po_id: int,
    body: schemas.PurchaseOrderReceive,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_RECEIVE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    try:
        po = reorder_engine.receive_purchase_order(
            db, po_id, restaurant.id, body.quantity_received,
            current_user.id, body.notes,
        )
    except reorder_engine.PurchaseOrderError as exc:
        status_code = 404 if str(exc) == "Purchase order not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc))
    return _po_out(po, db)
