from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant

router = APIRouter(prefix="/menu", tags=["menu"])

@router.get("/")
async def read_menu_items(
    skip: int = 0,
    limit: int = 200,
    category: Optional[str] = None,
    available_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    restaurant = get_or_create_restaurant(db, current_user)
    q = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == restaurant.id)
    if category and category != "All":
        q = q.filter(models.MenuItem.category == category)
    if available_only:
        q = q.filter(models.MenuItem.is_available == True)

    items = q.offset(skip).limit(limit).all()

    # Enrich with food cost % and modifier groups
    results = []
    for item in items:
        # Calculate recipe BOM cost
        ingredients = db.query(models.MenuIngredient).join(models.InventoryItem).filter(
            models.MenuIngredient.menu_item_id == item.id
        ).all()
        bom_cost_cents = sum(int((ing.inventory_item.cost_per_unit or 0) * ing.quantity_per_serving * 100) for ing in ingredients if ing.inventory_item)
        effective_cost = bom_cost_cents if bom_cost_cents > 0 else (item.cost_price or 0)

        food_cost_pct = round((effective_cost / item.price * 100), 1) if item.price > 0 else 0
        margin_pct = max(0, round(100 - food_cost_pct, 1))

        # Attached modifier groups
        mod_groups = db.query(models.ModifierGroup).join(
            models.MenuItemModifierGroup, models.MenuItemModifierGroup.modifier_group_id == models.ModifierGroup.id
        ).filter(models.MenuItemModifierGroup.menu_item_id == item.id).all()

        results.append({
            "id": item.id,
            "restaurant_id": item.restaurant_id,
            "name": item.name,
            "description": item.description or "",
            "price": item.price,
            "cost_price": item.cost_price or 0,
            "effective_cost_cents": effective_cost,
            "food_cost_percent": food_cost_pct,
            "margin_percent": margin_pct,
            "category": item.category,
            "image_url": item.image_url or "",
            "is_available": item.is_available,
            "prep_station": item.prep_station or "main",
            "avg_prep_minutes": item.avg_prep_minutes or 10.0,
            "modifier_groups": [
                {
                    "id": mg.id,
                    "name": mg.name,
                    "min_selection": mg.min_selection,
                    "max_selection": mg.max_selection,
                    "is_required": mg.is_required,
                    "options": [
                        {
                            "id": opt.id,
                            "name": opt.name,
                            "price_delta_cents": opt.price_delta_cents,
                            "is_available": opt.is_available,
                        }
                        for opt in mg.options
                    ],
                }
                for mg in mod_groups
            ],
            "recipe_count": len(ingredients),
        })
    return results

