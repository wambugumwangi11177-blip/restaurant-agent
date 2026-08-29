"""
Directive 017 — recipe-driven auto-deduction, kitchen requisition (pull),
and physical stock counts.

Covers the pieces most likely to be subtly wrong: deduction actually firing
at order creation (not serve), the cancel-before-served-vs-after-served
reversal rule, the REQUESTED->fulfil->confirm state machine matching the
existing push-flow's confirm behavior exactly, and a physical count both
reconciling the system's number AND flagging only when the gap is real.
"""

import pytest

import auth
import models
from time_utils import utcnow


def _user_with_staff_role(db_session, suffix, staff_role):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF,
        staff_role=staff_role,
        token_version=0,
    )
    db_session.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token, user, restaurant


@pytest.fixture
def recipe_setup(db_session):
    """One restaurant, one Owner, one menu item with a defined recipe."""
    tenant = models.Tenant(name="RT")
    db_session.add(tenant)
    db_session.commit()
    owner = models.User(
        tenant_id=tenant.id, email="owner@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER, token_version=0,
    )
    db_session.add(owner)
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R", address="x")
    db_session.add(restaurant)
    db_session.commit()

    menu_item = models.MenuItem(restaurant_id=restaurant.id, name="Chicken Burger",
                                 price=500, cost_price=200, category="mains")
    inv_item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Chicken",
                                     quantity=100.0, unit="kg", low_stock_threshold=5)
    db_session.add_all([menu_item, inv_item])
    db_session.commit()
    db_session.add(models.MenuIngredient(
        menu_item_id=menu_item.id, inventory_item_id=inv_item.id, quantity_per_serving=0.3,
    ))
    db_session.commit()

    owner_token = auth.create_access_token({"sub": owner.email, "ver": 0})
    return restaurant, owner, owner_token, menu_item, inv_item


# ── Recipe editor CRUD ─────────────────────────────────────────────────────

