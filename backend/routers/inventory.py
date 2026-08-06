from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from time_utils import utcnow

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

    for key, value in item_update.dict(exclude_unset=True).items():
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

    db_item.quantity += adjust.quantity  # Can be negative

    movement = models.StockMovement(
        inventory_item_id=db_item.id,
        movement_type=models.StockMovementType.ADJUST if adjust.quantity >= 0 else models.StockMovementType.OUT,
        quantity=abs(adjust.quantity),
        reason=adjust.reason or "Manual adjustment",
    )
    db.add(movement)
    db.commit()
    db.refresh(db_item)
    return {"message": f"Adjusted {db_item.item_name}", "new_quantity": db_item.quantity}


# ── Physical stock counts (shrinkage detection) ──────────────────────────────
#
# `/receive` and `/adjust` both change `InventoryItem.quantity` and both trust
# the number the caller gives them — that's correct for "20kg of chicken just
# arrived" or "we threw out 2kg", where the person entering it is describing a
# known event. A stock count is different: it's the physical shelf compared
# against what the system believes, and the whole point is that the two are
# allowed to disagree. Conflating this with `/adjust` would silently discard
# exactly the number — the variance — that makes a count worth doing.

@router.post("/{item_id}/count", response_model=schemas.StockCountOut)
async def record_stock_count(
    item_id: int,
    body: schemas.StockCountCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Record a physical count and reconcile the system to it.

    `variance = counted - expected`. Negative means less is on the shelf than
    the system expected — the shrinkage case. Positive means more than
    expected, which is a real (if less common) outcome too: a miscounted
    delivery, a correction to an earlier over-adjustment, or the count itself
    being wrong. This endpoint records what happened; it does not judge it —
    `ai/shrinkage.py` (`GET /ai/shrinkage`) is where variance across items and
    time becomes a report worth reading.

    The physical count is trusted as the new truth: `InventoryItem.quantity`
    is set to `counted_quantity`, and the reconciling delta is written to the
    existing `StockMovement` ledger (type ADJUST, tagged so it's traceable back
    to this count) so depletion prediction and every other movement-based
    analytic see one consistent number going forward — a count that's never
    reconciled would leave the system quantity permanently wrong until the
    next one.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    expected = item.quantity or 0.0
    counted = body.counted_quantity
    variance = counted - expected

    count = models.StockCount(
        restaurant_id=restaurant.id,
        inventory_item_id=item.id,
        expected_quantity=expected,
        counted_quantity=counted,
        variance=variance,
        counted_by_user_id=current_user.id,
        notes=body.notes,
    )
    db.add(count)
    db.flush()   # need count.id for the movement's reason tag below

    item.quantity = counted

    if variance != 0:
        db.add(models.StockMovement(
            inventory_item_id=item.id,
            movement_type=models.StockMovementType.ADJUST,
            quantity=abs(variance),
            reason=f"stock_count:{count.id}",
        ))

    db.commit()
    db.refresh(count)
    return {
        "id": count.id,
        "inventory_item_id": item.id,
        "item_name": item.item_name,
        "unit": item.unit,
        "expected_quantity": count.expected_quantity,
        "counted_quantity": count.counted_quantity,
        "variance": count.variance,
        "notes": count.notes,
        "created_at": count.created_at,
    }


@router.get("/{item_id}/counts", response_model=List[schemas.StockCountOut])
async def list_stock_counts(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Count history for one item, most recent first."""
    restaurant = get_or_create_restaurant(db, current_user)
    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    counts = db.query(models.StockCount).filter(
        models.StockCount.inventory_item_id == item.id
    ).order_by(models.StockCount.created_at.desc()).limit(100).all()

    return [{
        "id": c.id,
        "inventory_item_id": item.id,
        "item_name": item.item_name,
        "unit": item.unit,
        "expected_quantity": c.expected_quantity,
        "counted_quantity": c.counted_quantity,
        "variance": c.variance,
        "notes": c.notes,
        "created_at": c.created_at,
    } for c in counts]


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
