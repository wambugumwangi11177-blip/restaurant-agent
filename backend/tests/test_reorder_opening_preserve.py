"""Opening-count reorder thresholds must not be overwritten by sync_restaurant."""
import models
from services.reorder_points import sync_item_reorder_fields
from tests.factories import seed_owner


def test_sync_preserves_opening_reorder_threshold(db_session):
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven (empty)", email="owner-rop@eleven.leviii")
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Farm", contact_phone="", avg_lead_days=2)
    item = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name="Rice",
        quantity=2,
        unit="kg",
        par_level=20,
        low_stock_threshold=6,
        default_supplier_id=None,
        cost_per_unit=0,
    )
    db_session.add(supplier)
    db_session.add(item)
    db_session.flush()
    item.default_supplier_id = supplier.id
    db_session.add(
        models.StockMovement(
            inventory_item_id=item.id,
            movement_type=models.StockMovementType.ADJUST,
            quantity=2,
            reason="opening",
        )
    )
    db_session.commit()

    sync_item_reorder_fields(db_session, item)
    db_session.commit()
    db_session.refresh(item)

    assert item.low_stock_threshold == 6
    assert item.par_level == 20