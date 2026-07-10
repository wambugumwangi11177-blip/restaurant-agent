from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant

router = APIRouter(prefix="/menu", tags=["menu"])

@router.get("/", response_model=List[schemas.MenuItem])
async def read_menu_items(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    restaurant = get_or_create_restaurant(db, current_user)
    items = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == restaurant.id).offset(skip).limit(limit).all()
    return items

@router.post("/", response_model=schemas.MenuItem)
async def create_menu_item(
    item: schemas.MenuItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    restaurant = get_or_create_restaurant(db, current_user)
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
    # Tenant scoping via the shared restaurant lookup, consistent with every
    # other mutation endpoint (orders.py, inventory.py). Scoping the QUERY by
    # restaurant_id fails closed: a cross-tenant item_id simply isn't found (404),
    # so there is no ad-hoc post-fetch ownership check that a future edit could
    # drop and silently open an IDOR.
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

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
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    db.delete(db_item)
    db.commit()
    return {"message": "Item deleted successfully"}


# ── Public endpoint (no auth) for customer ordering ──

@router.get("/public/{restaurant_id}", response_model=List[schemas.MenuItem])
async def get_public_menu(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    """Public menu for customer ordering — no login required."""
    items = db.query(models.MenuItem).filter(
        models.MenuItem.restaurant_id == restaurant_id,
        models.MenuItem.is_available == True,
    ).all()
    return items

