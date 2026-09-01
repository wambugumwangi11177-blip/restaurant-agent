from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from time_utils import utcnow, aware_utcnow
import time_utils

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/", response_model=List[schemas.InventoryItemOut])
async def get_inventory(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    return db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant.id
    ).order_by(models.InventoryItem.item_name).all()


@router.get("/summary")
async def get_inventory_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Rich inventory view with par, on-order, value, and status."""
    restaurant = get_or_create_restaurant(db, current_user)
    items = db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant.id
    ).order_by(models.InventoryItem.item_name).all()

    total_value_cents = 0
    items_out = []
    low_count = 0

    for item in items:
        val_cents = int((item.quantity or 0) * (item.cost_per_unit or 0) * 100)
        total_value_cents += val_cents

        # Check pending purchase orders for this item
        po_qty = db.query(models.PurchaseOrder).filter(
            models.PurchaseOrder.inventory_item_id == item.id,
            models.PurchaseOrder.status.in_(["PENDING", "SENT"]),
        ).all()
        on_order = sum(p.quantity_ordered for p in po_qty)

        is_low = (item.quantity or 0) <= (item.low_stock_threshold or 0)
        if is_low:
            low_count += 1

        status_label = "critical" if item.quantity <= 0 else ("low" if is_low else "healthy")

        items_out.append({
            "id": item.id,
            "item_name": item.item_name,
            "quantity": item.quantity,
            "unit": item.unit,
            "cost_per_unit": item.cost_per_unit,
            "low_stock_threshold": item.low_stock_threshold,
            "expiry_days": item.expiry_days,
            "on_order": on_order,
            "value_cents": val_cents,
            "status": status_label,
        })

    return {
        "items": items_out,
        "total_items": len(items),
        "low_stock_count": low_count,
        "total_inventory_value_cents": total_value_cents,
    }


@router.post("/", response_model=schemas.InventoryItemOut)
async def create_inventory_item(
    item: schemas.InventoryItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name=item.item_name,
        quantity=item.quantity,
        unit=item.unit,
        cost_per_unit=item.cost_per_unit,
        low_stock_threshold=item.low_stock_threshold,
        expiry_days=item.expiry_days,
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.put("/{item_id}", response_model=schemas.InventoryItemOut)
async def update_inventory_item(
    item_id: int,
    item_update: schemas.InventoryItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    for key, value in item_update.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)

    db.commit()
    db.refresh(db_item)
    return db_item


@router.post("/{item_id}/receive")
async def receive_stock(
    item_id: int,
    receive: schemas.StockReceive,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Record stock received from supplier — increases quantity."""
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    db_item.quantity += receive.quantity
    if receive.cost_per_unit is not None:
        db_item.cost_per_unit = receive.cost_per_unit

    movement = models.StockMovement(
        inventory_item_id=db_item.id,
        movement_type=models.StockMovementType.IN,
        quantity=receive.quantity,
        reason=f"Received from {receive.supplier}" if receive.supplier else "Stock received",
        user_id=current_user.id,
    )
    db.add(movement)
    db.commit()
    db.refresh(db_item)
    return {"message": f"Received {receive.quantity} {db_item.unit} of {db_item.item_name}", "new_quantity": db_item.quantity}


