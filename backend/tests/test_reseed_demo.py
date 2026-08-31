"""
Tests for the scoped demo re-seed (scripts/reseed_demo.py).

The gate this file protects: the re-seed must replace the demo tenant's
transactional data (orders now covering today) WITHOUT touching any other
tenant's rows. Time is pinned to a fixed "now" (20:00 UTC) so day-zero
clamping produces today's orders deterministically, regardless of when CI runs.
"""

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

from models import (
    Tenant, Restaurant, MenuItem, InventoryItem, Table,
    Order, OrderItem, StockMovement, Reservation, PrepTime,
    TableStatus,
)
import seed_generators
from seed_generators import (
    generate_orders, generate_stock_movements, generate_reservations,
)

FIXED_NOW = dt.datetime(2026, 8, 31, 20, 0)  # 20:00 — dinner hours already elapsed


@pytest.fixture
def fixed_now(monkeypatch):
    monkeypatch.setattr(seed_generators, "utcnow", lambda: FIXED_NOW)
    return FIXED_NOW


def _load_reseed():
    path = Path(__file__).resolve().parents[1] / "scripts" / "reseed_demo.py"
    spec = importlib.util.spec_from_file_location("reseed_demo_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_restaurant(db, tenant_name, restaurant_name):
    tenant = Tenant(name=tenant_name, plan="premium")
    db.add(tenant)
    db.flush()
    r = Restaurant(tenant_id=tenant.id, name=restaurant_name, address="Nairobi")
    db.add(r)
    db.flush()
    menu = [
        MenuItem(restaurant_id=r.id, name="Nyama Choma", description="", price=120000,
                 cost_price=45000, category="Main", prep_station="grill",
                 avg_prep_minutes=25.0, is_available=True),
        MenuItem(restaurant_id=r.id, name="Soda", description="", price=15000,
                 cost_price=6000, category="Beverages", prep_station="drinks",
                 avg_prep_minutes=1.0, is_available=True),
    ]
    inv = [
        InventoryItem(restaurant_id=r.id, item_name="Beef", quantity=50, unit="kg",
                      cost_per_unit=800, low_stock_threshold=5, expiry_days=7),
    ]
    tables = [Table(restaurant_id=r.id, table_number=1, capacity=4, status=TableStatus.AVAILABLE)]
    db.add_all(menu + inv + tables)
    db.flush()
    return tenant, r, menu, inv, tables


@pytest.fixture
def two_tenants(db_session):
    """Demo tenant + an unrelated second tenant, both seeded with 5 days of history."""
    db = db_session
    _, demo_r, demo_menu, demo_inv, demo_tables = _make_restaurant(db, "Leviii Client Demo", "Client Kitchen")
    _, other_r, other_menu, other_inv, other_tables = _make_restaurant(db, "Another Tenant", "Other Place")

    generate_orders(db, demo_r.id, demo_menu, days=5, include_today=False)
    generate_stock_movements(db, demo_inv, days=5, include_today=False)
    generate_reservations(db, demo_r.id, demo_tables, days=5, include_today=False)

    generate_orders(db, other_r.id, other_menu, days=5, include_today=False)
    generate_stock_movements(db, other_inv, days=5, include_today=False)
    generate_reservations(db, other_r.id, other_tables, days=5, include_today=False)

    db.commit()
    return db, demo_r, demo_menu, demo_inv, demo_tables, other_r


def _counts(db, restaurant_id):
    return {
        "orders": db.query(Order).filter(Order.restaurant_id == restaurant_id).count(),
        "order_items": db.query(OrderItem).join(Order).filter(Order.restaurant_id == restaurant_id).count(),
        "prep_times": db.query(PrepTime).join(OrderItem).join(Order).filter(Order.restaurant_id == restaurant_id).count(),
        "stock_movements": db.query(StockMovement).join(InventoryItem).filter(InventoryItem.restaurant_id == restaurant_id).count(),
        "reservations": db.query(Reservation).filter(Reservation.restaurant_id == restaurant_id).count(),
    }


def test_reseed_replaces_demo_orders_and_covers_today(fixed_now, two_tenants):
    db, demo_r, demo_menu, demo_inv, demo_tables, other_r = two_tenants
    reseed = _load_reseed()

    old_ids = {o.id for o in db.query(Order).filter(Order.restaurant_id == demo_r.id)}
    assert old_ids
    other_before = _counts(db, other_r.id)

    reseed.wipe_restaurant(db, demo_r.id)
    generate_orders(db, demo_r.id, demo_menu, days=5, include_today=True)
    generate_stock_movements(db, demo_inv, days=5, include_today=True)
    generate_reservations(db, demo_r.id, demo_tables, days=5, include_today=True)
    db.commit()

    new_orders = db.query(Order).filter(Order.restaurant_id == demo_r.id).all()
    assert new_orders
    assert old_ids.isdisjoint({o.id for o in new_orders}), "old demo orders must be gone"
    assert any(o.created_at.date() == fixed_now.date() for o in new_orders), \
        "regenerated history must include today"
    assert not any(o.created_at > fixed_now for o in new_orders), \
        "no order may land in the future of the seeded day"

    assert _counts(db, other_r.id) == other_before, "second tenant must be untouched"


def test_main_refuses_without_confirmation_flag(fixed_now, two_tenants, monkeypatch):
    db, demo_r, *_rest, other_r = two_tenants
    reseed = _load_reseed()
    before = {o.id for o in db.query(Order).filter(Order.restaurant_id == demo_r.id)}
    other_before = _counts(db, other_r.id)

    monkeypatch.setattr("sys.argv", ["reseed_demo.py", "--tenant", "Leviii Client Demo"])
    assert reseed.main() == 2

    after = {o.id for o in db.query(Order).filter(Order.restaurant_id == demo_r.id)}
    assert after == before
    assert _counts(db, other_r.id) == other_before


def test_main_rejects_unknown_tenant(fixed_now, two_tenants, monkeypatch):
    reseed = _load_reseed()
    monkeypatch.setattr("sys.argv", ["reseed_demo.py", "--tenant", "No Such Tenant", "--yes-delete-demo-data"])
    assert reseed.main() == 2


def test_main_with_flag_reseeds_and_leaves_other_tenant_alone(fixed_now, two_tenants, monkeypatch):
    db, demo_r, *_rest, other_r = two_tenants
    reseed = _load_reseed()
    before = {o.id for o in db.query(Order).filter(Order.restaurant_id == demo_r.id)}
    assert before
    other_before = _counts(db, other_r.id)

    monkeypatch.setattr("sys.argv", ["reseed_demo.py", "--tenant", "Leviii Client Demo", "--yes-delete-demo-data"])
    assert reseed.main() == 0

    new_orders = db.query(Order).filter(Order.restaurant_id == demo_r.id).all()
    assert new_orders
    assert before.isdisjoint({o.id for o in new_orders})
    assert any(o.created_at.date() == fixed_now.date() for o in new_orders)
    assert _counts(db, other_r.id) == other_before
