"""
Recipes (MenuIngredient) and order-driven stock deduction.

Two gaps closed 2026-08-06, which were really one gap:

  • `MenuIngredient` had been in the schema since the knowledge-graph work and
    was read by ai/graph/build.py and the executive orchestrator's cascade
    analysis — but no endpoint could create a row. On a real restaurant the
    table was always empty, so both readers traversed nothing.

  • Nothing decremented stock when food was sold. `InventoryItem.quantity` moved
    only through the manual /receive and /adjust endpoints, which meant food
    cost %, depletion prediction, reorder suggestions and "4 hours of chicken
    left" all rested on counts a human remembered to type.

The tests below pin the behaviours that make the deduction safe to run on a
restaurant's busiest night — in particular that it never blocks a sale, never
double-deducts on a retry, and never lets one tenant's recipe reach another
tenant's inventory.
"""

import auth
import models
import stock_ledger


def _owner(db_session, suffix):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"chef{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN,
        token_version=0,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add_all([user, restaurant])
    db_session.commit()
    return auth.create_access_token({"sub": user.email, "ver": 0}), restaurant.id


def _ingredient(db_session, restaurant_id, name, qty, unit="kg", cost_per_unit=0.0):
    """cost_per_unit is whole KES — InventoryItem's native unit."""
    inv = models.InventoryItem(
        restaurant_id=restaurant_id, item_name=name, quantity=qty, unit=unit,
        cost_per_unit=cost_per_unit, low_stock_threshold=1,
    )
    db_session.add(inv)
    db_session.commit()
    return inv.id


def _dish(db_session, restaurant_id, name="Chicken Biryani", price=1500, cost_price=0):
    item = models.MenuItem(
        restaurant_id=restaurant_id, name=name, price=price,
        cost_price=cost_price, category="main",
    )
    db_session.add(item)
    db_session.commit()
    return item.id


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


# ── Recipe CRUD ──────────────────────────────────────────────────────────────

def test_recipe_round_trips(client, db_session):
    token, rid = _owner(db_session, "rt")
    chicken = _ingredient(db_session, rid, "Chicken", 100.0, "kg", cost_per_unit=600.0)
    rice = _ingredient(db_session, rid, "Rice", 50.0, "kg", cost_per_unit=150.0)
    dish = _dish(db_session, rid)

    r = client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [
            {"inventory_item_id": chicken, "quantity_per_serving": 0.25},
            {"inventory_item_id": rice, "quantity_per_serving": 0.2, "is_critical": False},
        ]
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["ingredients"]) == 2

    got = client.get(f"/menu/{dish}/recipe", headers=_hdr(token)).json()
    by_id = {line["inventory_item_id"]: line for line in got["ingredients"]}
    assert by_id[chicken]["quantity_per_serving"] == 0.25
    assert by_id[chicken]["is_critical"] is True
    assert by_id[rice]["is_critical"] is False


def test_recipe_replace_is_a_full_replace(client, db_session):
    token, rid = _owner(db_session, "replace")
    a = _ingredient(db_session, rid, "A", 10.0)
    b = _ingredient(db_session, rid, "B", 10.0)
    dish = _dish(db_session, rid)

    client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [{"inventory_item_id": a, "quantity_per_serving": 1.0}]
    })
    client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [{"inventory_item_id": b, "quantity_per_serving": 2.0}]
    })

    got = client.get(f"/menu/{dish}/recipe", headers=_hdr(token)).json()
    assert [l["inventory_item_id"] for l in got["ingredients"]] == [b]


def test_cost_price_is_derived_from_recipe(client, db_session):
    """
    0.25 kg chicken @ KES 600 = 150.00, plus 0.2 kg rice @ KES 150 = 30.00
    → KES 180.00 → 18000 cents. The ×100 is the unit boundary between
    InventoryItem.cost_per_unit (whole KES) and MenuItem.cost_price (cents);
    getting it wrong yields margins wrong by 100×.
    """
    token, rid = _owner(db_session, "cost")
    chicken = _ingredient(db_session, rid, "Chicken", 100.0, cost_per_unit=600.0)
    rice = _ingredient(db_session, rid, "Rice", 50.0, cost_per_unit=150.0)
    dish = _dish(db_session, rid, cost_price=99)

    body = client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [
            {"inventory_item_id": chicken, "quantity_per_serving": 0.25},
            {"inventory_item_id": rice, "quantity_per_serving": 0.2},
        ]
    }).json()

    assert body["derived_cost_price"] == 18000
    assert body["stored_cost_price"] == 18000
    assert body["cost_price_synced"] is True
    db_session.expire_all()
    assert db_session.get(models.MenuItem, dish).cost_price == 18000