@router.post("/{item_id}/adjust")
async def adjust_stock(
    item_id: int,
    adjust: schemas.StockAdjust,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Adjust stock for waste, breakage, or corrections."""
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    db_item.quantity += adjust.quantity

    movement = models.StockMovement(
        inventory_item_id=db_item.id,
        movement_type=models.StockMovementType.ADJUST if adjust.quantity >= 0 else models.StockMovementType.OUT,
        quantity=abs(adjust.quantity),
        reason=adjust.reason or "Manual adjustment",
        user_id=current_user.id,
    )
    db.add(movement)
    db.commit()
    db.refresh(db_item)
    return {"message": f"Adjusted {db_item.item_name}", "new_quantity": db_item.quantity}


# ── Waste Logs ──

@router.post("/waste", response_model=schemas.WasteLogOut)
async def log_waste(
    body: schemas.WasteLogCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == body.inventory_item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    # Decrement on-hand
    item.quantity = max(0.0, (item.quantity or 0.0) - body.quantity)
    cost_cents = int(body.quantity * (item.cost_per_unit or 0) * 100)

    waste = models.WasteLog(
        restaurant_id=restaurant.id,
        inventory_item_id=item.id,
        user_id=current_user.id,
        quantity=body.quantity,
        unit=item.unit,
        reason=body.reason,
        cost_cents=cost_cents,
        notes=body.notes or "",
    )
    db.add(waste)

    # Also log StockMovement
    db.add(models.StockMovement(
        inventory_item_id=item.id,
        movement_type=models.StockMovementType.OUT,
        quantity=body.quantity,
        reason=f"Waste: {body.reason}",
        user_id=current_user.id,
    ))

    db.commit()
    db.refresh(waste)

    return {
        "id": waste.id,
        "inventory_item_id": waste.inventory_item_id,
        "item_name": item.item_name,
        "user_id": waste.user_id,
        "quantity": waste.quantity,
        "unit": waste.unit,
        "reason": waste.reason,
        "cost_cents": waste.cost_cents,
        "notes": waste.notes or "",
        "created_at": waste.created_at,
    }


@router.get("/waste", response_model=List[schemas.WasteLogOut])
async def list_waste(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    wastes = db.query(models.WasteLog).options(
        joinedload(models.WasteLog.inventory_item)
    ).filter(
        models.WasteLog.restaurant_id == restaurant.id
    ).order_by(models.WasteLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id": w.id,
            "inventory_item_id": w.inventory_item_id,
            "item_name": w.inventory_item.item_name if w.inventory_item else "",
            "user_id": w.user_id,
            "quantity": w.quantity,
            "unit": w.unit,
            "reason": w.reason,
            "cost_cents": w.cost_cents,
            "notes": w.notes or "",
            "created_at": w.created_at,
        }
        for w in wastes
    ]


# ── Inventory Count Sheets ──

@router.post("/counts", response_model=schemas.InventoryCountOut)
async def create_count_sheet(
    body: schemas.InventoryCountCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    today = time_utils.business_today(restaurant)

    count = models.InventoryCount(
        restaurant_id=restaurant.id,
        user_id=current_user.id,
        count_date=today,
        status="draft",
        notes=body.notes or "",
    )
    db.add(count)
    db.flush()

    for line in body.lines:
        item = db.query(models.InventoryItem).filter(
            models.InventoryItem.id == line.inventory_item_id,
            models.InventoryItem.restaurant_id == restaurant.id,
        ).first()
        if item:
            theory = item.quantity or 0.0
            variance = line.counted_qty - theory
            db.add(models.InventoryCountLine(
                count_id=count.id,
                inventory_item_id=item.id,
                theoretical_qty=theory,
                counted_qty=line.counted_qty,
                variance_qty=variance,
            ))

    db.commit()
    db.refresh(count)
    return _count_to_dict(count)


@router.post("/counts/{count_id}/post", response_model=schemas.InventoryCountOut)
async def post_count_sheet(
    count_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    count = db.query(models.InventoryCount).options(
        joinedload(models.InventoryCount.lines).joinedload(models.InventoryCountLine.inventory_item)
    ).filter(
        models.InventoryCount.id == count_id,
        models.InventoryCount.restaurant_id == restaurant.id,
    ).first()
    if not count:
        raise HTTPException(status_code=404, detail="Count sheet not found")
    if count.status == "posted":
        return _count_to_dict(count)

    # Adjust on-hand for each line
    for line in count.lines:
        item = line.inventory_item
        if item:
            diff = line.counted_qty - (item.quantity or 0.0)
            item.quantity = line.counted_qty
            if abs(diff) > 0.001:
                db.add(models.StockMovement(
                    inventory_item_id=item.id,
                    movement_type=models.StockMovementType.ADJUST if diff >= 0 else models.StockMovementType.OUT,
                    quantity=abs(diff),
                    reason=f"Count sheet #{count.id} adjustment (variance {diff:+.2f} {item.unit})",
                    user_id=current_user.id,
                ))

    count.status = "posted"
    count.posted_at = utcnow()
    db.commit()
    db.refresh(count)
    return _count_to_dict(count)


@router.get("/counts", response_model=List[schemas.InventoryCountOut])
async def list_counts(
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    counts = db.query(models.InventoryCount).options(
        joinedload(models.InventoryCount.lines).joinedload(models.InventoryCountLine.inventory_item)
    ).filter(
        models.InventoryCount.restaurant_id == restaurant.id
    ).order_by(models.InventoryCount.created_at.desc()).limit(limit).all()

    return [_count_to_dict(c) for c in counts]


def _count_to_dict(c: models.InventoryCount) -> dict:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "count_date": c.count_date,
        "status": c.status,
        "notes": c.notes or "",
        "created_at": c.created_at,
        "posted_at": c.posted_at,
        "lines": [
            {
                "id": line.id,
                "inventory_item_id": line.inventory_item_id,
                "item_name": line.inventory_item.item_name if line.inventory_item else "",
                "unit": line.inventory_item.unit if line.inventory_item else "",
                "theoretical_qty": line.theoretical_qty,
                "counted_qty": line.counted_qty,
                "variance_qty": line.variance_qty,
            }
            for line in c.lines
        ],
    }


@router.delete("/{item_id}")
async def delete_inventory_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(db_item)
    db.commit()
    return {"message": "Item deleted"}