def test_manager_can_add_and_remove_recipe_ingredient(client, db_session):
    token, user, restaurant = _user_with_staff_role(db_session, "mgr1", models.StaffRole.MANAGER)
    menu_item = models.MenuItem(restaurant_id=restaurant.id, name="Chips", price=200, category="sides")
    inv_item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Potatoes", quantity=50.0, unit="kg", low_stock_threshold=5)
    db_session.add_all([menu_item, inv_item])
    db_session.commit()

    r = client.post(
        f"/menu/{menu_item.id}/ingredients",
        json={"inventory_item_id": inv_item.id, "quantity_per_serving": 0.25},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    ingredient_id = r.json()["id"]

    r2 = client.get(f"/menu/{menu_item.id}/ingredients", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    assert r2.json()[0]["item_name"] == "Potatoes"

    r3 = client.delete(f"/menu/{menu_item.id}/ingredients/{ingredient_id}", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 200

    r4 = client.get(f"/menu/{menu_item.id}/ingredients", headers={"Authorization": f"Bearer {token}"})
    assert r4.json() == []


def test_waiter_cannot_add_recipe_ingredient(client, db_session):
    token, user, restaurant = _user_with_staff_role(db_session, "waiter1", models.StaffRole.WAITER)
    menu_item = models.MenuItem(restaurant_id=restaurant.id, name="Chips", price=200, category="sides")
    inv_item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Potatoes", quantity=50.0, unit="kg", low_stock_threshold=5)
    db_session.add_all([menu_item, inv_item])
    db_session.commit()

    r = client.post(
        f"/menu/{menu_item.id}/ingredients",
        json={"inventory_item_id": inv_item.id, "quantity_per_serving": 0.25},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


# ── Auto-deduction on order creation ───────────────────────────────────────

def test_order_creation_deducts_recipe_ingredients(client, db_session, recipe_setup):
    restaurant, owner, owner_token, menu_item, inv_item = recipe_setup
    before_qty = inv_item.quantity

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 2}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201, r.text

    db_session.refresh(inv_item)
    # 2 servings x 0.3kg/serving = 0.6kg deducted
    assert inv_item.quantity == pytest.approx(before_qty - 0.6)

    movements = db_session.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id == inv_item.id,
        models.StockMovement.movement_type == models.StockMovementType.OUT,
    ).all()
    assert len(movements) == 1
    assert movements[0].quantity == pytest.approx(0.6)
    assert movements[0].performed_by_user_id == owner.id


def test_order_with_no_recipe_does_not_crash_or_deduct(client, db_session, recipe_setup):
    restaurant, owner, owner_token, _menu_item, inv_item = recipe_setup
    no_recipe_item = models.MenuItem(restaurant_id=restaurant.id, name="Soda", price=100, category="drinks")
    db_session.add(no_recipe_item)
    db_session.commit()
    before_qty = inv_item.quantity

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": no_recipe_item.id, "quantity": 3}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201, r.text

    db_session.refresh(inv_item)
    assert inv_item.quantity == before_qty   # untouched — no recipe references it


def test_going_negative_is_allowed_not_blocked(client, db_session, recipe_setup):
    """Directive 007's existing policy: allow negative stock, don't block the sale."""
    restaurant, owner, owner_token, menu_item, inv_item = recipe_setup
    inv_item.quantity = 0.1   # nowhere near enough for a full order
    db_session.commit()

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 5}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r.status_code == 201   # order still succeeds

    db_session.refresh(inv_item)
    assert inv_item.quantity < 0   # allowed to go negative


# ── Reversal rule ───────────────────────────────────────────────────────────

def test_cancel_before_served_reverses_deduction(client, db_session, recipe_setup):
    restaurant, owner, owner_token, menu_item, inv_item = recipe_setup
    before_qty = inv_item.quantity

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 1}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    order_id = r.json()["id"]
    db_session.refresh(inv_item)
    assert inv_item.quantity == pytest.approx(before_qty - 0.3)   # deducted

    r2 = client.post(
        f"/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r2.status_code == 200

    db_session.refresh(inv_item)
    assert inv_item.quantity == pytest.approx(before_qty)   # credited back in full


def test_cancel_after_served_does_not_reverse(client, db_session, recipe_setup):
    restaurant, owner, owner_token, menu_item, inv_item = recipe_setup
    before_qty = inv_item.quantity

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 1}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    order_id = r.json()["id"]

    client.post(f"/orders/{order_id}/status", json={"status": "served"},
                 headers={"Authorization": f"Bearer {owner_token}"})
    db_session.refresh(inv_item)
    after_served = inv_item.quantity
    assert after_served == pytest.approx(before_qty - 0.3)

    r3 = client.post(f"/orders/{order_id}/status", json={"status": "cancelled"},
                       headers={"Authorization": f"Bearer {owner_token}"})
    assert r3.status_code == 200

    db_session.refresh(inv_item)
    # Still deducted — the food was already made, cancelling the bill
    # afterward doesn't put the chicken back.
    assert inv_item.quantity == pytest.approx(after_served)


# ── Kitchen requisition (pull) flow ────────────────────────────────────────

@pytest.fixture
def requisition_setup(db_session):
    tenant = models.Tenant(name="QT")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R", address="x")
    db_session.add(restaurant)
    db_session.commit()

    kitchen = models.User(tenant_id=tenant.id, email="kitchen@e.com",
                           hashed_password=auth.get_password_hash("x"),
                           role=models.Role.STAFF, staff_role=models.StaffRole.KITCHEN, token_version=0)
    stockkeeper = models.User(tenant_id=tenant.id, email="stock@e.com",
                               hashed_password=auth.get_password_hash("x"),
                               role=models.Role.STAFF, staff_role=models.StaffRole.STOCKKEEPER, token_version=0)
    db_session.add_all([kitchen, stockkeeper])
    db_session.commit()

    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Rice", quantity=80.0, unit="kg", low_stock_threshold=5)
    db_session.add(item)
    db_session.commit()

    kitchen_token = auth.create_access_token({"sub": kitchen.email, "ver": 0})
    stock_token = auth.create_access_token({"sub": stockkeeper.email, "ver": 0})
    return restaurant, item, kitchen_token, stock_token


