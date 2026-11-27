"""Sixteen deterministic store rules — thresholds from onboarding + item fields."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

import models
from ai.stock_custody import VARIANCE_THRESHOLD, flagged_items
from services.approval_workflow import _actor_label
from time_utils import utcnow


def _restock_actor(restaurant: models.Restaurant) -> str:
    mode = (restaurant.restock_routing_mode or "owner_approves").lower()
    if mode == "staples_self":
        return "stockkeeper"
    if mode == "flag_office":
        return "controller"
    return "owner"


def _custody_alert_headline(db: Session, restaurant_id: int, hit) -> str:
    """Plain language for variance alerts — never a misleading 100% when plates did not sell."""
    from sqlalchemy import func

    from services.plate_tracking import pos_has_dish_lines

    theo = float(hit.theoretical_usage or 0)
    act = float(hit.actual_usage or 0)
    unit = hit.unit or ""
    name = hit.item_name

    if act > 0 and theo <= 0:
        return f"{act:g} {unit} {name} went to the kitchen, no plates sold yet."

    if act > 0 and pos_has_dish_lines(db, restaurant_id):
        sold = (
            db.query(func.coalesce(func.sum(models.OrderItem.quantity), 0))
            .join(models.Order, models.Order.id == models.OrderItem.order_id)
            .join(
                models.MenuIngredient,
                models.MenuIngredient.menu_item_id == models.OrderItem.menu_item_id,
            )
            .join(models.InventoryItem, models.InventoryItem.id == models.MenuIngredient.inventory_item_id)
            .filter(
                models.Order.restaurant_id == restaurant_id,
                models.InventoryItem.id == hit.inventory_item_id,
                models.Order.status != models.OrderStatus.CANCELLED,
            )
            .scalar()
        )
        if float(sold or 0) <= 0:
            return f"{act:g} {unit} {name} went to the kitchen, no plates sold yet."

    if theo > 0:
        pct = (hit.variance_pct or 0) * 100
        if pct >= 99:
            return f"{name}: about {act:g} {unit} used vs {theo:g} {unit} expected from sold plates."
        return f"{name} use needs a look ({theo:g} {unit} expected, {act:g} {unit} recorded)."

    return f"{name} stock movement needs a look."


def run_eleven_rules(db: Session, restaurant_id: int) -> list[dict]:
    """Plain-language rule hits for owner Alerts / approvals."""
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if not restaurant:
        return []
    out: list[dict] = []
    actor_order = _restock_actor(restaurant)
    low = (
        db.query(models.InventoryItem)
        .filter(
            models.InventoryItem.restaurant_id == restaurant_id,
            models.InventoryItem.par_level.isnot(None),
        )
        .all()
    )
    for item in low:
        threshold = item.low_stock_threshold or 0
        if item.quantity <= threshold:
            out.append({
                "rule_id": "R1",
                "kind": "restock",
                "status": "needs_approval",
                "actor_staff_role": actor_order,
                "headline": f"Order in time: {item.item_name} is at {item.quantity:g} {item.unit}.",
                "action": f"Restock {item.item_name}",
                "item_name": item.item_name,
                "quantity": item.quantity,
                "unit": item.unit,
            })

    open_po = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.restaurant_id == restaurant_id,
        models.PurchaseOrder.status.in_(("PENDING", "APPROVED", "SENT")),
    ).count()
    if open_po:
        out.append({
            "rule_id": "R2",
            "kind": "restock",
            "status": "info",
            "headline": f"{open_po} purchase order(s) still in flight.",
            "action": "Check open orders",
            "actor_staff_role": actor_order,
        })

    for check in (
        db.query(models.DeliveryVisionCheck)
        .join(models.DeliveryReceipt, models.DeliveryReceipt.id == models.DeliveryVisionCheck.receipt_id)
        .filter(
            models.DeliveryReceipt.restaurant_id == restaurant_id,
            models.DeliveryVisionCheck.status == "mismatch",
        )
        .order_by(models.DeliveryVisionCheck.id.desc())
        .limit(5)
        .all()
    ):
        out.append({
            "rule_id": "R3",
            "kind": "delivery",
            "status": "needs_approval",
            "id": check.receipt_id,
            "actor_staff_role": "owner",
            "headline": "Delivery count or photo needs a look.",
            "action": "Review delivery",
        })

    today = utcnow().date()
    if not db.query(models.KitchenHandover).filter(
        models.KitchenHandover.restaurant_id == restaurant_id,
        models.KitchenHandover.created_at >= today,
    ).first():
        out.append({
            "rule_id": "R5",
            "kind": "handover",
            "status": "needs_approval",
            "actor_staff_role": "stockkeeper",
            "headline": "No kitchen handover recorded today yet.",
            "action": "Complete handover",
        })

    for row in db.query(models.RunningCost).filter(
        models.RunningCost.restaurant_id == restaurant_id,
        models.RunningCost.status == "needs_approval",
    ).limit(10):
        actor = "controller" if row.delegated_to == "accountant" or row.status == "unknown" else "owner"
        out.append({
            "rule_id": "R11",
            "kind": "cost" if row.amount_cents else "cost_unknown",
            "status": "needs_approval",
            "id": row.id,
            "actor_staff_role": actor,
            "headline": row.label or row.kind,
            "action": "Approve bill" if row.amount_cents else "Key bill amount",
            "label": row.label,
            "amount_cents": row.amount_cents,
        })

    for row in db.query(models.RunningCost).filter(
        models.RunningCost.restaurant_id == restaurant_id,
        models.RunningCost.next_due_on.isnot(None),
        models.RunningCost.next_due_on < date.today(),
        models.RunningCost.status == "approved",
    ).limit(5):
        out.append({
            "rule_id": "R11",
            "kind": "cost",
            "status": "needs_approval",
            "id": row.id,
            "actor_staff_role": "owner",
            "headline": f"Overdue: {row.label}",
            "action": "Review overdue bill",
        })

    for hit in flagged_items(db, restaurant_id)[:5]:
        out.append({
            "rule_id": "R8",
            "kind": "custody",
            "status": "needs_approval",
            "actor_staff_role": "owner",
            "headline": _custody_alert_headline(db, restaurant_id, hit),
            "action": "Review custody gap",
        })

    late = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.restaurant_id == restaurant_id,
        models.PurchaseOrder.status.in_(("SENT", "APPROVED")),
        models.PurchaseOrder.ordered_at.isnot(None),
    ).all()
    for po in late:
        supplier = db.query(models.Supplier).filter(models.Supplier.id == po.supplier_id).first()
        lead = float(supplier.avg_lead_days or 1) if supplier else 1.0
        if po.ordered_at and utcnow() > po.ordered_at + timedelta(days=lead):
            item = db.query(models.InventoryItem).filter(models.InventoryItem.id == po.inventory_item_id).first()
            out.append({
                "rule_id": "R16",
                "kind": "restock",
                "status": "needs_approval",
                "id": po.id,
                "actor_staff_role": actor_order,
                "headline": f"Late delivery: {item.item_name if item else 'order'} from {supplier.name if supplier else 'supplier'}.",
                "action": "Chase supplier",
            })

    for hit in out:
        actor = hit.get("actor_staff_role") or "owner"
        hit["approval_waiting_on"] = _actor_label(actor)
        hit["approval_needs_you"] = hit.get("status") == "needs_approval"
    return out