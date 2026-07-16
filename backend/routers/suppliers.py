"""
backend/routers/suppliers.py
───────────────────────────────
Supplier CRUD (directive 018). The Supplier model already existed —
read by ai/supply_chain/intelligence.py for performance analysis, and
referenced by PurchaseOrder — but nothing let an owner actually create or
edit one. Verified by grep before assuming: zero references to
`models.Supplier` in any router prior to this file.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from phone_utils import normalize_phone

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

# Suppliers are procurement/financial-adjacent — Owner/Manager, matching the
# menu and inventory-write gates elsewhere (directive 015's spirit, not a
# literal matrix row since `suppliers` isn't a dashboard route in that table).
_CAN_WRITE = (models.StaffRole.MANAGER,)
_CAN_READ = (models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER, models.StaffRole.CONTROLLER)


@router.get("/", response_model=List[schemas.SupplierOut])
async def list_suppliers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_READ)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    return db.query(models.Supplier).filter(
        models.Supplier.restaurant_id == restaurant.id
    ).order_by(models.Supplier.name).all()


@router.post("/", response_model=schemas.SupplierOut)
async def create_supplier(
    body: schemas.SupplierCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    supplier = models.Supplier(
        restaurant_id=restaurant.id,
        name=body.name,
        # Normalized on write so it matches what a Twilio send expects —
        # same reasoning as Restaurant.owner_phone / StaffMember.phone.
        contact_phone=normalize_phone(body.contact_phone) if body.contact_phone else "",
        contact_email=body.contact_email,
        avg_lead_days=body.avg_lead_days,
        notes=body.notes,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.put("/{supplier_id}", response_model=schemas.SupplierOut)
async def update_supplier(
    supplier_id: int,
    body: schemas.SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    supplier = db.query(models.Supplier).filter(
        models.Supplier.id == supplier_id,
        models.Supplier.restaurant_id == restaurant.id,
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    updates = body.dict(exclude_unset=True)
    if "contact_phone" in updates and updates["contact_phone"]:
        updates["contact_phone"] = normalize_phone(updates["contact_phone"])
    for key, value in updates.items():
        setattr(supplier, key, value)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    supplier = db.query(models.Supplier).filter(
        models.Supplier.id == supplier_id,
        models.Supplier.restaurant_id == restaurant.id,
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    in_use = db.query(models.InventoryItem).filter(
        models.InventoryItem.default_supplier_id == supplier_id
    ).count()
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"{in_use} inventory item(s) still default to this supplier — reassign them first.",
        )

    db.delete(supplier)
    try:
        db.commit()
    except IntegrityError:
        # Backstop for purchase_orders.supplier_id (RESTRICT, migration 028) —
        # the default_supplier_id precheck above doesn't cover PO history.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This supplier has purchase order history and can't be deleted — set is_active=false to deactivate it instead.",
        )
    return {"message": "Supplier deleted"}
