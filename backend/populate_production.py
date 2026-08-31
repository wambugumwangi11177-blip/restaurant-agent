"""
Production Sub-Account Population Script
Creates a specific "Leviii Client Demo" tenant and populates it with realistic data.
Does NOT drop tables. Safe to run in production.
"""
import sys
import os
import random

# backend is now the current directory

from sqlalchemy.orm import Session
from database import SessionLocal
from models import (
    Tenant, User, Restaurant, MenuItem,
    Table, InventoryItem,
    TableStatus, Role
)
from auth import get_password_hash
from seed_generators import generate_orders, generate_stock_movements, generate_reservations

def populate():
    db = SessionLocal()
    try:
        print("[INFO] Checking for existing Client Demo tenant...")
        existing_tenant = db.query(Tenant).filter(Tenant.name == "Leviii Client Demo").first()
        
        if existing_tenant:
            print("[WARN] Tenant 'Leviii Client Demo' already exists. Skipping creation to avoid duplicates.")
            return

        existing_user = db.query(User).filter(User.email == "client@leviii.ai").first()
        if existing_user:
            db.delete(existing_user)
            db.flush()

        # -- TENANT & USER --
        print("[INFO] Creating 'Leviii Client Demo' tenant and admin user...")
        tenant = Tenant(name="Leviii Client Demo", plan="premium")
        db.add(tenant)
        db.flush()

        # Never ship a guessable password for an ADMIN account: take it from the
        # environment, or generate a strong one-time value and print it once.
        admin_password = os.getenv("SEED_ADMIN_PASSWORD", "")
        if not admin_password:
            import secrets as _secrets
            admin_password = _secrets.token_urlsafe(16)
            print("[WARN] SEED_ADMIN_PASSWORD not set — generated a one-time admin password.")
        print(f"[INFO] Admin email: client@leviii.ai")
        print(f"[INFO] Admin password (store securely, shown once): {admin_password}")
        admin = User(
            tenant_id=tenant.id,
            email="client@leviii.ai",
            hashed_password=get_password_hash(admin_password),
            role=Role.ADMIN,
        )
        db.add(admin)
        db.flush()

        # -- RESTAURANT --
        print("[INFO] Creating Restaurant...")
        restaurant = Restaurant(
            tenant_id=tenant.id,
            name="Client Kitchen",
            address="Nairobi, Kenya"
        )
        db.add(restaurant)
        db.flush()
        rid = restaurant.id

        # -- TABLES --
        print("[INFO] Creating tables...")
        tables = []
        for i in range(1, 13):
            cap = random.choice([2, 4, 4, 6, 6, 8])
            t = Table(restaurant_id=rid, table_number=i, capacity=cap, status=TableStatus.AVAILABLE)
            db.add(t)
            tables.append(t)
        db.flush()

        # -- MENU ITEMS --
        print("[INFO] Creating menu items...")
        menu_data = [
            # (name, price_kes, cost_kes, category, station, prep_min)
            ("Nyama Choma", 1200, 450, "Main", "grill", 25),
            ("Chicken Tikka", 950, 350, "Main", "grill", 20),
            ("Grilled Fish", 1100, 500, "Main", "grill", 22),
            ("Beef Burger", 750, 280, "Main", "grill", 15),
            ("Caesar Salad", 550, 120, "Starters", "salad", 8),
            ("Spring Rolls", 450, 100, "Starters", "fryer", 10),
            ("Soup of the Day", 400, 80, "Starters", "main", 12),
            ("Chapati", 50, 15, "Sides", "main", 5),
            ("Ugali", 100, 20, "Sides", "main", 8),
            ("Pilau Rice", 350, 80, "Sides", "main", 15),
            ("French Fries", 300, 60, "Sides", "fryer", 10),
            ("Fruit Juice", 250, 50, "Beverages", "drinks", 3),
            ("Tusker Beer", 350, 180, "Beverages", "drinks", 1),
            ("Soda", 150, 60, "Beverages", "drinks", 1),
            ("Mocktail", 400, 80, "Beverages", "drinks", 5),
            ("Chocolate Cake", 500, 150, "Desserts", "main", 5),
            ("Ice Cream", 350, 100, "Desserts", "main", 3),
            ("Tiramisu", 600, 200, "Desserts", "main", 5),
        ]

        menu_items = []
        for name, price, cost, cat, station, prep in menu_data:
            item = MenuItem(
                restaurant_id=rid,
                name=name,
                description=f"Delicious {name.lower()} prepared fresh",
                price=price * 100,  # Store in cents
                cost_price=cost * 100,
                category=cat,
                prep_station=station,
                avg_prep_minutes=float(prep),
                is_available=True,
            )
            db.add(item)
            menu_items.append(item)
        db.flush()

        # -- INVENTORY --
        print("[INFO] Creating inventory items...")
        inventory_data = [
            ("Beef", 50, "kg", 800, 5, 7),
            ("Chicken", 40, "kg", 600, 5, 5),
            ("Fish", 30, "kg", 900, 5, 3),
            ("Rice", 100, "kg", 200, 10, 90),
            ("Flour", 80, "kg", 150, 10, 60),
            ("Cooking Oil", 50, "litres", 300, 5, 180),
            ("Tomatoes", 30, "kg", 100, 5, 5),
            ("Onions", 40, "kg", 80, 5, 14),
            ("Potatoes", 60, "kg", 120, 10, 21),
            ("Lettuce", 10, "heads", 50, 3, 4),
            ("Beer Stock", 200, "bottles", 180, 20, 365),
            ("Soda Stock", 300, "bottles", 60, 30, 365),
            ("Chocolate", 5, "kg", 1200, 2, 90),
            ("Ice Cream Base", 10, "litres", 500, 3, 30),
        ]

        inv_items = []
        for name, qty, unit, cost, threshold, expiry in inventory_data:
            inv = InventoryItem(
                restaurant_id=rid,
                item_name=name,
                quantity=qty,
                unit=unit,
                cost_per_unit=cost,
                low_stock_threshold=threshold,
                expiry_days=expiry,
            )
            db.add(inv)
            inv_items.append(inv)
        db.flush()

        # -- GENERATE 30 DAYS OF ORDERS (including today, clamped to now) --
        print("[INFO] Generating 30 days of order history...")
        total_orders = generate_orders(db, rid, menu_items, days=30, include_today=True)

        # -- STOCK MOVEMENTS --
        print("[INFO] Generating stock movements...")
        generate_stock_movements(db, inv_items, days=30, include_today=True)

        # -- RESERVATIONS --
        print("[INFO] Generating reservations...")
        generate_reservations(db, rid, tables, days=30, include_today=True)

        db.commit()
        print(f"\n[SUCCESS] Client Demo Seed complete!")
        print(f"   Tenant: Leviii Client Demo")
        print(f"   Login: client@leviii.ai (password printed above)")
        print(f"   {total_orders} orders generated")
        print(f"   {len(menu_items)} menu items")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    populate()