def test_sync_cost_price_false_leaves_stored_cost_alone(client, db_session):
    token, rid = _owner(db_session, "nosync")
    inv = _ingredient(db_session, rid, "Beef", 10.0, cost_per_unit=800.0)
    dish = _dish(db_session, rid, cost_price=12345)

    body = client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [{"inventory_item_id": inv, "quantity_per_serving": 0.5}],
        "sync_cost_price": False,
    }).json()

    assert body["derived_cost_price"] == 40000
    assert body["stored_cost_price"] == 12345
    assert body["cost_price_synced"] is False


def test_empty_recipe_does_not_zero_cost_price(client, db_session):
    """A 0 cost would read as 100% margin and poison pricing and profit."""
    token, rid = _owner(db_session, "empty")
    dish = _dish(db_session, rid, cost_price=5000)

    client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={"ingredients": []})
    db_session.expire_all()
    assert db_session.get(models.MenuItem, dish).cost_price == 5000


def test_recipe_rejects_duplicate_and_nonpositive_quantities(client, db_session):
    token, rid = _owner(db_session, "invalid")
    inv = _ingredient(db_session, rid, "Salt", 10.0)
    dish = _dish(db_session, rid)

    dup = client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [
            {"inventory_item_id": inv, "quantity_per_serving": 1.0},
            {"inventory_item_id": inv, "quantity_per_serving": 2.0},
        ]
    })
    assert dup.status_code == 400

    zero = client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [{"inventory_item_id": inv, "quantity_per_serving": 0}]
    })
    assert zero.status_code == 400


def test_recipe_cannot_reference_another_tenants_inventory(client, db_session):
    """
    Cross-tenant write through a legitimately-owned object: without ingredient
    scoping, restaurant A could point its recipe at restaurant B's stock row and
    drain B's inventory with A's own sales.
    """
    token_a, rid_a = _owner(db_session, "ta")
    _, rid_b = _owner(db_session, "tb")
    victim_stock = _ingredient(db_session, rid_b, "Their Chicken", 100.0)
    dish = _dish(db_session, rid_a)

    r = client.put(f"/menu/{dish}/recipe", headers=_hdr(token_a), json={
        "ingredients": [{"inventory_item_id": victim_stock, "quantity_per_serving": 1.0}]
    })
    assert r.status_code == 404
    db_session.expire_all()
    assert db_session.get(models.InventoryItem, victim_stock).quantity == 100.0


def test_recipe_writes_are_admin_only(client, db_session):
    token, rid = _owner(db_session, "rbac")
    dish = _dish(db_session, rid)

    staff = models.User(
        tenant_id=db_session.get(models.Restaurant, rid).tenant_id,
        email="waiter@e.com", hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, token_version=0,
    )
    db_session.add(staff)
    db_session.commit()
    staff_token = auth.create_access_token({"sub": staff.email, "ver": 0})

    r = client.put(f"/menu/{dish}/recipe", headers=_hdr(staff_token),
                   json={"ingredients": []})
    assert r.status_code == 403
    # ...but reading a recipe is fine for staff — the kitchen needs it.
    assert client.get(f"/menu/{dish}/recipe", headers=_hdr(staff_token)).status_code == 200


# ── Deduction on sale ────────────────────────────────────────────────────────

def _order(client, token, menu_item_id, qty=1):
    r = client.post("/orders/", headers=_hdr(token), json={
        "items": [{"menu_item_id": menu_item_id, "quantity": qty}]
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_selling_a_dish_deducts_its_ingredients(client, db_session):
    token, rid = _owner(db_session, "deduct")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)
    dish = _dish(db_session, rid)
    client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [{"inventory_item_id": chicken, "quantity_per_serving": 0.25}]
    })

    _order(client, token, dish, qty=4)          # 4 × 0.25 = 1.0 kg
    db_session.expire_all()

    assert db_session.get(models.InventoryItem, chicken).quantity == 9.0
    movement = db_session.query(models.StockMovement).filter(
        models.StockMovement.movement_type == models.StockMovementType.OUT
    ).one()
    assert movement.quantity == 1.0
    assert movement.reason.startswith(stock_ledger.SALE_REASON_PREFIX)


