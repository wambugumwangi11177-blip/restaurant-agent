"""
Directive 015 (staff RBAC) + directive 016 (stock chain-of-custody).

Covers the pieces that are easy to get subtly wrong and hard to catch by
reading the code: the NULL-staff_role distinguishable 403, Owner's bypass
still working after the second gate was added, a deactivated staff login
actually being revoked on the very next request (not just hidden from the
nav), the two-party transfer confirm writing the StockMovement pair only on
a match, and the variance math's threshold + div-by-zero behavior.
"""

import pytest

import auth
import models
from time_utils import utcnow


def _user_with_staff_role(db_session, suffix, role=models.Role.STAFF, staff_role=None, is_active=True):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=role,
        staff_role=staff_role,
        is_active=is_active,
        token_version=0,
    )
    db_session.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token, user, restaurant


# ── require_staff_role: unassigned vs assigned vs Owner bypass ────────────────

def test_unassigned_staff_role_gets_distinguishable_403(client, db_session):
    token, _, _ = _user_with_staff_role(db_session, "unassigned")
    r = client.get("/inventory/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert r.json()["detail"] == "staff_role_unassigned"


def test_correct_tier_allowed(client, db_session):
    token, _, _ = _user_with_staff_role(db_session, "stockkeeper", staff_role=models.StaffRole.STOCKKEEPER)
    r = client.get("/inventory/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_wrong_tier_forbidden(client, db_session):
    """Waiter is not in inventory's _CAN_READ group (directive 015's matrix: '–')."""
    token, _, _ = _user_with_staff_role(db_session, "waiter", staff_role=models.StaffRole.WAITER)
    r = client.get("/inventory/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert r.json()["detail"] != "staff_role_unassigned"


def test_owner_bypasses_staff_role_gate_regardless_of_staff_role(client, db_session):
    """An Owner (Role.ADMIN) must never be blocked by the second gate, even
    with no staff_role set — require_staff_role's ADMIN/SUPERADMIN bypass is
    what directive 015 promises ("Owner maps 1:1 onto Role.ADMIN")."""
    token, _, _ = _user_with_staff_role(db_session, "owner", role=models.Role.ADMIN, staff_role=None)
    r = client.get("/inventory/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


# ── Staff deactivation actually revokes an existing login ─────────────────────

def test_deactivating_staff_member_revokes_linked_login(client, db_session):
    manager_token, manager, restaurant = _user_with_staff_role(
        db_session, "mgr", role=models.Role.STAFF, staff_role=models.StaffRole.MANAGER
    )
    staff_token, staff_user, _ = _user_with_staff_role(
        db_session, "waiterlogin", role=models.Role.STAFF, staff_role=models.StaffRole.WAITER
    )
    member = models.StaffMember(
        restaurant_id=restaurant.id, user_id=staff_user.id, name="Waiter One",
    )
    db_session.add(member)
    db_session.commit()

    # Sanity: the login works before deactivation.
    pre = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {staff_token}"})
    assert pre.status_code == 200

    resp = client.put(
        f"/staff/{member.id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    # manager's own StaffMember row doesn't exist yet in this test's DB, but
    # require_staff_role only checks current_user.staff_role — it doesn't
    # require a StaffMember row to exist, so this should succeed.
    assert resp.status_code == 200, resp.text

    post = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {staff_token}"})
    assert post.status_code == 401


# ── Stock transfer: two-party custody ──────────────────────────────────────────

@pytest.fixture
def transfer_setup(db_session):
    tenant = models.Tenant(name="TT")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R", address="x")
    db_session.add(restaurant)
    db_session.commit()

    sender = models.User(tenant_id=tenant.id, email="sender@e.com",
                          hashed_password=auth.get_password_hash("x"),
                          role=models.Role.STAFF, staff_role=models.StaffRole.STOCKKEEPER, token_version=0)
    receiver = models.User(tenant_id=tenant.id, email="receiver@e.com",
                            hashed_password=auth.get_password_hash("x"),
                            role=models.Role.STAFF, staff_role=models.StaffRole.KITCHEN, token_version=0)
    db_session.add_all([sender, receiver])
    db_session.commit()

    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Rice",
                                 quantity=100.0, unit="kg", low_stock_threshold=10)
    db_session.add(item)
    db_session.commit()

    sender_token = auth.create_access_token({"sub": sender.email, "ver": 0})
    receiver_token = auth.create_access_token({"sub": receiver.email, "ver": 0})
    return restaurant, item, sender_token, receiver_token


def test_matching_transfer_confirms_and_writes_movement_pair(client, db_session, transfer_setup):
    restaurant, item, sender_token, receiver_token = transfer_setup

    r = client.post(
        "/stock/transfers",
        json={"inventory_item_id": item.id, "quantity": 10.0, "from_location": "store", "to_location": "kitchen"},
        headers={"Authorization": f"Bearer {sender_token}"},
    )
    assert r.status_code == 201, r.text
    transfer_id = r.json()["id"]

    before_movements = db_session.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id == item.id
    ).count()

    r2 = client.post(
        f"/stock/transfers/{transfer_id}/confirm",
        json={"confirmed_quantity": 10.0},
        headers={"Authorization": f"Bearer {receiver_token}"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "confirmed"

    after_movements = db_session.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id == item.id
    ).count()
    assert after_movements == before_movements + 2   # OUT + IN pair, exactly once


def test_mismatched_transfer_disputes_without_writing_movements(client, db_session, transfer_setup):
    restaurant, item, sender_token, receiver_token = transfer_setup

    r = client.post(
        "/stock/transfers",
        json={"inventory_item_id": item.id, "quantity": 10.0},
        headers={"Authorization": f"Bearer {sender_token}"},
    )
    transfer_id = r.json()["id"]

    before_movements = db_session.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id == item.id
    ).count()

    r2 = client.post(
        f"/stock/transfers/{transfer_id}/confirm",
        json={"confirmed_quantity": 7.0},   # 3kg short — a real mismatch
        headers={"Authorization": f"Bearer {receiver_token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "disputed"

    after_movements = db_session.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id == item.id
    ).count()
    # A disputed transfer must NOT silently move stock on either side's
    # say-so — that would defeat the entire point of requiring both parties.
    assert after_movements == before_movements


def test_storekeeper_cannot_confirm_the_issue_they_sent(client, db_session, transfer_setup):
    """Eleven: the storekeeper and the accountant were issuing and confirming together.
    The person who sends the stock cannot also confirm it."""
    _restaurant, item, sender_token, _receiver_token = transfer_setup
    issued = client.post(
        "/stock/transfers",
        json={"inventory_item_id": item.id, "quantity": 4.0, "unit": "kg", "from_location": "store", "to_location": "kitchen"},
        headers={"Authorization": f"Bearer {sender_token}"},
    )
    assert issued.status_code == 201, issued.text
    confirmed = client.post(
        f"/stock/transfers/{issued.json()['id']}/confirm",
        json={"confirmed_quantity": 4.0},
        headers={"Authorization": f"Bearer {sender_token}"},
    )
    assert confirmed.status_code == 403, confirmed.text
    assert client.get("/stock/transfers", headers={"Authorization": f"Bearer {sender_token}"}).status_code == 200


def test_manager_and_owner_cannot_confirm_in_place_of_the_kitchen(client, db_session, transfer_setup):
    restaurant, item, sender_token, _receiver_token = transfer_setup
    issued = client.post(
        "/stock/transfers",
        json={"inventory_item_id": item.id, "quantity": 4.0, "unit": "kg"},
        headers={"Authorization": f"Bearer {sender_token}"},
    )
    transfer_id = issued.json()["id"]
    manager = models.User(
        tenant_id=restaurant.tenant_id, email="mgr-confirm@e.com", hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, staff_role=models.StaffRole.MANAGER, token_version=0,
    )
    owner = models.User(
        tenant_id=restaurant.tenant_id, email="owner-confirm@e.com", hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER, token_version=0,
    )
    db_session.add_all([manager, owner])
    db_session.commit()
    manager_token = auth.create_access_token({"sub": manager.email, "ver": 0})
    manager_denied = client.post(
        f"/stock/transfers/{transfer_id}/confirm",
        json={"confirmed_quantity": 4.0},
        headers={"Authorization": f"Bearer {manager_token}"},
    )
    assert manager_denied.status_code == 403, manager_denied.text
    owner_token = auth.create_access_token({"sub": owner.email, "ver": 0})
    owner_denied = client.post(
        f"/stock/transfers/{transfer_id}/confirm",
        json={"confirmed_quantity": 4.0},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_denied.status_code == 403, owner_denied.text
    assert "kitchen" in owner_denied.json()["detail"].lower()


def test_kitchen_confirming_less_than_issued_marks_the_handover_disputed(client, db_session, transfer_setup):
    """4 kg issued, 3.8 kg counted in the kitchen: disputed, and stock is not moved."""
    _restaurant, item, sender_token, receiver_token = transfer_setup
    item.item_name = "Beef"
    db_session.commit()
    issued = client.post(
        "/stock/transfers",
        json={"inventory_item_id": item.id, "quantity": 4.0, "unit": "kg", "from_location": "store", "to_location": "kitchen"},
        headers={"Authorization": f"Bearer {sender_token}"},
    )
    assert issued.status_code == 201, issued.text
    before = db_session.query(models.StockMovement).filter(models.StockMovement.inventory_item_id == item.id).count()
    confirmed = client.post(
        f"/stock/transfers/{issued.json()['id']}/confirm",
        json={"confirmed_quantity": 3.8},
        headers={"Authorization": f"Bearer {receiver_token}"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "disputed"
    assert confirmed.json()["confirmed_quantity"] == 3.8
    after = db_session.query(models.StockMovement).filter(models.StockMovement.inventory_item_id == item.id).count()
    assert after == before


def test_the_kitchen_user_who_issued_cannot_confirm_that_same_issue(db_session, transfer_setup):
    from ai.stock_custody import TransferConfirmError, confirm_transfer
    restaurant, item, _sender_token, _receiver_token = transfer_setup
    kitchen = db_session.query(models.User).filter_by(email="receiver@e.com").one()
    transfer = models.StockTransfer(
        restaurant_id=restaurant.id, inventory_item_id=item.id, quantity=4.0, unit="kg",
        from_location="store", to_location="kitchen", status=models.StockTransferStatus.PENDING,
        initiated_by_user_id=kitchen.id,
    )
    db_session.add(transfer)
    db_session.commit()
    with pytest.raises(TransferConfirmError, match="different person"):
        confirm_transfer(db_session, transfer.id, restaurant.id, kitchen.id, 4.0)


def test_transfer_cannot_be_confirmed_twice(client, db_session, transfer_setup):
    restaurant, item, sender_token, receiver_token = transfer_setup
    r = client.post("/stock/transfers", json={"inventory_item_id": item.id, "quantity": 5.0},
                     headers={"Authorization": f"Bearer {sender_token}"})
    transfer_id = r.json()["id"]
    client.post(f"/stock/transfers/{transfer_id}/confirm", json={"confirmed_quantity": 5.0},
                headers={"Authorization": f"Bearer {receiver_token}"})
    r2 = client.post(f"/stock/transfers/{transfer_id}/confirm", json={"confirmed_quantity": 5.0},
                      headers={"Authorization": f"Bearer {receiver_token}"})
    assert r2.status_code == 400


# ── Variance computation (ai/stock_custody.py) ─────────────────────────────────

def test_variance_flags_a_real_gap(db_session):
    from ai.stock_custody import compute_variance_report

    restaurant = models.Restaurant(tenant_id=None, name="VR", address="x")
    db_session.add(restaurant)
    db_session.commit()

    menu_item = models.MenuItem(restaurant_id=restaurant.id, name="Chips", price=300, cost_price=100, category="mains")
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Potatoes", quantity=50.0, unit="kg", low_stock_threshold=5)
    db_session.add_all([menu_item, item])
    db_session.commit()

    # 0.2kg potatoes per serving of chips.
    db_session.add(models.MenuIngredient(menu_item_id=menu_item.id, inventory_item_id=item.id, quantity_per_serving=0.2))
    db_session.commit()

    # Sold 100 servings -> theoretical usage = 20kg.
    order = models.Order(restaurant_id=restaurant.id, status=models.OrderStatus.SERVED, total=30000, created_at=utcnow())
    db_session.add(order)
    db_session.commit()
    db_session.add(models.OrderItem(order_id=order.id, menu_item_id=menu_item.id, quantity=100, unit_price=300))
    db_session.commit()

    # But 30kg actually went OUT — a 50% gap, well over the 3% threshold.
    db_session.add(models.StockMovement(
        inventory_item_id=item.id, movement_type=models.StockMovementType.OUT,
        quantity=30.0, created_at=utcnow(),
    ))
    db_session.commit()

    report = compute_variance_report(db_session, restaurant.id, hours=24)
    assert len(report) == 1
    assert report[0].flagged is True
    assert report[0].variance_pct == pytest.approx(0.5, abs=0.01)


def test_variance_within_tolerance_not_flagged(db_session):
    from ai.stock_custody import compute_variance_report

    restaurant = models.Restaurant(tenant_id=None, name="VR2", address="x")
    db_session.add(restaurant)
    db_session.commit()
    menu_item = models.MenuItem(restaurant_id=restaurant.id, name="Soup", price=200, cost_price=80, category="starters")
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Stock", quantity=50.0, unit="l", low_stock_threshold=5)
    db_session.add_all([menu_item, item])
    db_session.commit()
    db_session.add(models.MenuIngredient(menu_item_id=menu_item.id, inventory_item_id=item.id, quantity_per_serving=1.0))
    db_session.commit()

    order = models.Order(restaurant_id=restaurant.id, status=models.OrderStatus.SERVED, total=2000, created_at=utcnow())
    db_session.add(order)
    db_session.commit()
    db_session.add(models.OrderItem(order_id=order.id, menu_item_id=menu_item.id, quantity=10, unit_price=200))
    db_session.commit()

    # 10.1 actual vs 10 theoretical — 1% gap, under the 3% threshold.
    db_session.add(models.StockMovement(
        inventory_item_id=item.id, movement_type=models.StockMovementType.OUT,
        quantity=10.1, created_at=utcnow(),
    ))
    db_session.commit()

    report = compute_variance_report(db_session, restaurant.id, hours=24)
    assert len(report) == 1
    assert report[0].flagged is False


def test_variance_skips_zero_theoretical_instead_of_crashing(db_session):
    """An item that moved stock but has no recipe usage in the window —
    variance is undefined, not zero or infinite. Must not raise."""
    from ai.stock_custody import compute_variance_report

    restaurant = models.Restaurant(tenant_id=None, name="VR3", address="x")
    db_session.add(restaurant)
    db_session.commit()
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Napkins", quantity=200.0, unit="pieces", low_stock_threshold=20)
    db_session.add(item)
    db_session.commit()
    db_session.add(models.StockMovement(
        inventory_item_id=item.id, movement_type=models.StockMovementType.OUT,
        quantity=15.0, created_at=utcnow(),
    ))
    db_session.commit()

    report = compute_variance_report(db_session, restaurant.id, hours=24)
    assert len(report) == 1
    assert report[0].variance_pct is None
    assert report[0].flagged is False
