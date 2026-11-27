"""Dish cost from recipes and reorder point sync."""
import models
from services.dish_cost import dish_cost_cents
from services.reorder_points import sync_item_reorder_fields
from tests.test_storekeeper_foundation import _tenant


def test_dish_cost_sums_ingredients(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "dc@eleven.leviii")
    rice = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name="Rice",
        quantity=10,
        unit="kg",
        cost_per_unit=120,
    )
    db_session.add(rice)
    db_session.flush()
    dish = models.MenuItem(restaurant_id=restaurant.id, name="Pilau", category="Kitchen", price=45000)
    db_session.add(dish)
    db_session.flush()
    db_session.add(
        models.MenuIngredient(
            menu_item_id=dish.id,
            inventory_item_id=rice.id,
            quantity_per_serving=0.2,
            recipe_unit="kg",
            yield_fraction=1.0,
        )
    )
    db_session.commit()
    cents = dish_cost_cents(db_session, restaurant.id, dish.id)
    assert cents == 2400


def test_reorder_point_from_usage(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "rp@eleven.leviii")
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Farm", contact_phone="0700", avg_lead_days=2)
    db_session.add(supplier)
    db_session.flush()
    item = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name="Oil",
        quantity=5,
        unit="L",
        default_supplier_id=supplier.id,
        cost_per_unit=100,
    )
    db_session.add(item)
    db_session.flush()
    for _ in range(7):
        db_session.add(
            models.StockMovement(
                inventory_item_id=item.id,
                movement_type=models.StockMovementType.OUT,
                quantity=1,
                reason="kitchen",
            )
        )
    db_session.commit()
    snap = sync_item_reorder_fields(db_session, item, lead_days=2, order_qty=4)
    assert item.low_stock_threshold is not None
    assert item.par_level is not None
    assert snap["reorder_point"] > 0