"""
Demo Seed Data Generator
Generates 30 days of realistic restaurant data so the AI Intelligence Engine
has meaningful patterns to analyze and display.
"""
import sys
import os
import random
from datetime import datetime, timedelta, time, date

# Add backend to path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, backend_dir)

from sqlalchemy.orm import Session
from database import SessionLocal, engine
from models import (
    Base, Tenant, User, Restaurant, MenuItem, Order, OrderItem,
    Table, Reservation, InventoryItem, StockMovement, PrepTime,
    OrderStatus, OrderType, TableStatus, ReservationStatus, StockMovementType, Role
)
from auth import get_password_hash


def seed():
    db = SessionLocal()
    try:
        print("🧹 Clearing existing data...")
        # Drop and recreate all tables
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        # ── TENANT & USER ──
        print("👤 Creating tenant and admin user...")
        tenant = Tenant(name="Leviii Demo Restaurant", plan="premium")
        db.add(tenant)
        db.flush()

        admin = User(
            tenant_id=tenant.id,
            email="admin@leviii.ai",
            hashed_password=get_password_hash("admin123"),
            role=Role.ADMIN,
        )
        db.add(admin)
        db.flush()

        # ── RESTAURANT ──
        restaurant = Restaurant(
            tenant_id=tenant.id,
            name="Leviii Kitchen",
            address="Nairobi, Kenya"
        )
        db.add(restaurant)
        db.flush()
        rid = restaurant.id

        # ── TABLES ──
        print("🪑 Creating tables...")
        tables = []
        for i in range(1, 13):
            cap = random.choice([2, 4, 4, 6, 6, 8])
            t = Table(restaurant_id=rid, table_number=i, capacity=cap, status=TableStatus.AVAILABLE)
            db.add(t)
            tables.append(t)
        db.flush()

        # ── MENU ITEMS ──
        print("🍽️  Creating menu items...")
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

        # ── INVENTORY ──
        print("📦 Creating inventory items...")
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

        # ── GENERATE 30 DAYS OF ORDERS ──
        print("📊 Generating 30 days of order history...")
        today = datetime.utcnow()
        total_orders = 0

        for day_offset in range(30, 0, -1):
            order_date = today - timedelta(days=day_offset)
            weekday = order_date.weekday()

            # More orders on weekends
            if weekday >= 5:  # Saturday/Sunday
                num_orders = random.randint(25, 45)
            elif weekday == 4:  # Friday
                num_orders = random.randint(20, 35)
            else:
                num_orders = random.randint(10, 25)

            for _ in range(num_orders):
                # Random time: lunch (11-14) or dinner (18-22)
                if random.random() < 0.4:
                    hour = random.randint(11, 14)
                else:
                    hour = random.randint(18, 22)
                minute = random.randint(0, 59)
                order_time = order_date.replace(hour=hour, minute=minute, second=0)

                order_type = random.choices(
                    [OrderType.DINE_IN, OrderType.TAKEOUT, OrderType.DELIVERY],
                    weights=[60, 25, 15]
                )[0]

                # Pick random items for the order (1-5 items)
                num_items = random.randint(1, 5)
                selected = random.sample(menu_items, min(num_items, len(menu_items)))
                total = 0

                order = Order(
                    restaurant_id=rid,
                    status=random.choices(
                        [OrderStatus.SERVED, OrderStatus.SERVED, OrderStatus.SERVED, OrderStatus.CANCELLED],
                        weights=[70, 15, 10, 5]
                    )[0],
                    order_type=order_type,
                    table_number=random.randint(1, 12) if order_type == OrderType.DINE_IN else None,
                    customer_name=f"Customer_{random.randint(100, 999)}",
                    total=0,
                    created_at=order_time,
                    completed_at=order_time + timedelta(minutes=random.randint(15, 45)) if order_type != OrderType.DELIVERY else None,
                )
                db.add(order)
                db.flush()

                for item in selected:
                    qty = random.randint(1, 3)
                    oi = OrderItem(
                        order_id=order.id,
                        menu_item_id=item.id,
                        quantity=qty,
                        unit_price=item.price,
                    )
                    db.add(oi)
                    db.flush()
                    total += qty * item.price

                    # Add prep time tracking
                    actual_prep = item.avg_prep_minutes + random.uniform(-3, 5)
                    pt = PrepTime(
                        order_item_id=oi.id,
                        station=item.prep_station,
                        started_at=order_time,
                        completed_at=order_time + timedelta(minutes=actual_prep),
                        actual_minutes=round(actual_prep, 1),
                    )
                    db.add(pt)

                order.total = total
                total_orders += 1

        # ── STOCK MOVEMENTS ──
        print("📦 Generating stock movements...")
        for day_offset in range(30, 0, -1):
            move_date = today - timedelta(days=day_offset)
            for inv in inv_items:
                # Daily usage (OUT)
                daily_use = random.uniform(0.5, 3.0)
                db.add(StockMovement(
                    inventory_item_id=inv.id,
                    movement_type=StockMovementType.OUT,
                    quantity=round(daily_use, 1),
                    reason="sale",
                    created_at=move_date,
                ))
                # Weekly restock (IN) on Mondays
                if move_date.weekday() == 0:
                    restock = random.uniform(10, 25)
                    db.add(StockMovement(
                        inventory_item_id=inv.id,
                        movement_type=StockMovementType.IN,
                        quantity=round(restock, 1),
                        reason="purchase",
                        created_at=move_date,
                    ))

        # ── RESERVATIONS ──
        print("📅 Generating reservations...")
        for day_offset in range(30, 0, -1):
            res_date = (today - timedelta(days=day_offset)).date()
            num_res = random.randint(3, 10)

            for _ in range(num_res):
                res_time = time(hour=random.choice([12, 13, 18, 19, 20]), minute=random.choice([0, 30]))
                party = random.randint(2, 8)
                table = random.choice(tables)
                deposit = random.random() < 0.3

                status = random.choices(
                    [ReservationStatus.COMPLETED, ReservationStatus.NO_SHOW, ReservationStatus.CANCELLED],
                    weights=[75, 15, 10]
                )[0]

                db.add(Reservation(
                    restaurant_id=rid,
                    table_id=table.id,
                    customer_name=f"Guest_{random.randint(100, 999)}",
                    customer_phone=f"+2547{random.randint(10000000, 99999999)}",
                    party_size=party,
                    reservation_date=res_date,
                    reservation_time=res_time,
                    duration_minutes=random.choice([60, 90, 120]),
                    status=status,
                    deposit_paid=deposit,
                ))

        db.commit()
        print(f"\n✅ Seed complete!")
        print(f"   📊 {total_orders} orders generated")
        print(f"   🍽️  {len(menu_items)} menu items")
        print(f"   📦 {len(inv_items)} inventory items")
        print(f"   📅 ~{30 * 6} reservations")
        print(f"\n   Login with: admin@leviii.ai / admin123")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
