"""
Directive 018 — par-level / reorder-point automation.

Covers: the reorder-point math itself (par - on_hand, adjusted by demand),
that items missing par_level/default_supplier are never drafted (no
guessing), that an item with an already-open PO doesn't get a duplicate
draft, the approve gate (nothing reaches SENT without it), and receive's
reconciliation + shortfall-only alerting.
"""

from datetime import date

import pytest

import auth
import models
from time_utils import utcnow


def _user_with_staff_role(db_session, suffix, staff_role, role=models.Role.STAFF):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id, email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=role, staff_role=staff_role, token_version=0,
    )
    db_session.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token, user, restaurant


NEUTRAL_DATE = date(2026, 2, 15)   # No holiday, no school break — factor should be 1.0


@pytest.fixture
def reorder_setup(db_session):
    tenant = models.Tenant(name="PT")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R", address="x")
    db_session.add(restaurant)
    db_session.commit()

    supplier = models.Supplier(restaurant_id=restaurant.id, name="Chicken Co", contact_phone="+254700000000")
    db_session.add(supplier)
    db_session.commit()

    item = models.InventoryItem(
        restaurant_id=restaurant.id, item_name="Chicken", quantity=5.0, unit="kg",
        low_stock_threshold=10, cost_per_unit=300.0,
        par_level=50.0, default_supplier_id=supplier.id,
    )
    db_session.add(item)
    db_session.commit()
    return restaurant, supplier, item


# ── find_reorder_candidates ────────────────────────────────────────────────

def test_finds_candidate_below_threshold(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates
    restaurant, supplier, item = reorder_setup

    candidates = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.inventory_item_id == item.id
    assert c.base_quantity == pytest.approx(45.0)   # 50 par - 5 on hand
    assert c.demand_factor == pytest.approx(1.0)
    assert c.adjusted_quantity == pytest.approx(45.0)
    assert c.supplier_id == supplier.id


def test_item_above_threshold_not_a_candidate(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates
    restaurant, supplier, item = reorder_setup
    item.quantity = 40.0   # well above low_stock_threshold=10
    db_session.commit()

    candidates = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)
    assert candidates == []


def test_item_without_par_level_never_drafted(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates
    restaurant, supplier, item = reorder_setup
    item.par_level = None
    db_session.commit()

    candidates = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)
    assert candidates == []


def test_item_without_default_supplier_never_drafted(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates
    restaurant, supplier, item = reorder_setup
    item.default_supplier_id = None
    db_session.commit()

    candidates = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)
    assert candidates == []


def test_skips_item_with_already_open_purchase_order(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates
    restaurant, supplier, item = reorder_setup
    db_session.add(models.PurchaseOrder(
        restaurant_id=restaurant.id, supplier_id=supplier.id, inventory_item_id=item.id,
        quantity_ordered=20, status="PENDING",
    ))
    db_session.commit()

    candidates = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)
    assert candidates == []


def test_demand_signal_adjusts_quantity_upward(db_session, reorder_setup):
    """A public holiday (2026-01-01, hardcoded in ai/simulation/signals.py)
    should raise the order quantity above the flat par-minus-on-hand math."""
    from ai.reorder import find_reorder_candidates
    restaurant, supplier, item = reorder_setup

    neutral = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)[0]
    holiday = find_reorder_candidates(db_session, restaurant.id, on_date=date(2026, 1, 1))[0]

    assert holiday.demand_factor > neutral.demand_factor
    assert holiday.adjusted_quantity > neutral.adjusted_quantity


# ── draft_purchase_order ───────────────────────────────────────────────────

def test_draft_purchase_order_creates_pending_po_with_cents_conversion(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates, draft_purchase_order
    restaurant, supplier, item = reorder_setup

    candidate = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)[0]
    po = draft_purchase_order(db_session, restaurant.id, candidate)

    assert po.status == "PENDING"
    assert po.supplier_id == supplier.id
    assert po.inventory_item_id == item.id
    # item.cost_per_unit is 300.0 KES -> 30000 cents
    assert po.cost_per_unit == 30000


# ── approve / send ─────────────────────────────────────────────────────────

