"""
execution/seed_local_dev_db.py
─────────────────────────────────
Builds a throwaway LOCAL SQLite dev database (backend/dev_local.db) — fully
decoupled from the shared Neon "production" DATABASE_URL in backend/.env.
This exists because of a real incident (2026-07-17): this feature branch's
models.py has diverged from what's safely deployable to the same DB the live
Railway/master backend uses, so testing this branch's stock-custody/staff-
notification work against that shared DB is not safe. See directive 016's
as-built notes for the incident writeup.

Sets DATABASE_URL/SECRET_KEY as process env vars BEFORE importing database/
models (database.py reads DATABASE_URL at import time) — never touches
backend/.env, which must keep pointing at the real DB for every other script.

Seeds one restaurant with a working login for all 7 staff_role tiers plus a
few inventory items, so the kitchen "request stock" -> storekeeper "fulfil"
-> confirm chain (and its notifications) has something real to click through.

Run: python execution/seed_local_dev_db.py
Then: uvicorn main:app --reload --port 8000   (from backend/, same env vars)
"""
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)

DB_PATH = os.path.join(_backend, "dev_local.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ.setdefault("SECRET_KEY", "dev-local-only-secret-not-for-production")

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)  # Fresh seed every run — this file is throwaway by design.

import database
database.init_db()

import auth
import models
from database import SessionLocal

PASSWORD = "DevTest2026!"

db = SessionLocal()
try:
    tenant = models.Tenant(name="Dev Test Kitchen")
    db.add(tenant)
    db.commit()

    restaurant = models.Restaurant(tenant_id=tenant.id, name="Dev Test Kitchen", address="Nairobi")
    db.add(restaurant)
    db.commit()

    accounts = [
        ("owner@dev.local", models.Role.ADMIN, models.StaffRole.OWNER),
        ("manager@dev.local", models.Role.STAFF, models.StaffRole.MANAGER),
        ("supervisor@dev.local", models.Role.STAFF, models.StaffRole.SUPERVISOR),
        ("controller@dev.local", models.Role.STAFF, models.StaffRole.CONTROLLER),
        ("stockkeeper@dev.local", models.Role.STAFF, models.StaffRole.STOCKKEEPER),
        ("kitchen@dev.local", models.Role.STAFF, models.StaffRole.KITCHEN),
        ("waiter@dev.local", models.Role.STAFF, models.StaffRole.WAITER),
    ]
    pw_hash = auth.get_password_hash(PASSWORD)
    for email, role, staff_role in accounts:
        user = models.User(
            tenant_id=tenant.id, email=email, hashed_password=pw_hash,
            role=role, staff_role=staff_role, is_active=True, token_version=0,
            is_email_verified=True,
        )
        db.add(user)
        db.commit()
        db.add(models.StaffMember(
            restaurant_id=restaurant.id, user_id=user.id,
            name=email.split("@")[0].capitalize(), role_title=staff_role.value.capitalize(),
            is_active=True,
        ))
        db.commit()

    items = [
        ("Chicken", "kg", 40.0, 8),
        ("Rice", "kg", 60.0, 10),
        ("Tomatoes", "kg", 15.0, 5),
        ("Cooking Oil", "liters", 20.0, 5),
    ]
    inv_items = {}
    for name, unit, qty, threshold in items:
        item = models.InventoryItem(
            restaurant_id=restaurant.id, item_name=name, quantity=qty, unit=unit,
            low_stock_threshold=threshold, cost_per_unit=200.0,
        )
        db.add(item)
        db.commit()
        inv_items[name] = item

    menu_item = models.MenuItem(
        restaurant_id=restaurant.id, name="Chicken Rice Combo", price=650, cost_price=250, category="mains",
    )
    db.add(menu_item)
    db.commit()
    db.add(models.MenuIngredient(
        menu_item_id=menu_item.id, inventory_item_id=inv_items["Chicken"].id, quantity_per_serving=0.3,
    ))
    db.add(models.MenuIngredient(
        menu_item_id=menu_item.id, inventory_item_id=inv_items["Rice"].id, quantity_per_serving=0.2,
    ))
    db.commit()

    print(f"Seeded {DB_PATH}")
    print(f"Restaurant: {restaurant.name} (id={restaurant.id})\n")
    print(f"{'email':<24} {'tier':<12} password")
    print("-" * 55)
    for email, _, staff_role in accounts:
        print(f"{email:<24} {staff_role.value:<12} {PASSWORD}")
finally:
    db.close()
