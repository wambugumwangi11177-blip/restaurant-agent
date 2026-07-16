from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant

router = APIRouter(prefix="/inventory", tags=["inventory"])

# Directive 015's permission matrix for `inventory`: RW = Owner, Manager,
# Stockkeeper; R = Controller, Kitchen; nothing for Supervisor/Waiter. Owner
# passes through every require_staff_role() call automatically (Role.ADMIN
# bypass), so it isn't listed explicitly below.
_CAN_WRITE = (models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER)
_CAN_READ = (models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER,
             models.StaffRole.CONTROLLER, models.StaffRole.KITCHEN)


@router.get("/", response_model=List[schemas.InventoryItemOut])
async def get_inventory(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_READ)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    return db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant.id
    ).order_by(models.InventoryItem.item_name).all()


@router.post("/", response_model=schemas.InventoryItemOut)
async def create_inventory_item(
    item: schemas.InventoryItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
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
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
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
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
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
        performed_by_user_id=current_user.id,
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
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
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
        performed_by_user_id=current_user.id,
    )
    db.add(movement)
    db.commit()
    db.refresh(db_item)
    return {"message": f"Adjusted {db_item.item_name}", "new_quantity": db_item.quantity}


@router.delete("/{item_id}")
async def delete_inventory_item(
    item_id: int,
    db: Session = Depends(get_db),
    # Deleting an item definition (not adjusting its quantity) is more
    # structural than the matrix's RW label implies — Stockkeeper can
    # receive/adjust stock but not remove the item record itself.
    current_user: models.User = Depends(auth.require_staff_role(models.StaffRole.MANAGER)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    db.delete(db_item)
    try:
        db.commit()
    except IntegrityError:
        # stock_movements/stock_transfers/stock_counts.inventory_item_id are all
        # RESTRICT (migration 028) — the theft/shrinkage audit trail must
        # survive an inventory item being removed.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This item has stock movement, transfer, or count history and can't be deleted.",
        )
    return {"message": "Item deleted"}


@router.put("/{item_id}/reorder-settings", response_model=schemas.InventoryItemOut)
async def update_reorder_settings(
    item_id: int,
    body: schemas.InventoryReorderSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    """Set the par level and default supplier that drive automated
    reordering (directive 018 — ai/reorder.py). Both nullable: an item with
    either unset is simply never auto-drafted."""
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.default_supplier_id is not None:
        supplier = db.query(models.Supplier).filter(
            models.Supplier.id == body.default_supplier_id,
            models.Supplier.restaurant_id == restaurant.id,
        ).first()
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")

    for key, value in body.dict(exclude_unset=True).items():
        setattr(db_item, key, value)
    db.commit()
    db.refresh(db_item)
    return db_item
