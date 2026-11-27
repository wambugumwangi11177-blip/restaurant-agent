"""Restock queue: approvals, WhatsApp draft, mark ordered."""
from __future__ import annotations

import json
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from routers.deps import get_or_create_restaurant
from schemas import StrictModel
from services.approval_workflow import notify_requester_outcome, resolve_reminder
from time_utils import utcnow

router = APIRouter(prefix="/store/restock", tags=["store-restock"])

_FLOOR = (
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.CONTROLLER,
    models.StaffRole.MANAGER,
)


class MarkOrderedIn(StrictModel):
    po_id: int


def _po_public(db: Session, row: models.PurchaseOrder, user: models.User | None = None) -> dict:
    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == row.inventory_item_id).first()
    supplier = db.query(models.Supplier).filter(models.Supplier.id == row.supplier_id).first()
    phone = (supplier.contact_phone if supplier else "") or ""
    msg = (
        f"Order from Eleven: {row.quantity_ordered:g} {row.unit} {item.item_name if item else 'stock'}. "
        "Please confirm delivery date."
    )
    wa = ""
    if phone:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits:
            wa = f"https://wa.me/{digits}?text={urllib.parse.quote(msg)}"
    from money_visibility import hides_money, scrub_money

    payload = {
        "id": row.id,
        "status": row.status,
        "item_name": item.item_name if item else "",
        "quantity": row.quantity_ordered,
        "unit": row.unit,
        "supplier_name": supplier.name if supplier else "",
        "whatsapp_url": wa,
        "message_draft": msg,
        "cost_per_unit_cents": int(row.cost_per_unit or 0),
        "total_cost": int(row.total_cost or 0),
    }
    if user and hides_money(user, "/store/restock"):
        payload = scrub_money(payload)
    return payload


@router.get("")
async def list_restock(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_FLOOR)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.PurchaseOrder)
        .filter(
            models.PurchaseOrder.restaurant_id == restaurant.id,
            models.PurchaseOrder.status.in_(("PENDING", "SENT", "APPROVED")),
        )
        .order_by(models.PurchaseOrder.id.desc())
        .limit(40)
        .all()
    )
    return {"orders": [_po_public(db, row, current_user) for row in rows], "routing": restaurant.restock_routing_mode}


@router.post("/ordered")
async def mark_ordered(
    body: MarkOrderedIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_FLOOR)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    row = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.id == body.po_id,
        models.PurchaseOrder.restaurant_id == restaurant.id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if row.status not in ("SENT", "APPROVED"):
        raise HTTPException(status_code=400, detail="Approve the restock first")
    row.status = "SENT"
    row.ordered_by_user_id = current_user.id
    row.ordered_at = utcnow()
    db.commit()
    resolve_reminder(db, restaurant.id, "restock_place", row.id)
    return _po_public(db, row, current_user)


class StapleCapsIn(StrictModel):
    caps: dict[str, float] = Field(default_factory=dict)


@router.post("/caps")
async def save_staple_caps(
    body: StapleCapsIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_FLOOR)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    restaurant.staple_caps_json = json.dumps(
        {str(k): float(v) for k, v in body.caps.items() if float(v) > 0}
    )
    db.commit()
    return {"saved": True}