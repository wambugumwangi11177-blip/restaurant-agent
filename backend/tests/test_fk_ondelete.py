"""
backend/tests/test_fk_ondelete.py
────────────────────────────────────
Explicit ON DELETE policy added in migration 028 (see models.py's `ondelete=`
comments for the per-relationship reasoning): CASCADE for pure-owned child rows
with no independent value, RESTRICT for audit/financial trails that must
survive a parent being removed, SET NULL for optional back-references.

SQLite does not enforce FK constraints by default (its own PRAGMA is off
unless a connection turns it on), so this file enables it locally for its own
engine only — conftest's shared `db_session`/`client` fixtures are untouched,
and the listener is removed in teardown so it can't leak into other test
files.
"""

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def db_session(db_env):
    import database
    importlib_engine = database.engine

    def _fk_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(importlib_engine, "connect", _fk_pragma)
    database.init_db()
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()
        event.remove(importlib_engine, "connect", _fk_pragma)


def _restaurant(db):
    import models
    t = models.Tenant(name="T")
    db.add(t)
    db.commit()
    r = models.Restaurant(tenant_id=t.id, name="R", address="x")
    db.add(r)
    db.commit()
    return r


def test_deleting_order_cascades_order_items(db_session):
    import models
    r = _restaurant(db_session)
    item = models.MenuItem(restaurant_id=r.id, name="Chips", price=100, category="m")
    db_session.add(item)
    db_session.commit()
    order = models.Order(restaurant_id=r.id, total=100, payment_method=models.PaymentMethod.CASH)
    db_session.add(order)
    db_session.commit()
    oi = models.OrderItem(order_id=order.id, menu_item_id=item.id, quantity=1, unit_price=100)
    db_session.add(oi)
    db_session.commit()
    oi_id = oi.id

    db_session.delete(order)
    db_session.commit()

    assert db_session.query(models.OrderItem).filter_by(id=oi_id).first() is None


def test_deleting_menu_item_with_order_history_is_restricted(db_session):
    import models
    r = _restaurant(db_session)
    item = models.MenuItem(restaurant_id=r.id, name="Chips", price=100, category="m")
    db_session.add(item)
    db_session.commit()
    order = models.Order(restaurant_id=r.id, total=100, payment_method=models.PaymentMethod.CASH)
    db_session.add(order)
    db_session.commit()
    db_session.add(models.OrderItem(order_id=order.id, menu_item_id=item.id, quantity=1, unit_price=100))
    db_session.commit()

    db_session.delete(item)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_menu_item_cascades_recipe_and_pricing_rows(db_session):
    import models
    r = _restaurant(db_session)
    item = models.MenuItem(restaurant_id=r.id, name="Chips", price=100, category="m")
    inv = models.InventoryItem(restaurant_id=r.id, item_name="Potatoes", unit="kg")
    db_session.add_all([item, inv])
    db_session.commit()
    ingredient = models.MenuIngredient(menu_item_id=item.id, inventory_item_id=inv.id, quantity_per_serving=0.2)
    rec = models.PricingRecommendation(
        restaurant_id=r.id, menu_item_id=item.id, recommendation_type="raise",
        current_price=100, suggested_price=120,
    )
    db_session.add_all([ingredient, rec])
    db_session.commit()
    ingredient_id, rec_id = ingredient.id, rec.id

    db_session.delete(item)
    db_session.commit()

    assert db_session.query(models.MenuIngredient).filter_by(id=ingredient_id).first() is None
    assert db_session.query(models.PricingRecommendation).filter_by(id=rec_id).first() is None


def test_deleting_inventory_item_with_stock_movement_is_restricted(db_session):
    import models
    r = _restaurant(db_session)
    inv = models.InventoryItem(restaurant_id=r.id, item_name="Potatoes", unit="kg")
    db_session.add(inv)
    db_session.commit()
    db_session.add(models.StockMovement(inventory_item_id=inv.id, movement_type=models.StockMovementType.IN, quantity=10))
    db_session.commit()

    db_session.delete(inv)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_inventory_item_nulls_out_purchase_order_reference(db_session):
    import models
    r = _restaurant(db_session)
    supplier = models.Supplier(restaurant_id=r.id, name="Acme")
    inv = models.InventoryItem(restaurant_id=r.id, item_name="Potatoes", unit="kg")
    db_session.add_all([supplier, inv])
    db_session.commit()
    po = models.PurchaseOrder(
        restaurant_id=r.id, supplier_id=supplier.id, inventory_item_id=inv.id,
        quantity_ordered=50,
    )
    db_session.add(po)
    db_session.commit()
    po_id = po.id

    db_session.delete(inv)
    db_session.commit()

    reloaded = db_session.query(models.PurchaseOrder).filter_by(id=po_id).first()
    assert reloaded is not None
    assert reloaded.inventory_item_id is None


def test_deleting_supplier_with_purchase_order_is_restricted(db_session):
    import models
    r = _restaurant(db_session)
    supplier = models.Supplier(restaurant_id=r.id, name="Acme")
    db_session.add(supplier)
    db_session.commit()
    db_session.add(models.PurchaseOrder(restaurant_id=r.id, supplier_id=supplier.id, quantity_ordered=10))
    db_session.commit()

    db_session.delete(supplier)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_workflow_run_cascades_steps(db_session):
    import models
    r = _restaurant(db_session)
    run = models.WorkflowRun(restaurant_id=r.id, template="low_stock_reorder")
    db_session.add(run)
    db_session.commit()
    step = models.WorkflowStep(run_id=run.id, seq=0, name="check", step_type="agent_call")
    db_session.add(step)
    db_session.commit()
    step_id = step.id

    db_session.delete(run)
    db_session.commit()

    assert db_session.query(models.WorkflowStep).filter_by(id=step_id).first() is None