@router.post("/", response_model=schemas.MenuItem)
async def create_menu_item(
    item: schemas.MenuItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
):
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = models.MenuItem(**item.model_dump(), restaurant_id=restaurant.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@router.put("/{item_id}", response_model=schemas.MenuItem)
async def update_menu_item(
    item_id: int,
    item_update: schemas.MenuItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
):
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    for key, value in item_update.model_dump(exclude_unset=True).items():
        setattr(db_item, key, value)
        
    db.commit()
    db.refresh(db_item)
    return db_item

@router.post("/{item_id}/toggle-86")
async def toggle_item_availability(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    """Instant 86 toggle accessible to floor staff and admin."""
    restaurant = get_or_create_restaurant(db, current_user)
    db_item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    db_item.is_available = not db_item.is_available
    db.commit()
    db.refresh(db_item)
    return {"id": db_item.id, "name": db_item.name, "is_available": db_item.is_available}

@router.post("/bulk-86")
async def bulk_86_items(
    item_ids: List[int] = Body(...),
    is_available: bool = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    restaurant = get_or_create_restaurant(db, current_user)
    items = db.query(models.MenuItem).filter(
        models.MenuItem.id.in_(item_ids),
        models.MenuItem.restaurant_id == restaurant.id,
    ).all()
    for item in items:
        item.is_available = is_available
    db.commit()
    return {"updated_count": len(items), "is_available": is_available}

@router.delete("/{item_id}")
async def delete_menu_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
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

# ── Modifier Groups & Options ──

@router.get("/modifiers/groups", response_model=List[schemas.ModifierGroupOut])
async def list_modifier_groups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    restaurant = get_or_create_restaurant(db, current_user)
    groups = db.query(models.ModifierGroup).options(
        joinedload(models.ModifierGroup.options)
    ).filter(models.ModifierGroup.restaurant_id == restaurant.id).all()
    return groups

@router.post("/modifiers/groups", response_model=schemas.ModifierGroupOut)
async def create_modifier_group(
    group: schemas.ModifierGroupCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
):
    restaurant = get_or_create_restaurant(db, current_user)
    db_group = models.ModifierGroup(
        restaurant_id=restaurant.id,
        name=group.name,
        min_selection=group.min_selection,
        max_selection=group.max_selection,
        is_required=group.is_required,
    )
    db.add(db_group)
    db.flush()

    for opt in group.options:
        db_opt = models.ModifierOption(
            group_id=db_group.id,
            name=opt.name,
            price_delta_cents=opt.price_delta_cents,
            is_available=opt.is_available,
        )
        db.add(db_opt)

    db.commit()
    db.refresh(db_group)
    return db_group

@router.post("/{item_id}/modifiers/{group_id}")
async def attach_modifier_group(
    item_id: int,
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
):
    restaurant = get_or_create_restaurant(db, current_user)
    item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    group = db.query(models.ModifierGroup).filter(
        models.ModifierGroup.id == group_id,
        models.ModifierGroup.restaurant_id == restaurant.id,
    ).first()
    if not item or not group:
        raise HTTPException(status_code=404, detail="Item or modifier group not found")

    existing = db.query(models.MenuItemModifierGroup).filter(
        models.MenuItemModifierGroup.menu_item_id == item.id,
        models.MenuItemModifierGroup.modifier_group_id == group.id,
    ).first()
    if not existing:
        db.add(models.MenuItemModifierGroup(menu_item_id=item.id, modifier_group_id=group.id))
        db.commit()

    return {"status": "attached", "menu_item_id": item.id, "group_id": group.id}

@router.delete("/{item_id}/modifiers/{group_id}")
async def detach_modifier_group(
    item_id: int,
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
):
    restaurant = get_or_create_restaurant(db, current_user)
    link = db.query(models.MenuItemModifierGroup).join(models.MenuItem).filter(
        models.MenuItemModifierGroup.menu_item_id == item_id,
        models.MenuItemModifierGroup.modifier_group_id == group_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if link:
        db.delete(link)
        db.commit()
    return {"status": "detached"}

# ── Recipe / BOM Endpoints ──

@router.get("/{item_id}/recipe", response_model=List[schemas.RecipeIngredientOut])
async def get_item_recipe(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    restaurant = get_or_create_restaurant(db, current_user)
    item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    recipes = db.query(models.MenuIngredient).join(models.InventoryItem).filter(
        models.MenuIngredient.menu_item_id == item.id
    ).all()

    return [
        {
            "id": r.id,
            "menu_item_id": r.menu_item_id,
            "inventory_item_id": r.inventory_item_id,
            "item_name": r.inventory_item.item_name if r.inventory_item else "",
            "unit": r.inventory_item.unit if r.inventory_item else "",
            "cost_per_unit": r.inventory_item.cost_per_unit if r.inventory_item else 0.0,
            "quantity_per_serving": r.quantity_per_serving,
            "is_critical": r.is_critical,
        }
        for r in recipes
    ]

@router.post("/{item_id}/recipe", response_model=schemas.RecipeIngredientOut)
async def add_recipe_ingredient(
    item_id: int,
    body: schemas.RecipeIngredientCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
):
    restaurant = get_or_create_restaurant(db, current_user)
    item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    inv = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == body.inventory_item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    rec = db.query(models.MenuIngredient).filter(
        models.MenuIngredient.menu_item_id == item.id,
        models.MenuIngredient.inventory_item_id == inv.id,
    ).first()
    if rec:
        rec.quantity_per_serving = body.quantity_per_serving
        rec.is_critical = body.is_critical
    else:
        rec = models.MenuIngredient(
            menu_item_id=item.id,
            inventory_item_id=inv.id,
            quantity_per_serving=body.quantity_per_serving,
            is_critical=body.is_critical,
        )
        db.add(rec)

    db.commit()
    db.refresh(rec)
    return {
        "id": rec.id,
        "menu_item_id": rec.menu_item_id,
        "inventory_item_id": rec.inventory_item_id,
        "item_name": inv.item_name,
        "unit": inv.unit,
        "cost_per_unit": inv.cost_per_unit,
        "quantity_per_serving": rec.quantity_per_serving,
        "is_critical": rec.is_critical,
    }

@router.delete("/{item_id}/recipe/{ingredient_id}")
async def remove_recipe_ingredient(
    item_id: int,
    ingredient_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
):
    restaurant = get_or_create_restaurant(db, current_user)
    rec = db.query(models.MenuIngredient).join(models.MenuItem).filter(
        models.MenuIngredient.id == ingredient_id,
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant.id,
    ).first()
    if rec:
        db.delete(rec)
        db.commit()
    return {"status": "removed"}

# ── Public endpoint (no auth) for customer ordering ──

@router.get("/public/{restaurant_id}")
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


