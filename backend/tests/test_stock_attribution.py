"""
Stock-movement attribution (audit finding, migration 029).

`POST /inventory/{id}/receive` and `/adjust` are open to any authenticated
user — deliberately, since logging a delivery or writing off waste is normal
floor work, not an admin task. But StockMovement recorded only
item/type/quantity/reason, so a negative adjustment with a free-text reason
was completely anonymous: the classic shrinkage vector, sitting directly
under the profit-leak / portion-drift detection this product sells.

These tests prove every movement now records who performed it — including
the STAFF-written negative adjustment, which is the case that actually
matters — and that attribution survives as history rather than blocking
user deletion.
"""

import auth
import models


def _tenant_with_user_and_item(db_session, suffix, role=models.Role.STAFF):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()

    user = models.User(
        tenant_id=tenant.id,
        email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("CorrectHorseBattery1!"),
        role=role,
        token_version=0,
    )
    db_session.add(user)

    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()

    item = models.InventoryItem(
        restaurant_id=restaurant.id, item_name="Tomatoes",
        quantity=100.0, unit="kg", cost_per_unit=50, low_stock_threshold=10,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(item)

    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return user, item, token


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _latest_movement(db_session, item_id):
    return (
        db_session.query(models.StockMovement)
        .filter(models.StockMovement.inventory_item_id == item_id)
        .order_by(models.StockMovement.id.desc())
        .first()
    )


def test_receive_records_who_did_it(client, db_session):
    user, item, token = _tenant_with_user_and_item(db_session, "recv")

    r = client.post(f"/inventory/{item.id}/receive",
                    json={"quantity": 20.0, "supplier": "Mama Mboga"},
                    headers=_auth_headers(token))
    assert r.status_code == 200

    movement = _latest_movement(db_session, item.id)
    assert movement.user_id == user.id
    assert movement.movement_type == models.StockMovementType.IN


def test_negative_adjustment_by_staff_is_attributed(client, db_session):
    """The case that matters: a STAFF user writing stock DOWN with a free-text
    reason. Previously this produced a completely anonymous record."""
    user, item, token = _tenant_with_user_and_item(db_session, "shrink", role=models.Role.STAFF)

    r = client.post(f"/inventory/{item.id}/adjust",
                    json={"quantity": -15.0, "reason": "spoilage"},
                    headers=_auth_headers(token))
    assert r.status_code == 200

    movement = _latest_movement(db_session, item.id)
    assert movement.user_id == user.id, "a negative stock adjustment must never be anonymous"
    assert movement.movement_type == models.StockMovementType.OUT
    assert movement.quantity == 15.0

    db_session.refresh(item)
    assert item.quantity == 85.0


def test_attribution_survives_user_deletion_as_history(client, db_session):
    """SET NULL, not CASCADE — removing a user must not delete the stock
    history they created, nor be blocked by it."""
    user, item, token = _tenant_with_user_and_item(db_session, "hist")

    client.post(f"/inventory/{item.id}/adjust",
                json={"quantity": -5.0, "reason": "breakage"},
                headers=_auth_headers(token))

    movement_id = _latest_movement(db_session, item.id).id

    db_session.delete(user)
    db_session.commit()

    movement = db_session.query(models.StockMovement).filter(
        models.StockMovement.id == movement_id
    ).first()
    assert movement is not None, "stock history must outlive the user who created it"