def test_approve_moves_pending_to_sent(client, db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates, draft_purchase_order
    restaurant, supplier, item = reorder_setup
    candidate = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)[0]
    po = draft_purchase_order(db_session, restaurant.id, candidate)

    token, user, _ = _user_with_staff_role(db_session, "sup1", models.StaffRole.SUPERVISOR)
    # Reassign the user/order onto the SAME restaurant as the fixture, since
    # _user_with_staff_role creates its own tenant/restaurant.
    user.tenant_id = restaurant.tenant_id
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})

    r = client.post(f"/purchase-orders/{po.id}/approve", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SENT"


def test_cannot_approve_twice(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates, draft_purchase_order, approve_and_send, PurchaseOrderError
    restaurant, supplier, item = reorder_setup
    candidate = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)[0]
    po = draft_purchase_order(db_session, restaurant.id, candidate)

    approve_and_send(db_session, po.id, restaurant.id, "owner@e.com")
    with pytest.raises(PurchaseOrderError):
        approve_and_send(db_session, po.id, restaurant.id, "owner@e.com")


# ── receive / reconcile ────────────────────────────────────────────────────

def test_receive_full_quantity_marks_delivered_and_updates_stock(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates, draft_purchase_order, approve_and_send, receive_purchase_order
    restaurant, supplier, item = reorder_setup
    candidate = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)[0]
    po = draft_purchase_order(db_session, restaurant.id, candidate)
    approve_and_send(db_session, po.id, restaurant.id, "owner@e.com")

    before_qty = item.quantity
    result = receive_purchase_order(db_session, po.id, restaurant.id, po.quantity_ordered, received_by_user_id=1)

    assert result.status == "DELIVERED"
    db_session.refresh(item)
    assert item.quantity == pytest.approx(before_qty + po.quantity_ordered)


def test_receive_short_marks_partial_and_flags_event(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates, draft_purchase_order, approve_and_send, receive_purchase_order
    from events.bus import subscribe, EventType
    received = []
    subscribe(EventType.PURCHASE_ORDER_DELIVERED, lambda p: received.append(p))

    restaurant, supplier, item = reorder_setup
    candidate = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)[0]
    po = draft_purchase_order(db_session, restaurant.id, candidate)
    approve_and_send(db_session, po.id, restaurant.id, "owner@e.com")

    short_qty = po.quantity_ordered - 10
    result = receive_purchase_order(db_session, po.id, restaurant.id, short_qty, received_by_user_id=1)
    assert result.status == "PARTIAL"

    import time as time_mod
    for _ in range(20):
        if received:
            break
        time_mod.sleep(0.05)
    assert len(received) == 1
    assert received[0]["shortfall"] == pytest.approx(10)


def test_cannot_receive_before_sent(db_session, reorder_setup):
    from ai.reorder import find_reorder_candidates, draft_purchase_order, receive_purchase_order, PurchaseOrderError
    restaurant, supplier, item = reorder_setup
    candidate = find_reorder_candidates(db_session, restaurant.id, on_date=NEUTRAL_DATE)[0]
    po = draft_purchase_order(db_session, restaurant.id, candidate)   # still PENDING, never approved

    with pytest.raises(PurchaseOrderError):
        receive_purchase_order(db_session, po.id, restaurant.id, po.quantity_ordered, received_by_user_id=1)


# ── Supplier CRUD (HTTP) ───────────────────────────────────────────────────

def test_manager_can_create_supplier(client, db_session):
    token, user, restaurant = _user_with_staff_role(db_session, "mgr2", models.StaffRole.MANAGER)
    r = client.post("/suppliers/", json={"name": "Fresh Veg Ltd", "contact_phone": "0712345678"},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Fresh Veg Ltd"


def test_waiter_cannot_create_supplier(client, db_session):
    token, user, restaurant = _user_with_staff_role(db_session, "waiter2", models.StaffRole.WAITER)
    r = client.post("/suppliers/", json={"name": "Fresh Veg Ltd"},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_reorder_settings_reject_unknown_supplier(client, db_session):
    token, user, restaurant = _user_with_staff_role(db_session, "mgr3", models.StaffRole.MANAGER)
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Rice", quantity=10, unit="kg", low_stock_threshold=5)
    db_session.add(item)
    db_session.commit()

    r = client.put(f"/inventory/{item.id}/reorder-settings",
                    json={"par_level": 40, "default_supplier_id": 999999},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404
