"""Engines run on normal entry points — not only cron."""
from __future__ import annotations

import pytest

import models
from auth import get_password_hash
from events.bus import EventType, subscribe
from services.dish_cost import dish_cost_cents, sync_menu_cost_prices
from tests.test_quicksell_webhook import _post, _KEY


@pytest.fixture(autouse=True)
def _quicksell_key(monkeypatch):
    monkeypatch.setenv("QUICKSELL_API_KEY", _KEY)


@pytest.fixture(autouse=True)
def _mirror_tables(db_env):
    import database
    from integration.models import Base as IntegrationBase

    IntegrationBase.metadata.create_all(bind=database.engine)


@pytest.fixture
def empty_stack(db_session):
    tenant = models.Tenant(name="Eleven")
    db_session.add(tenant)
    db_session.flush()
    owner = models.User(
        tenant_id=tenant.id,
        email="owner-empty@eleven.leviii",
        hashed_password=get_password_hash("Ownerpass1"),
        role=models.Role.ADMIN,
        staff_role=models.StaffRole.OWNER,
        is_active=True,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Eleven", address="Audit")
    db_session.add_all([owner, restaurant])
    db_session.commit()
    owner.active_restaurant_id = restaurant.id
    db_session.commit()
    return restaurant, owner


def test_quicksell_sale_emits_order_events(client, db_session, empty_stack, monkeypatch):
    restaurant, owner = empty_stack
    monkeypatch.setenv("ELEVEN_RESTAURANT_NAME", "Eleven")
    rice = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name="Rice",
        quantity=50,
        unit="kg",
        low_stock_threshold=5,
        par_level=40,
        cost_per_unit=100,
    )
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Farm", contact_phone="", avg_lead_days=3)
    db_session.add(supplier)
    db_session.flush()
    rice.default_supplier_id = supplier.id
    dish = models.MenuItem(
        restaurant_id=restaurant.id,
        name="Pilau",
        category="Mains",
        price=50000,
        cost_price=0,
        is_available=True,
    )
    db_session.add_all([rice, dish])
    db_session.flush()
    db_session.add(
        models.MenuIngredient(
            menu_item_id=dish.id,
            inventory_item_id=rice.id,
            quantity_per_serving=0.5,
            yield_fraction=1.0,
            recipe_unit="kg",
            created_by_user_id=owner.id,
        )
    )
    db_session.commit()

    seen: list[int | None] = []

    def on_created(payload):
        seen.append(payload.get("order_id"))

    def on_paid(payload):
        seen.append(payload.get("order_id"))

    subscribe(EventType.ORDER_CREATED, on_created)
    subscribe(EventType.ORDER_PAID, on_paid)
    body = {
            "entity": "sale",
            "records": [{
                "source_id": "AUDIT-QS-1",
                "occurred_at": "2026-09-19T14:30:00+03:00",
                "total_cents": 50000,
                "lines": [{"name": "Pilau", "quantity": 4, "unit_price_cents": 12500}],
            }],
        }
    assert _post(client, body).status_code == 200
    db_session.refresh(rice)
    assert db_session.query(models.Order).filter(models.Order.restaurant_id == restaurant.id).count() == 1
    assert rice.quantity < 50
    assert len(seen) >= 2


def test_maybe_draft_reorders_invokes_draft(db_session, empty_stack, monkeypatch):
    """after_inventory_touch path calls reorder draft (not cron-only)."""
    from ai.reorder import ReorderCandidate
    from services import engine_triggers

    restaurant, _owner = empty_stack
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Farm", contact_phone="", avg_lead_days=2)
    rice = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name="Rice",
        quantity=2,
        unit="kg",
        low_stock_threshold=10,
        par_level=30,
        default_supplier_id=None,
        cost_per_unit=100,
    )
    db_session.add(supplier)
    db_session.flush()
    rice.default_supplier_id = supplier.id
    db_session.add(rice)
    db_session.commit()

    cand = ReorderCandidate(
        inventory_item_id=rice.id,
        item_name="Rice",
        unit="kg",
        on_hand=2,
        par_level=30,
        base_quantity=28,
        demand_factor=1.0,
        demand_reasons=[],
        adjusted_quantity=28,
        supplier_id=supplier.id,
        supplier_name="Farm",
        cost_per_unit=100,
        supplier_reliability_score=90.0,
    )
    drafts: list[int] = []

    def fake_find(*_a, **_k):
        return [cand]

    def fake_draft(db, rid, candidate, requested_by_user_id=None):
        drafts.append(candidate.inventory_item_id)
        row = models.PurchaseOrder(
            restaurant_id=rid,
            supplier_id=candidate.supplier_id,
            inventory_item_id=candidate.inventory_item_id,
            quantity_ordered=candidate.adjusted_quantity,
            unit=candidate.unit,
            status="PENDING",
        )
        db.add(row)
        db.commit()

    monkeypatch.setattr("ai.reorder.find_reorder_candidates", fake_find)
    monkeypatch.setattr("ai.reorder.draft_purchase_order", fake_draft)
    assert engine_triggers.maybe_draft_reorders(db_session, restaurant.id) == 1
    assert drafts == [rice.id]


def test_sync_menu_cost_prices_after_invoice(db_session):
    from tests.test_storekeeper_foundation import _tenant

    _, _, restaurant = _tenant(db_session, "Eleven", "sync@eleven.leviii")
    rice = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name="Rice",
        quantity=10,
        unit="kg",
        cost_per_unit=200,
    )
    db_session.add(rice)
    db_session.flush()
    dish = models.MenuItem(restaurant_id=restaurant.id, name="Pilau", category="Kitchen", price=45000, cost_price=0)
    db_session.add(dish)
    db_session.flush()
    db_session.add(
        models.MenuIngredient(
            menu_item_id=dish.id,
            inventory_item_id=rice.id,
            quantity_per_serving=0.25,
            recipe_unit="kg",
            yield_fraction=1.0,
        )
    )
    db_session.commit()
    assert dish_cost_cents(db_session, restaurant.id, dish.id) == 5000
    updated = sync_menu_cost_prices(db_session, restaurant.id)
    assert updated == 1
    db_session.refresh(dish)
    assert dish.cost_price == 5000