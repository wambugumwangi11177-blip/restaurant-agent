from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant

router = APIRouter(prefix="/menu", tags=["menu"])

# Directive 015's `menu` matrix row: RW = Owner, Manager only.
_CAN_WRITE = (models.StaffRole.MANAGER,)

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

@router.post("/", response_model=schemas.MenuItem, status_code=201)
async def create_menu_item(
    item: schemas.MenuItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE))
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
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE))
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

    was_available = db_item.is_available
    old_price = db_item.price
    for key, value in item_update.dict(exclude_unset=True).items():
        setattr(db_item, key, value)

    db.commit()
    db.refresh(db_item)

    # POS-facing staff need to stop selling this immediately — fires only on
    # the True->False transition, not every update to the item (price edits,
    # etc. don't warrant an alert). See EventType.MENU_ITEM_UNAVAILABLE.
    if was_available and not db_item.is_available:
        from events.bus import emit_async, EventType
        emit_async(EventType.MENU_ITEM_UNAVAILABLE, {
            "restaurant_id": restaurant.id,
            "item_name": db_item.name,
        })

    # 2026-07-18 event-map pass: the *manual* counterpart to
    # recommendation.approved — POS staff quoting from memory need to know a
    # price they set by hand just changed too. Fires only on a real price
    # delta; the actor (Owner/Manager who edited it) is excluded.
    if db_item.price != old_price:
        from events.bus import emit_async, EventType
        emit_async(EventType.PRICE_CHANGED, {
            "restaurant_id": restaurant.id,
            "menu_item_id": db_item.id,
            "item_name": db_item.name,
            "old_price": old_price,
            "new_price": db_item.price,
            "actor_user_id": current_user.id,
        })

    return db_item

@router.delete("/{item_id}")
async def delete_menu_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE))
):
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    db.delete(db_item)
    try:
        db.commit()
    except IntegrityError:
        # order_items.menu_item_id is RESTRICT (migration 028) — order history
        # must survive a menu item being removed.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This item has order history and can't be deleted — set is_available=false to hide it instead.",
        )
    return {"message": "Item deleted successfully"}


# ── Recipes: what a dish is made of (directive 017) ──
# The prerequisite for auto-deducting stock on order creation — without this,
# MenuIngredient (which already existed, used by the knowledge graph and the
# stock-critical cascade) had no way for an owner to actually populate it.

def _ingredient_out(row: models.MenuIngredient, item: models.InventoryItem | None) -> dict:
    return {
        "id": row.id,
        "menu_item_id": row.menu_item_id,
        "inventory_item_id": row.inventory_item_id,
        "quantity_per_serving": row.quantity_per_serving,
        "is_critical": row.is_critical,
        "item_name": item.item_name if item else None,
        "unit": item.unit if item else None,
    }


@router.get("/{item_id}/ingredients", response_model=List[schemas.MenuIngredientOut])
async def list_ingredients(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    menu_item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not menu_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    rows = db.query(models.MenuIngredient).filter(
        models.MenuIngredient.menu_item_id == item_id
    ).all()
    items_by_id = {
        i.id: i for i in db.query(models.InventoryItem).filter(
            models.InventoryItem.id.in_([r.inventory_item_id for r in rows]),
            models.InventoryItem.restaurant_id == restaurant.id,
        ).all()
    } if rows else {}
    return [_ingredient_out(r, items_by_id.get(r.inventory_item_id)) for r in rows]


@router.post("/{item_id}/ingredients", response_model=schemas.MenuIngredientOut, status_code=201)
async def add_ingredient(
    item_id: int,
    body: schemas.MenuIngredientCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    menu_item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not menu_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    inv_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == body.inventory_item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not inv_item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    existing = db.query(models.MenuIngredient).filter(
        models.MenuIngredient.menu_item_id == item_id,
        models.MenuIngredient.inventory_item_id == body.inventory_item_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="This ingredient is already on the recipe — edit it instead.")

    row = models.MenuIngredient(
        menu_item_id=item_id,
        inventory_item_id=body.inventory_item_id,
        quantity_per_serving=body.quantity_per_serving,
        is_critical=body.is_critical,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _ingredient_out(row, inv_item)


@router.put("/{item_id}/ingredients/{ingredient_id}", response_model=schemas.MenuIngredientOut)
async def update_ingredient(
    item_id: int,
    ingredient_id: int,
    body: schemas.MenuIngredientUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    row = db.query(models.MenuIngredient).join(
        models.MenuItem, models.MenuItem.id == models.MenuIngredient.menu_item_id
    ).filter(
        models.MenuIngredient.id == ingredient_id,
        models.MenuIngredient.menu_item_id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe ingredient not found")

    updates = body.dict(exclude_unset=True)
    for key, value in updates.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)

    inv_item = db.query(models.InventoryItem).filter(models.InventoryItem.id == row.inventory_item_id).first()
    return _ingredient_out(row, inv_item)


@router.delete("/{item_id}/ingredients/{ingredient_id}")
async def delete_ingredient(
    item_id: int,
    ingredient_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    row = db.query(models.MenuIngredient).join(
        models.MenuItem, models.MenuItem.id == models.MenuIngredient.menu_item_id
    ).filter(
        models.MenuIngredient.id == ingredient_id,
        models.MenuIngredient.menu_item_id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe ingredient not found")

    db.delete(row)
    db.commit()
    return {"message": "Ingredient removed from recipe"}


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

