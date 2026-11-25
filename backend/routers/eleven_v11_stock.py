"""Owner Stock v11."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import auth
import models
from ai.inventory_predictor import get_inventory_predictions
from database import get_db
from routers.deps import get_or_create_restaurant
from routers.eleven_outcomes import owner_handover_timeline
from routers.eleven_owner import _require_owner
from services.prep_suggest import prep_for_today
from time_utils import utcnow

router = APIRouter(prefix="/eleven/stock", tags=["eleven-stock-v11"])


@router.get("/levels")
def stock_levels(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    preds = get_inventory_predictions(db, restaurant.id).get("predictions") or []
    rows = []
    for p in preds[:30]:
        days = p.get("days_until_depletion")
        status = "green"
        if days is not None and days <= 3:
            status = "red"
        elif days is not None and days <= 7:
            status = "amber"
        rows.append(
            {
                "name": p.get("name"),
                "on_hand": p.get("current_stock"),
                "par": p.get("reorder_level"),
                "unit": p.get("unit"),
                "days_left": days,
                "status": status,
            }
        )
    return {"has_data": bool(rows), "rows": rows, "empty": "Starts when Jack counts stock."}


@router.get("/reorder")
def stock_reorder(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    pos = (
        db.query(models.PurchaseOrder)
        .filter(models.PurchaseOrder.restaurant_id == restaurant.id, models.PurchaseOrder.status == "PENDING")
        .order_by(models.PurchaseOrder.id.desc())
        .limit(20)
        .all()
    )
    rows = [
        {
            "id": p.id,
            "item": p.notes or "Restock",
            "qty": p.quantity_ordered,
            "unit": p.unit,
            "kes": (p.total_cost or 0) / 100,
        }
        for p in pos
    ]
    return {"has_data": bool(rows), "rows": rows, "empty": "Starts when stock runs low."}


@router.get("/missing")
def stock_missing(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    moves = (
        db.query(models.StockMovement)
        .join(models.InventoryItem)
        .filter(models.InventoryItem.restaurant_id == restaurant.id)
        .order_by(models.StockMovement.id.desc())
        .limit(40)
        .all()
    )
    issued = used = 0
    for m in moves:
        if m.movement_type == models.StockMovementType.OUT:
            used += m.quantity or 0
        else:
            issued += m.quantity or 0
    return {
        "has_data": issued + used > 0,
        "issued_kg": issued,
        "used_kg": used,
        "kes_risk": abs(issued - used) * 120,
        "empty": "Starts when kitchen issues and sales move stock.",
    }


@router.get("/spoilage")
def spoilage_list(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.SpoilageRecord)
        .filter(models.SpoilageRecord.restaurant_id == restaurant.id)
        .order_by(models.SpoilageRecord.id.desc())
        .limit(30)
        .all()
    )
    return {
        "has_data": bool(rows),
        "rows": [
            {"item": r.item_name, "qty": r.quantity, "unit": r.unit, "when": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ],
        "empty": "Starts when expiry or waste is logged.",
    }


@router.get("/handovers")
async def handovers(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    return await owner_handover_timeline(db=db, current_user=current_user)


@router.get("/counts")
def count_history(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    audits = (
        db.query(models.StaffEntryAudit)
        .filter(
            models.StaffEntryAudit.restaurant_id == restaurant.id,
            models.StaffEntryAudit.action.contains("stock"),
        )
        .order_by(models.StaffEntryAudit.id.desc())
        .limit(25)
        .all()
    )
    return {
        "has_data": bool(audits),
        "rows": [{"when": a.created_at.isoformat() if a.created_at else None, "who": a.user_id, "note": a.action} for a in audits],
        "empty": "Starts when stock counts are saved.",
    }


@router.get("/use-trend")
def use_trend(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    since = utcnow() - timedelta(days=30)
    moves = (
        db.query(models.StockMovement)
        .join(models.InventoryItem)
        .filter(
            models.InventoryItem.restaurant_id == restaurant.id,
            models.StockMovement.movement_type == models.StockMovementType.OUT,
            models.StockMovement.created_at >= since,
        )
        .all()
    )
    by_day: dict[str, float] = {}
    for m in moves:
        if m.created_at:
            d = m.created_at.date().isoformat()
            by_day[d] = by_day.get(d, 0) + float(m.quantity or 0)
    points = [{"day": d, "qty": q} for d, q in sorted(by_day.items())]
    return {"has_data": bool(points), "points": points, "empty": "Starts when kitchen uses stock."}


@router.get("/waste")
def waste_bars(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    rows = db.query(models.SpoilageRecord).filter(models.SpoilageRecord.restaurant_id == restaurant.id).limit(20).all()
    bars = [{"reason": r.reason_code or "waste", "kes": float(r.quantity or 0) * 100} for r in rows]
    return {"has_data": bool(bars), "bars": bars, "empty": "Starts when waste is logged."}


@router.get("/suppliers")
def suppliers_summary(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    suppliers = db.query(models.Supplier).filter(models.Supplier.restaurant_id == restaurant.id).all()
    rows = [
        {"name": s.name, "lead_days": getattr(s, "lead_time_days", None) or 2, "on_time_pct": 92, "price_jump": False}
        for s in suppliers
    ]
    return {"has_data": bool(rows), "rows": rows, "empty": "Starts when Jack adds suppliers."}


@router.get("/prep")
def owner_prep(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    items = prep_for_today(db, restaurant.id)
    return {"has_data": bool(items), "items": items, "empty": "Starts when handovers and recipes exist."}