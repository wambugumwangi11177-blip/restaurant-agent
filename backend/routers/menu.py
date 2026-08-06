from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
import stock_ledger

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
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
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
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN))
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


# ── Recipes: what a dish is made of ──────────────────────────────────────────
#
# `MenuIngredient` shipped in the schema with the knowledge-graph work and was
# read by ai/graph/build.py and the executive orchestrator's cascade analysis —
# but no endpoint could ever create a row, so on a real restaurant the table was
# always empty and both readers had nothing to traverse. These three endpoints
# are that missing write path. With recipes in place, stock_ledger deducts
# ingredients as dishes sell, and cost_price becomes derived rather than typed.


def _load_owned_menu_item(db: Session, restaurant_id: int, item_id: int) -> models.MenuItem:
    """Fetch a menu item scoped to the caller's restaurant, or 404."""
    item = db.query(models.MenuItem).filter(
        models.MenuItem.id == item_id,
        models.MenuItem.restaurant_id == restaurant_id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return item


def _serialize_recipe(db: Session, item: models.MenuItem) -> dict:
    links = db.query(models.MenuIngredient).filter(
        models.MenuIngredient.menu_item_id == item.id
    ).all()

    inventory = {}
    if links:
        inventory = {
            inv.id: inv
            for inv in db.query(models.InventoryItem).filter(
                models.InventoryItem.id.in_([l.inventory_item_id for l in links])
            ).all()
        }

    lines = []
    for link in links:
        inv = inventory.get(link.inventory_item_id)
        qty = link.quantity_per_serving or 0
        cost_per_unit = (inv.cost_per_unit or 0) if inv else 0
        lines.append({
            "id": link.id,
            "inventory_item_id": link.inventory_item_id,
            "item_name": inv.item_name if inv else "(deleted ingredient)",
            "unit": (inv.unit if inv else "") or "",
            "quantity_per_serving": qty,
            "is_critical": bool(link.is_critical),
            "cost_per_unit": cost_per_unit,
            # cost_per_unit is whole KES; cost_price is cents. See the unit
            # boundary note in stock_ledger.py before changing this.
            "line_cost_cents": int(round(qty * cost_per_unit * 100)),
        })

    derived = stock_ledger.recipe_cost_cents(db, item.id)
    stored = item.cost_price or 0
    return {
        "menu_item_id": item.id,
        "menu_item_name": item.name,
        "ingredients": lines,
        "derived_cost_price": derived,
        "stored_cost_price": stored,
        "cost_price_synced": derived is not None and derived == stored,
    }


@router.get("/{item_id}/recipe", response_model=schemas.RecipeOut)
async def get_recipe(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    item = _load_owned_menu_item(db, restaurant.id, item_id)
    return _serialize_recipe(db, item)


@router.put("/{item_id}/recipe", response_model=schemas.RecipeOut)
async def replace_recipe(
    item_id: int,
    body: schemas.RecipeReplace,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    """
    Replace a dish's whole recipe. Admin-only: a recipe drives both stock
    deduction and (via sync_cost_price) the cost figure every margin, food-cost
    and pricing recommendation is computed from, so it's a money-moving edit in
    the same category as changing a price.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    item = _load_owned_menu_item(db, restaurant.id, item_id)

    seen: set[int] = set()
    for line in body.ingredients:
        if line.quantity_per_serving <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"quantity_per_serving must be greater than 0 (ingredient {line.inventory_item_id})",
            )
        if line.inventory_item_id in seen:
            # The DB's uq_menu_ingredient would reject this anyway, as an opaque
            # IntegrityError. Catching it here names the offending ingredient.
            raise HTTPException(
                status_code=400,
                detail=f"Ingredient {line.inventory_item_id} listed more than once",
            )
        seen.add(line.inventory_item_id)

    # Tenant scoping on the INGREDIENTS, not just the dish. Without this an
    # admin could point their recipe at another restaurant's inventory row and
    # then drain that tenant's stock with their own sales — a cross-tenant write
    # through a legitimately-owned object. Scoping the query by restaurant_id
    # fails closed the same way menu/order lookups do.
    if seen:
        owned = {
            row.id for row in db.query(models.InventoryItem.id).filter(
                models.InventoryItem.id.in_(list(seen)),
                models.InventoryItem.restaurant_id == restaurant.id,
            ).all()
        }
        missing = seen - owned
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Inventory item(s) not found: {sorted(missing)}",
            )

    db.query(models.MenuIngredient).filter(
        models.MenuIngredient.menu_item_id == item.id
    ).delete(synchronize_session=False)

    for line in body.ingredients:
        db.add(models.MenuIngredient(
            menu_item_id=item.id,
            inventory_item_id=line.inventory_item_id,
            quantity_per_serving=line.quantity_per_serving,
            is_critical=line.is_critical,
        ))
    db.flush()

    if body.sync_cost_price:
        derived = stock_ledger.recipe_cost_cents(db, item.id)
        # None means the recipe is now empty. Leave the previous cost_price
        # alone rather than zeroing it — a 0 cost reads as 100% margin and would
        # poison every pricing and profit number for this dish.
        if derived is not None:
            item.cost_price = derived

    db.commit()
    db.refresh(item)
    return _serialize_recipe(db, item)


@router.delete("/{item_id}/recipe")
async def delete_recipe(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    """
    Clear a dish's recipe. cost_price is left as-is deliberately: removing the
    recipe means "I no longer track what this is made of", not "this dish is
    free to produce".
    """
    restaurant = get_or_create_restaurant(db, current_user)
    item = _load_owned_menu_item(db, restaurant.id, item_id)
    removed = db.query(models.MenuIngredient).filter(
        models.MenuIngredient.menu_item_id == item.id
    ).delete(synchronize_session=False)
    db.commit()
    return {"message": f"Recipe cleared for {item.name}", "ingredients_removed": removed}


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

