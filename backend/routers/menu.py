from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/menu", tags=["menu"])

@router.get("/", response_model=List[schemas.MenuItem])
async def read_menu_items(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # Currently checks all, eventually filter by tenant/restaurant
    items = db.query(models.MenuItem).offset(skip).limit(limit).all()
    return items

@router.post("/", response_model=schemas.MenuItem)
async def create_menu_item(
    item: schemas.MenuItemCreate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(auth.get_current_user)
):
    # Ensure user has a restaurant (or tenant context)
    # For MVP, we assign to the first restaurant of the tenant or create one if missing?
    # Better: User -> Tenant -> Restaurant.
    # We need to find the restaurant associated with the user's tenant.
    
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.tenant_id == current_user.tenant_id).first()
    if not restaurant:
        # Auto-create a restaurant for the tenant if none exists (for MVP speed)
        restaurant = models.Restaurant(name=f"{current_user.tenant.name}'s Restaurant", tenant_id=current_user.tenant_id)
        db.add(restaurant)
        db.commit()
        db.refresh(restaurant)
        
    db_item = models.MenuItem(**item.dict(), restaurant_id=restaurant.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.put("/{item_id}", response_model=schemas.MenuItem)
async def update_menu_item(
    item_id: int, 
    item_update: schemas.MenuItemUpdate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Verify ownership (TODO: Strict permission checks)
    db_item = db.query(models.MenuItem).filter(models.MenuItem.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Menu item not found")
        
    # Simple check: does item belong to user's tenant's restaurant?
    # db_item.restaurant.tenant_id == current_user.tenant_id
    if db_item.restaurant.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this item")
    
    for key, value in item_update.dict(exclude_unset=True).items():
        setattr(db_item, key, value)
        
    db.commit()
    db.refresh(db_item)
    return db_item

@router.delete("/{item_id}")
async def delete_menu_item(
    item_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    db_item = db.query(models.MenuItem).filter(models.MenuItem.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Menu item not found")
        
    if db_item.restaurant.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this item")
        
    db.delete(db_item)
    db.commit()
    return {"message": "Item deleted successfully"}
