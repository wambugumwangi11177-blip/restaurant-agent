"""Owner decision detail payloads (all kinds share one shape)."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy.orm import Session

import models
from ai.inventory_predictor import get_inventory_predictions
from routers.store_control import list_approvals
from services.approval_workflow import _actor_label, approval_type_label
from services.owner_display import owner_facing_label, owner_facing_text
from services.restock_workflow import build_invoice_draft, parse_draft_from_notes, placement_actor_role
from time_utils import utcnow


def _usage_sparkline(db: Session, restaurant_id: int, item_id: int, days: int = 14) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    rows = (
        db.query(models.StockMovement)
        .filter(
            models.StockMovement.inventory_item_id == item_id,
            models.StockMovement.movement_type == models.StockMovementType.OUT,
            models.StockMovement.created_at >= since,
        )
        .all()
    )
    by_day: dict[str, float] = defaultdict(float)
    for m in rows:
        if m.created_at:
            by_day[m.created_at.date().isoformat()] += float(m.quantity or 0)
    start = (utcnow() - timedelta(days=days - 1)).date()
    out = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        out.append({"day": d[5:], "qty": round(by_day.get(d, 0), 2)})
    return out


def _pred_for_item(db: Session, restaurant_id: int, item_name: str) -> dict | None:
    preds = get_inventory_predictions(db, restaurant_id).get("predictions") or []
    for p in preds:
        if (p.get("name") or "").lower() == item_name.lower():
            return p
    return None


async def build_decision_detail(
    db: Session,
    restaurant: models.Restaurant,
    current_user: models.User,
    kind: str,
    item_id: int,
) -> dict:
    feed = await list_approvals(db=db, current_user=current_user)
    pending = feed.get("pending") or []
    match = next((p for p in pending if p.get("kind") == kind and int(p.get("id")) == item_id), None)
    if not match:
        events = feed.get("events") or []
        match = next((p for p in events if p.get("kind") == kind and int(p.get("id")) == item_id), None)
    if not match:
        return {}
    base = {
        "id": item_id,
        "kind": kind,
        "headline": owner_facing_text(match.get("headline") or match.get("approval_card_title") or ""),
        "freshness": "Live · from your records",
        "can_act": bool(match.get("approval_viewer_is_actor") and match.get("status") == "needs_approval"),
        "photo_url": match.get("photo_path"),
    }
    if kind in ("restock", "restock_place"):
        row = (
            db.query(models.PurchaseOrder)
            .filter(models.PurchaseOrder.id == item_id, models.PurchaseOrder.restaurant_id == restaurant.id)
            .first()
        )
        if not row:
            return {**base, "why": "Restock request.", "what_we_saw": [], "numbers": {}}
        item = db.query(models.InventoryItem).filter(models.InventoryItem.id == row.inventory_item_id).first()
        supplier = db.query(models.Supplier).filter(models.Supplier.id == row.supplier_id).first()
        pred = _pred_for_item(db, restaurant.id, item.item_name if item else "") if item else None
        days_left = pred.get("days_until_depletion") if pred else None
        use_day = (pred.get("daily_usage_recent_7d") or pred.get("daily_usage_avg")) if pred else None
        on_hand = float(item.quantity or 0) if item else None
        par = float(item.par_level or item.low_stock_threshold or 0) if item else None
        lead = float(supplier.avg_lead_days or 2) if supplier else 2.0
        if days_left is not None:
            why = f"{item.item_name if item else 'Stock'} runs out in about {days_left} days; supplier needs {lead:g} days to deliver."
        else:
            why = f"{item.item_name if item else 'Stock'} is low; supplier needs {lead:g} days to deliver."
        unit_cents = int(row.cost_per_unit or (item.cost_per_unit or 0) if item else 0)
        if unit_cents and unit_cents < 500:
            unit_cents *= 100
        total_cents = int(row.total_cost or unit_cents * row.quantity_ordered)
        draft = parse_draft_from_notes(row.notes) or build_invoice_draft(db, row)
        next_role = placement_actor_role(restaurant) if kind == "restock" and row.status == "PENDING" else match.get("actor_staff_role") or "stockkeeper"
        return {
            **base,
            "why": why,
            "what_we_saw": [
                {"label": "On hand", "value": f"{on_hand:g} {row.unit}" if on_hand is not None else "—"},
                {"label": "Usual use", "value": f"{use_day:g} {row.unit}/day" if use_day else "—"},
                {"label": "Par", "value": f"{par:g} {row.unit}" if par else "—"},
                {"label": "Lead time", "value": f"{lead:g} days"},
            ],
            "usage_sparkline": _usage_sparkline(db, restaurant.id, row.inventory_item_id) if row.inventory_item_id else [],
            "numbers": {
                "qty": f"{row.quantity_ordered:g} {row.unit}",
                "unit_price_kes": unit_cents / 100.0,
                "total_kes": total_cents / 100.0,
            },
            "next_step": f"Next: {_actor_label(next_role)} places the order",
            "po_draft": draft,
            "invoice_draft_note": "Draft only — prices are not changed until you approve.",
        }
    if kind in ("cost", "cost_unknown"):
        row = db.query(models.RunningCost).filter(models.RunningCost.id == item_id).first()
        label = owner_facing_label(row.label if row else match.get("label"))
        why = owner_facing_text(match.get("owner_note") or "") or f"{label} needs a number before it can sit in your monthly costs."
        nums = {}
        if row and row.amount_cents:
            nums = {"amount_kes": row.amount_cents / 100.0, "label": label}
        actor = match.get("approval_waiting_on") or _actor_label(match.get("actor_staff_role") or "owner")
        return {
            **base,
            "headline": label or base["headline"],
            "why": why,
            "what_we_saw": [{"label": "Bill", "value": label}],
            "usage_sparkline": [],
            "numbers": nums,
            "next_step": f"Waiting on {actor} to key the amount" if kind == "cost_unknown" else "Approve to add this cost",
        }
    if kind in ("waste", "spoilage"):
        row = db.query(models.SpoilageRecord).filter(models.SpoilageRecord.id == item_id).first()
        why = owner_facing_text(match.get("approval_reason_line") or match.get("headline") or "Staff logged waste.")
        what = []
        if row:
            what = [
                {"label": "Item", "value": row.item_name},
                {"label": "Quantity", "value": f"{row.quantity:g} {row.unit or ''}".strip()},
            ]
        return {
            **base,
            "why": why,
            "what_we_saw": what,
            "usage_sparkline": [],
            "numbers": {"amount_kes": (match.get("amount_cents") or 0) / 100},
            "next_step": "You approve or decline the write-off",
        }
    type_label = approval_type_label(kind)
    why = owner_facing_text(match.get("approval_reason_line") or match.get("headline") or type_label)
    what = [{"label": "Detail", "value": owner_facing_text(b)} for b in (match.get("approval_detail_bullets") or [])[:4]]
    return {
        **base,
        "why": why,
        "what_we_saw": what,
        "usage_sparkline": [],
        "numbers": {"amount_kes": (match.get("amount_cents") or match.get("estimated_total_cents") or 0) / 100},
        "next_step": match.get("action") or f"Review this {type_label.lower()}",
    }