def test_kitchen_requisition_full_pull_flow(client, db_session, requisition_setup):
    restaurant, item, kitchen_token, stock_token = requisition_setup

    r1 = client.post("/stock/transfers/request",
                      json={"inventory_item_id": item.id},
                      headers={"Authorization": f"Bearer {kitchen_token}"})
    assert r1.status_code == 201, r1.text
    assert r1.json()["status"] == "requested"
    assert r1.json()["quantity"] is None
    transfer_id = r1.json()["id"]

    r2 = client.post(f"/stock/transfers/{transfer_id}/fulfil",
                      json={"quantity": 10.0},
                      headers={"Authorization": f"Bearer {stock_token}"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "pending"
    assert r2.json()["quantity"] == 10.0

    before_movements = db_session.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id == item.id
    ).count()

    r3 = client.post(f"/stock/transfers/{transfer_id}/confirm",
                      json={"confirmed_quantity": 10.0},
                      headers={"Authorization": f"Bearer {kitchen_token}"})
    assert r3.status_code == 200
    assert r3.json()["status"] == "confirmed"

    after_movements = db_session.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id == item.id
    ).count()
    assert after_movements == before_movements + 2


def test_cannot_fulfil_a_transfer_twice(client, db_session, requisition_setup):
    restaurant, item, kitchen_token, stock_token = requisition_setup
    r1 = client.post("/stock/transfers/request", json={"inventory_item_id": item.id},
                      headers={"Authorization": f"Bearer {kitchen_token}"})
    transfer_id = r1.json()["id"]

    client.post(f"/stock/transfers/{transfer_id}/fulfil", json={"quantity": 5.0},
                headers={"Authorization": f"Bearer {stock_token}"})
    r2 = client.post(f"/stock/transfers/{transfer_id}/fulfil", json={"quantity": 5.0},
                      headers={"Authorization": f"Bearer {stock_token}"})
    assert r2.status_code == 400


# ── Physical stock counts ──────────────────────────────────────────────────

def test_stock_count_reconciles_quantity(client, db_session):
    token, user, restaurant = _user_with_staff_role(db_session, "counter1", models.StaffRole.STOCKKEEPER)
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Onions", quantity=20.0, unit="kg", low_stock_threshold=2)
    db_session.add(item)
    db_session.commit()

    r = client.post("/stock/counts", json={"inventory_item_id": item.id, "counted_quantity": 15.0},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["expected_quantity"] == 20.0
    assert r.json()["counted_quantity"] == 15.0

    db_session.refresh(item)
    assert item.quantity == 15.0   # reconciled to the physical count


def test_stock_count_within_tolerance_no_event(client, db_session):
    from events.bus import subscribe, EventType
    received = []
    subscribe(EventType.STOCK_COUNT_DISCREPANCY, lambda p: received.append(p))

    token, user, restaurant = _user_with_staff_role(db_session, "counter2", models.StaffRole.STOCKKEEPER)
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Salt", quantity=100.0, unit="kg", low_stock_threshold=5)
    db_session.add(item)
    db_session.commit()

    r = client.post("/stock/counts", json={"inventory_item_id": item.id, "counted_quantity": 99.5},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    assert received == []   # 0.5% gap, well under the 3% threshold


def test_stock_count_beyond_tolerance_flags_event(client, db_session):
    from events.bus import subscribe, EventType
    received = []
    subscribe(EventType.STOCK_COUNT_DISCREPANCY, lambda p: received.append(p))

    token, user, restaurant = _user_with_staff_role(db_session, "counter3", models.StaffRole.STOCKKEEPER)
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Beef", quantity=50.0, unit="kg", low_stock_threshold=5)
    db_session.add(item)
    db_session.commit()

    r = client.post("/stock/counts", json={"inventory_item_id": item.id, "counted_quantity": 35.0},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201

    # emit_async runs in a background thread — give it a moment (same
    # pattern as tests/test_event_orchestration.py).
    import time as time_mod
    for _ in range(20):
        if received:
            break
        time_mod.sleep(0.05)

    assert len(received) == 1
    assert received[0]["item_name"] == "Beef"
