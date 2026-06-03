from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _get_restaurant(db: Session, user: models.User):
    rest = db.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == user.tenant_id
    ).first()
    if not rest:
        rest = models.Restaurant(
            name=f"{user.tenant.name}'s Restaurant",
            tenant_id=user.tenant_id,
        )
        db.add(rest)
        db.commit()
        db.refresh(rest)
    return rest


@router.get("/", response_model=List[schemas.InventoryItemOut])
async def get_inventory(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = _get_restaurant(db, current_user)
    return db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant.id
    ).order_by(models.InventoryItem.item_name).all()


@router.post("/", response_model=schemas.InventoryItemOut)
async def create_inventory_item(
    item: schemas.InventoryItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = _get_restaurant(db, current_user)
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
    current_user: models.User = Depends(auth.get_current_user),
):
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id
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
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id
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
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id
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


@router.delete("/{item_id}")
async def delete_inventory_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(db_item)
    db.commit()
    return {"message": "Item deleted"}
