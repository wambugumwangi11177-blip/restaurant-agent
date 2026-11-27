"""Restock PO + invoice draft (suggest only — humans approve and act)."""
from __future__ import annotations

import json

import models
from sqlalchemy.orm import Session


def placement_actor_role(restaurant: models.Restaurant) -> str:
    mode = (restaurant.restock_routing_mode or "owner_approves").lower()
    if mode == "staples_self":
        return "stockkeeper"
    if mode == "flag_office":
        return "controller"
    return "owner"


def build_invoice_draft(db: Session, po: models.PurchaseOrder) -> dict:
    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == po.inventory_item_id).first()
    supplier = db.query(models.Supplier).filter(models.Supplier.id == po.supplier_id).first()
    unit_cents = int(po.cost_per_unit or (item.cost_per_unit or 0) * 100 if item and item.cost_per_unit else 0)
    return {
        "supplier_name": supplier.name if supplier else "",
        "lines": [
            {
                "item_name": item.item_name if item else "Stock",
                "quantity": po.quantity_ordered,
                "unit": po.unit or "",
                "unit_price_cents": unit_cents,
                "line_total_cents": int(po.total_cost or unit_cents * po.quantity_ordered),
            }
        ],
        "note": "Draft only — prices are not changed until a human approves and places the order.",
    }


def attach_draft_to_notes(po: models.PurchaseOrder, draft: dict) -> None:
    marker = "[INVOICE_DRAFT]"
    base = (po.notes or "").split(marker)[0].strip()
    po.notes = f"{base}\n{marker}{json.dumps(draft)}"


def parse_draft_from_notes(notes: str | None) -> dict | None:
    if not notes or "[INVOICE_DRAFT]" not in notes:
        return None
    try:
        raw = notes.split("[INVOICE_DRAFT]", 1)[1].strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def po_for_owner_feed(db: Session, row: models.PurchaseOrder, restaurant: models.Restaurant) -> dict:
    draft = parse_draft_from_notes(row.notes) or build_invoice_draft(db, row)
    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == row.inventory_item_id).first()
    item_name = item.item_name if item else "stock"
    actor = placement_actor_role(restaurant)
    if row.status == "PENDING":
        actor = "owner"
    elif row.status == "APPROVED":
        actor = placement_actor_role(restaurant)
    return {
        "id": row.id,
        "kind": "restock_place" if row.status == "APPROVED" else "restock",
        "status": "needs_approval",
        "item_name": item_name,
        "quantity": row.quantity_ordered,
        "unit": row.unit or "",
        "amount_cents": int(row.total_cost or 0),
        "estimated_total_cents": int(row.total_cost or 0),
        "invoice_draft": draft,
        "headline": f"Restock {row.quantity_ordered:g} {row.unit} {item_name}".strip(),
        "action": "Place supplier order" if row.status == "APPROVED" else f"Approve restock for {item_name}",
        "actor_staff_role": actor,
    }