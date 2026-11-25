"""Owner Stock v11."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

import auth
import models
import storage
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
        days_label = f"{days} days left" if days is not None else "no use yet"
        rows.append(
            {
                "name": p.get("name"),
                "on_hand": p.get("current_stock"),
                "par": p.get("reorder_level"),
                "unit": p.get("unit"),
                "days_left": days,
                "days_label": days_label,
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
    rows = []
    for p in pos:
        item = (
            db.query(models.InventoryItem).filter(models.InventoryItem.id == p.inventory_item_id).first()
            if p.inventory_item_id
            else None
        )
        name = item.item_name if item else "Stock"
        rows.append(
            {
                "id": p.id,
                "item": f"{name} — {p.quantity_ordered:g} {p.unit or ''}".strip(),
                "qty": p.quantity_ordered,
                "unit": p.unit,
                "kes": (p.total_cost or 0) / 100,
            }
        )
    return {"has_data": bool(rows), "rows": rows, "empty": "Starts when stock runs low."}


@router.get("/missing")
def stock_missing(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    since = utcnow() - timedelta(days=14)
    moves = (
        db.query(models.StockMovement)
        .join(models.InventoryItem)
        .filter(
            models.InventoryItem.restaurant_id == restaurant.id,
            models.StockMovement.created_at >= since,
        )
        .order_by(models.StockMovement.id.desc())
        .limit(80)
        .all()
    )
    issued = used = 0.0
    focus_item = None
    for m in moves:
        if m.movement_type == models.StockMovementType.OUT:
            reason = (m.reason or "").lower()
            if "kitchen" in reason or "issue" in reason:
                issued += float(m.quantity or 0)
            else:
                used += float(m.quantity or 0)
            if focus_item is None:
                focus_item = db.query(models.InventoryItem).filter(models.InventoryItem.id == m.inventory_item_id).first()
    gap = max(0.0, used - issued)
    unit_cost = float((focus_item.cost_per_unit if focus_item else 120) or 120)
    photo = "/api/v1/eleven/stock/missing/photo"
    return {
        "has_data": issued + used > 0,
        "item_name": focus_item.item_name if focus_item else "Stock",
        "issued_kg": round(issued, 2),
        "used_kg": round(used, 2),
        "gap_kg": round(gap, 2),
        "kes_risk": round(gap * unit_cost, 0),
        "photo_url": photo if gap > 0 else None,
        "empty": "Starts when kitchen issues and sales move stock.",
    }


@router.get("/missing/photo")
def stock_missing_photo(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    key = f"stock-variance/{restaurant.id}/rice-gap.jpg"
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail="No photo")
    return Response(content=storage.load(key), media_type="image/jpeg")


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
    rows = []
    for s in suppliers:
        jump = "[DEMO-PRICE-JUMP]" in (s.notes or "") or "[PRICE-JUMP]" in (s.notes or "")
        rows.append(
            {
                "name": s.name,
                "lead_days": float(s.avg_lead_days or 2),
                "on_time_pct": int(s.reliability_score or 90),
                "price_jump": jump,
            }
        )
    return {"has_data": bool(rows), "rows": rows, "empty": "Starts when Jack adds suppliers."}


@router.get("/prep")
def owner_prep(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    from collections import defaultdict
    from datetime import timedelta

    items = [b for b in prep_for_today(db, restaurant.id) if "(demo)" not in (b.get("dish") or "").lower()]
    seen: set[str] = set()
    deduped: list[dict] = []
    for block in items:
        key = (block.get("dish") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(block)
    items = deduped
    weekday = utcnow().date().weekday()
    since = utcnow() - timedelta(days=35)
    orders = (
        db.query(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.created_at >= since,
            models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .all()
    )
    qty_by_dish: dict[int, list[float]] = defaultdict(list)
    for o in orders:
        if not o.created_at or o.created_at.weekday() != weekday:
            continue
        for line in o.items:
            qty_by_dish[line.menu_item_id].append(float(line.quantity))
    for block in items:
        dish_name = block.get("dish") or ""
        dish = (
            db.query(models.MenuItem)
            .filter(models.MenuItem.restaurant_id == restaurant.id, models.MenuItem.name == dish_name)
            .first()
        )
        if dish and qty_by_dish.get(dish.id):
            plates = sum(qty_by_dish[dish.id]) / len(qty_by_dish[dish.id])
        else:
            plates = sum(float(n.get("quantity") or 0) for n in block.get("ingredients") or []) / 2
        block["plates"] = max(1, round(plates))
    return {"has_data": bool(items), "items": items, "empty": "Starts when handovers and recipes exist."}