def test_shared_ingredient_is_aggregated_into_one_movement(client, db_session):
    """A ticket using chicken twice moves chicken once — the ledger should read
    the way an owner would describe it."""
    token, rid = _owner(db_session, "agg")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)
    wings = _dish(db_session, rid, name="Wings")
    biryani = _dish(db_session, rid, name="Biryani")
    for d, q in ((wings, 0.3), (biryani, 0.2)):
        client.put(f"/menu/{d}/recipe", headers=_hdr(token), json={
            "ingredients": [{"inventory_item_id": chicken, "quantity_per_serving": q}]
        })

    client.post("/orders/", headers=_hdr(token), json={"items": [
        {"menu_item_id": wings, "quantity": 1},
        {"menu_item_id": biryani, "quantity": 1},
    ]})
    db_session.expire_all()

    movements = db_session.query(models.StockMovement).filter(
        models.StockMovement.movement_type == models.StockMovementType.OUT
    ).all()
    assert len(movements) == 1
    assert movements[0].quantity == 0.5
    assert db_session.get(models.InventoryItem, chicken).quantity == 9.5


def test_dish_without_a_recipe_sells_normally(client, db_session):
    """Partial recipe books are the normal case — a bottled soda never gets one."""
    token, rid = _owner(db_session, "norecipe")
    dish = _dish(db_session, rid, name="Bottled Soda")
    assert _order(client, token, dish) is not None
    assert db_session.query(models.StockMovement).count() == 0


def test_stock_is_allowed_to_go_negative_and_the_sale_succeeds(client, db_session):
    """
    Refusing to sell food because the software's count disagrees with the shelf
    would be a worse failure than a negative number on a dashboard — and it
    would teach staff to bypass the system on their busiest night.
    """
    token, rid = _owner(db_session, "negative")
    chicken = _ingredient(db_session, rid, "Chicken", 0.5)
    dish = _dish(db_session, rid)
    client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [{"inventory_item_id": chicken, "quantity_per_serving": 0.25}]
    })

    r = client.post("/orders/", headers=_hdr(token), json={
        "items": [{"menu_item_id": dish, "quantity": 10}]
    })
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(models.InventoryItem, chicken).quantity == -2.0


def test_cancelling_an_order_restores_stock_once(client, db_session):
    token, rid = _owner(db_session, "void")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)
    dish = _dish(db_session, rid)
    client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [{"inventory_item_id": chicken, "quantity_per_serving": 0.5}]
    })
    order_id = _order(client, token, dish, qty=2)      # -1.0 kg
    db_session.expire_all()
    assert db_session.get(models.InventoryItem, chicken).quantity == 9.0

    for _ in range(3):      # double-tapped cancel must not restore three times
        client.patch(f"/orders/{order_id}/status", headers=_hdr(token),
                     json={"status": "cancelled"})
    db_session.expire_all()

    assert db_session.get(models.InventoryItem, chicken).quantity == 10.0
    ins = db_session.query(models.StockMovement).filter(
        models.StockMovement.movement_type == models.StockMovementType.IN
    ).all()
    assert len(ins) == 1
    # The original OUT row is kept, not deleted: "taken, then given back" is the
    # auditable history, and it's what distinguishes a void from a sale that
    # never happened.
    assert db_session.query(models.StockMovement).count() == 2


def test_consume_is_idempotent_per_order(client, db_session):
    """A retried request or webhook replay must not deduct twice."""
    token, rid = _owner(db_session, "idem")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)
    dish = _dish(db_session, rid)
    client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [{"inventory_item_id": chicken, "quantity_per_serving": 1.0}]
    })
    order_id = _order(client, token, dish)

    order = db_session.get(models.Order, order_id)
    for _ in range(3):
        stock_ledger.consume_for_order(db_session, order)
    db_session.commit()
    db_session.expire_all()

    assert db_session.get(models.InventoryItem, chicken).quantity == 9.0


def test_public_customer_order_also_deducts(client, db_session):
    token, rid = _owner(db_session, "public")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)
    dish = _dish(db_session, rid)
    client.put(f"/menu/{dish}/recipe", headers=_hdr(token), json={
        "ingredients": [{"inventory_item_id": chicken, "quantity_per_serving": 0.5}]
    })

    r = client.post(f"/orders/public?restaurant_id={rid}", json={
        "items": [{"menu_item_id": dish, "quantity": 2}],
        "order_type": "takeout",
    })
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.get(models.InventoryItem, chicken).quantity == 9.0
