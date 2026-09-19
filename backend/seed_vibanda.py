"""One-shot: seed Vibanda Village with restaurant, menu, inventory, staff,
tables, and today's transactional data (via seed_generators). Idempotent per run.
Usage: DATABASE_URL=<railway> python seed_vibanda.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, init_db
from models import (Tenant, User, Restaurant, MenuItem, InventoryItem, Table,
                    StaffMember, Role, StaffRole, TableStatus)
from auth import get_password_hash
from seed_generators import generate_orders, generate_stock_movements, generate_reservations
from time_utils import utcnow

init_db()
db = SessionLocal()
try:
    tenant = db.query(Tenant).filter(Tenant.name == "Vibanda Village").one()
    user = db.query(User).filter(User.tenant_id == tenant.id).first()
    existing = db.query(Restaurant).filter(Restaurant.tenant_id == tenant.id).first()
    if existing and db.query(MenuItem).filter(MenuItem.restaurant_id == existing.id).count() > 0:
        print("[SKIP] Restaurant already seeded"); raise SystemExit(0)
    r = existing or Restaurant(tenant_id=tenant.id, name="Vibanda Village",
                               address="Nairobi, Kenya",
                               owner_phone=user.phone if hasattr(user, "phone") else None)
    if not existing:
        db.add(r); db.flush()

    menu = [("Nyama Choma 1/4", 65000, 26000), ("Ugali & Sukuma", 25000, 8000),
            ("Grilled Chicken", 75000, 30000), ("Chapati Ndengu", 30000, 10000),
            ("Pilau Beef", 45000, 18000), ("Soda", 12000, 6000),
            ("Fresh Juice", 20000, 7000), ("Chai", 8000, 2000)]
    existing_menu = {m.name for m in db.query(MenuItem).filter(MenuItem.restaurant_id == r.id)}
    items = [MenuItem(restaurant_id=r.id, name=n, price=p, cost_price=c,
                      category="Food" if p >= 20000 else "Drinks", is_available=True)
             for n, p, c in menu if n not in existing_menu]
    db.add_all(items)
    if not items:
        items = list(db.query(MenuItem).filter(MenuItem.restaurant_id == r.id))
    db.flush()

    inv = [("Tomatoes", 8, "kg", 12000, 15), ("Beef", 12, "kg", 62000, 10),
           ("Chicken", 5, "kg", 45000, 8), ("Maize flour", 20, "kg", 9000, 10),
           ("Cooking oil", 6, "L", 28000, 5), ("Sukuma wiki", 4, "kg", 6000, 8)]
    existing_inv = {i.item_name for i in db.query(InventoryItem).filter(InventoryItem.restaurant_id == r.id)}
    db.add_all([InventoryItem(restaurant_id=r.id, item_name=n, quantity=q, unit=u,
                              cost_per_unit_cents=c, low_stock_threshold=t)
                for n, q, u, c, t in inv if n not in existing_inv])
    db.flush()

    existing_tables = {t.table_number for t in db.query(Table).filter(Table.restaurant_id == r.id)}
    db.add_all([Table(restaurant_id=r.id, table_number=i, capacity=4,
                      status=TableStatus.AVAILABLE) for i in range(1, 11) if i not in existing_tables])
    db.flush()

    staff = [("Chef Wanjiru", "Head Chef", 12000), ("Otieno", "Waiter", 6000),
             ("Achieng", "Cashier", 7000), ("Mutua", "Cook", 8000)]
    db.add_all([StaffMember(restaurant_id=r.id, name=n, role_title=rt, hourly_rate=hr)
                for n, rt, hr in staff])
    db.commit()

    n_orders = generate_orders(db, r.id, items, days=30, include_today=True)
    db.commit()
    n_res = generate_reservations(db, r.id, list(db.query(Table).filter(Table.restaurant_id == r.id)), days=30, include_today=True)
    db.commit()
    generate_stock_movements(db, list(db.query(InventoryItem).filter(InventoryItem.restaurant_id == r.id)), days=30, include_today=True)
    db.commit()
    print(f"[OK] Vibanda Village seeded: {len(items)} menu, {len(inv)} inventory, 10 tables, "
          f"{len(staff)} staff, {n_orders} orders (30d incl today), {n_res} reservations")
finally:
    db.close()
