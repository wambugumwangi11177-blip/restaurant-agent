"""
Sprint 1 of the fraud-detection build: persisted order actor trail.
Covers the two write sites in routers/orders.py — cancel/refund via
PATCH /orders/{id}/status and manual payment overrides via
PATCH /orders/{id}/payment — plus the CANCEL vs REFUND action split.
"""

import pytest

import auth
import models


@pytest.fixture
def recipe_setup(db_session):
    """One restaurant, one Owner, one menu item with a defined recipe.
    Mirrors tests/test_recipe_auto_deduction_and_requisition.py's fixture of
    the same name (kept local, not shared via conftest, matching that file's
    own pattern)."""
    tenant = models.Tenant(name="RT-audit")
    db_session.add(tenant)
    db_session.commit()
    owner = models.User(
        tenant_id=tenant.id, email="owner-audit@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER, token_version=0,
    )
    db_session.add(owner)
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R-audit", address="x")
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


def test_cancel_before_served_writes_cancel_audit_row(client, db_session, recipe_setup):
    restaurant, owner, owner_token, menu_item, inv_item = recipe_setup

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 1}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    order_id = r.json()["id"]

    r2 = client.patch(
        f"/orders/{order_id}/status",
        json={"status": "cancelled", "reason": "customer changed mind"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r2.status_code == 200

    rows = db_session.query(models.OrderAudit).filter(
        models.OrderAudit.order_id == order_id
    ).all()
    assert len(rows) == 1
    assert rows[0].action == models.OrderAuditAction.CANCEL
    assert rows[0].actor_user_id == owner.id
    assert rows[0].restaurant_id == restaurant.id
    assert rows[0].reason == "customer changed mind"


def test_cancel_after_served_writes_refund_audit_row(client, db_session, recipe_setup):
    restaurant, owner, owner_token, menu_item, inv_item = recipe_setup

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 1}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    order_id = r.json()["id"]

    client.patch(f"/orders/{order_id}/status", json={"status": "served"},
                 headers={"Authorization": f"Bearer {owner_token}"})
    client.patch(f"/orders/{order_id}/status", json={"status": "cancelled"},
                 headers={"Authorization": f"Bearer {owner_token}"})

    rows = db_session.query(models.OrderAudit).filter(
        models.OrderAudit.order_id == order_id
    ).all()
    assert len(rows) == 1
    assert rows[0].action == models.OrderAuditAction.REFUND


def test_cancelling_twice_only_writes_one_audit_row(client, db_session, recipe_setup):
    restaurant, owner, owner_token, menu_item, inv_item = recipe_setup

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 1}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    order_id = r.json()["id"]

    client.patch(f"/orders/{order_id}/status", json={"status": "cancelled"},
                 headers={"Authorization": f"Bearer {owner_token}"})
    # Re-cancelling an already-cancelled order must not double-log — mirrors the
    # existing ingredient-reversal guard (old_status != CANCELLED) on the same endpoint.
    client.patch(f"/orders/{order_id}/status", json={"status": "cancelled"},
                 headers={"Authorization": f"Bearer {owner_token}"})

    rows = db_session.query(models.OrderAudit).filter(
        models.OrderAudit.order_id == order_id
    ).all()
    assert len(rows) == 1


def test_payment_method_override_writes_audit_row(client, db_session, recipe_setup):
    restaurant, owner, owner_token, menu_item, inv_item = recipe_setup

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 1}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    order_id = r.json()["id"]

    r2 = client.patch(
        f"/orders/{order_id}/payment",
        json={"payment_method": "cash", "is_paid": True},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert r2.status_code == 200

    rows = db_session.query(models.OrderAudit).filter(
        models.OrderAudit.order_id == order_id,
        models.OrderAudit.action == models.OrderAuditAction.PAYMENT_CHANGE,
    ).all()
    assert len(rows) == 1
    assert rows[0].actor_user_id == owner.id
    assert "is_paid False -> True" in rows[0].reason


def test_repeating_identical_payment_update_does_not_duplicate_audit(client, db_session, recipe_setup):
    restaurant, owner, owner_token, menu_item, inv_item = recipe_setup

    r = client.post(
        "/orders/",
        json={"items": [{"menu_item_id": menu_item.id, "quantity": 1}]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    order_id = r.json()["id"]

    client.patch(f"/orders/{order_id}/payment", json={"payment_method": "cash", "is_paid": True},
                 headers={"Authorization": f"Bearer {owner_token}"})
    # Same payload again — no actual change, should not add a second audit row.
    client.patch(f"/orders/{order_id}/payment", json={"payment_method": "cash", "is_paid": True},
                 headers={"Authorization": f"Bearer {owner_token}"})

    rows = db_session.query(models.OrderAudit).filter(
        models.OrderAudit.order_id == order_id,
        models.OrderAudit.action == models.OrderAuditAction.PAYMENT_CHANGE,
    ).all()
    assert len(rows) == 1
