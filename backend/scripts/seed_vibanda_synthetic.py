"""Create a two-month, staging-only Vibanda demonstration tenant.

This script is intentionally hard to run by accident. It never targets the
real "Vibanda Village" tenant, requires both an environment gate and a CLI
confirmation, and gives the initial owner a caller-supplied password.

Example (staging only):
  SYNTHETIC_DATA_ALLOWED=true python scripts/seed_vibanda_synthetic.py \\
    --yes-synthetic-data --owner-email demo@example.test --owner-password '...'
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import get_password_hash
from database import SessionLocal, init_db
from models import (InventoryItem, MenuItem, Restaurant, Role, StaffMember,
                    Table, TableStatus, Tenant, User)
from seed_generators import generate_orders, generate_reservations, generate_stock_movements
from scripts.reseed_demo import wipe_restaurant

SYNTHETIC_TENANT = "Vibanda Village — Synthetic"
SYNTHETIC_RESTAURANT = "Vibanda Village — Synthetic"
HISTORY_DAYS = 60

MENU = [
    ("Nyama Choma 1/4", 65000, 26000), ("Ugali & Sukuma", 25000, 8000),
    ("Grilled Chicken", 75000, 30000), ("Chapati Ndengu", 30000, 10000),
    ("Pilau Beef", 45000, 18000), ("Soda", 12000, 6000),
    ("Fresh Juice", 20000, 7000), ("Chai", 8000, 2000),
]
INVENTORY = [
    ("Tomatoes", 8, "kg", 12000, 15), ("Beef", 12, "kg", 62000, 10),
    ("Chicken", 5, "kg", 45000, 8), ("Maize flour", 20, "kg", 9000, 10),
    ("Cooking oil", 6, "L", 28000, 5), ("Sukuma wiki", 4, "kg", 6000, 8),
]


def ensure_scaffold(db, owner_email: str, owner_password: str) -> Restaurant:
    tenant = db.query(Tenant).filter(Tenant.name == SYNTHETIC_TENANT).first()
    if tenant is None:
        tenant = Tenant(name=SYNTHETIC_TENANT, plan="synthetic-staging")
        db.add(tenant); db.flush()
    owner = db.query(User).filter(User.tenant_id == tenant.id, User.email == owner_email).first()
    if owner is None:
        owner = User(tenant_id=tenant.id, email=owner_email, hashed_password=get_password_hash(owner_password), role=Role.ADMIN)
        db.add(owner); db.flush()
    restaurant = db.query(Restaurant).filter(Restaurant.tenant_id == tenant.id).first()
    if restaurant is None:
        restaurant = Restaurant(tenant_id=tenant.id, name=SYNTHETIC_RESTAURANT, address="Synthetic staging environment")
        db.add(restaurant); db.flush()
    if not db.query(MenuItem).filter(MenuItem.restaurant_id == restaurant.id).count():
        db.add_all([MenuItem(restaurant_id=restaurant.id, name=name, price=price, cost_price=cost, category="Food" if price >= 20000 else "Drinks", is_available=True) for name, price, cost in MENU])
    if not db.query(InventoryItem).filter(InventoryItem.restaurant_id == restaurant.id).count():
        db.add_all([InventoryItem(restaurant_id=restaurant.id, item_name=name, quantity=qty, unit=unit, cost_per_unit_cents=cost, low_stock_threshold=threshold) for name, qty, unit, cost, threshold in INVENTORY])
    if not db.query(Table).filter(Table.restaurant_id == restaurant.id).count():
        db.add_all([Table(restaurant_id=restaurant.id, table_number=number, capacity=4, status=TableStatus.AVAILABLE) for number in range(1, 11)])
    if not db.query(StaffMember).filter(StaffMember.restaurant_id == restaurant.id).count():
        db.add_all([StaffMember(restaurant_id=restaurant.id, name=name, role_title=role, hourly_rate=rate) for name, role, rate in [("Chef Wanjiru", "Head Chef", 12000), ("Otieno", "Waiter", 6000), ("Achieng", "Cashier", 7000), ("Mutua", "Cook", 8000)]])
    db.flush()
    owner.active_restaurant_id = restaurant.id
    return restaurant


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed only the named synthetic Vibanda staging tenant.")
    parser.add_argument("--yes-synthetic-data", action="store_true", help="required confirmation")
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--owner-password", required=True)
    args = parser.parse_args()
    if os.getenv("SYNTHETIC_DATA_ALLOWED", "").lower() != "true":
        parser.error("set SYNTHETIC_DATA_ALLOWED=true; this script is staging-only")
    if not args.yes_synthetic_data:
        parser.error("pass --yes-synthetic-data after confirming this is an isolated staging database")
    init_db()
    db = SessionLocal()
    try:
        restaurant = ensure_scaffold(db, args.owner_email, args.owner_password)
        wipe_restaurant(db, restaurant.id)
        items = db.query(MenuItem).filter(MenuItem.restaurant_id == restaurant.id).all()
        tables = db.query(Table).filter(Table.restaurant_id == restaurant.id).all()
        inventory = db.query(InventoryItem).filter(InventoryItem.restaurant_id == restaurant.id).all()
        orders = generate_orders(db, restaurant.id, items, days=HISTORY_DAYS, include_today=True)
        generate_reservations(db, restaurant.id, tables, days=HISTORY_DAYS, include_today=True)
        generate_stock_movements(db, inventory, days=HISTORY_DAYS, include_today=True)
        db.commit()
        print(f"[OK] Seeded {SYNTHETIC_TENANT}: {orders} synthetic orders across {HISTORY_DAYS} days.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
