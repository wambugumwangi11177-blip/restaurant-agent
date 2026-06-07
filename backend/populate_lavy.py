import sys
import os
import random
from datetime import datetime, timedelta, time, date

# Add backend to path if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database import SessionLocal
from models import (
    Tenant, User, Restaurant, MenuItem, Order, OrderItem,
    Table, Reservation, InventoryItem, StockMovement, PrepTime,
    OrderStatus, OrderType, TableStatus, ReservationStatus, StockMovementType, Role
)
from auth import get_password_hash

def populate_lavy():
    db = SessionLocal()
    try:
        print("[INFO] Checking for existing Lavy tenant...")
        existing_tenant = db.query(Tenant).filter(Tenant.name.ilike("%Lavy%")).first()
        
        if existing_tenant:
            print("[WARN] Tenant 'Lavy' already exists. Deleting to regenerate data...")
            # For a clean slate on regeneration, but usually we just skip.
            # To be safe, we won't delete, we'll just use a unique name.
            tenant = existing_tenant
            db.query(User).filter(User.tenant_id == tenant.id).delete()
            db.query(Restaurant).filter(Restaurant.tenant_id == tenant.id).delete()
            db.commit()
        else:
            print("[INFO] Creating 'Lavy' tenant...")
            tenant = Tenant(name="Lavy", plan="premium")
            db.add(tenant)
            db.commit()

        # Admin user
        admin = User(
            tenant_id=tenant.id,
            email="lavy@leviii.ai",
            hashed_password=get_password_hash("lavy123"),
            role=Role.ADMIN,
        )
        db.add(admin)
        db.commit()

        # Restaurant
        print("[INFO] Creating Lavy Restaurant...")
        restaurant = Restaurant(
            tenant_id=tenant.id,
            name="Lavy Restaurant",
            address="Westlands, Nairobi"
        )
        db.add(restaurant)
        db.commit()
        rid = restaurant.id

        # Tables
        print("[INFO] Creating tables...")
        tables = []
        for i in range(1, 15):
            cap = random.choice([2, 4, 4, 6, 8, 10])
            t = Table(restaurant_id=rid, table_number=i, capacity=cap, status=TableStatus.AVAILABLE)
            db.add(t)
            tables.append(t)
        db.commit()

        # Menu Items (based on Lavy demo data + typical Kenyan menu)
        print("[INFO] Creating menu items...")
        menu_data = [
            ("Goat Mandi", 1800, 700, "Main", "grill", 30),
            ("Sticky Wings", 1200, 400, "Main", "fryer", 15),
            ("Passion Mojito", 650, 150, "Beverages", "bar", 5),
            ("Nyama Choma (1kg)", 2500, 1000, "Main", "grill", 40),
            ("Chicken Tikka", 1100, 400, "Main", "grill", 20),
            ("Swahili Fish Curry", 1500, 600, "Main", "main", 25),
            ("Beef Samosas (3)", 450, 120, "Starters", "fryer", 10),
            ("Chapati", 100, 20, "Sides", "main", 5),
            ("Ugali", 150, 30, "Sides", "main", 8),
            ("Masala Chips", 400, 100, "Sides", "fryer", 12),
            ("Kachumbari", 200, 50, "Sides", "salad", 5),
            ("Tusker Lager", 400, 200, "Beverages", "bar", 1),
            ("Fresh Mango Juice", 350, 80, "Beverages", "bar", 4),
            ("Vanilla Milkshake", 500, 150, "Desserts", "bar", 5),
            ("Chocolate Brownie", 600, 200, "Desserts", "main", 5),
        ]

        menu_items = []
        for name, price, cost, cat, station, prep in menu_data:
            item = MenuItem(
                restaurant_id=rid,
                name=name,
                description=f"Signature {name.lower()}",
                price=price * 100,  # cents
                cost_price=cost * 100,
                category=cat,
                prep_station=station,
                avg_prep_minutes=float(prep),
                is_available=True,
            )
            db.add(item)
            menu_items.append(item)
        db.commit()

        # Inventory Items
        print("[INFO] Creating inventory items...")
        inventory_data = [
            ("Goat Meat", 80, "kg", 600, 15, 5),
            ("Chicken Wings", 50, "kg", 400, 10, 5),
            ("Passion Fruit", 20, "kg", 150, 5, 7),
            ("Mint Leaves", 2, "kg", 300, 0.5, 3),
            ("Fish Fillet", 30, "kg", 800, 5, 3),
            ("Potatoes", 100, "kg", 80, 20, 14),
            ("Wheat Flour", 50, "kg", 100, 10, 60),
            ("Cooking Oil", 40, "litres", 250, 10, 180),
            ("Tomatoes", 40, "kg", 100, 10, 5),
            ("Onions", 50, "kg", 80, 10, 14),
            ("Tusker Stock", 500, "bottles", 180, 50, 365),
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
        db.commit()

        # Generate 30 days of exhaustive order history
        print("[INFO] Generating 30 days of data for Lavy...")
        today = datetime.utcnow()
        total_orders = 0

        # Create orders and stock movements
        for day_offset in range(30, -1, -1):
            order_date = today - timedelta(days=day_offset)
            weekday = order_date.weekday()

            # Friday (4) and Saturday (5) are busiest for Lavy based on demo insight
            if weekday in [4, 5]:
                num_orders = random.randint(60, 90)
            elif weekday == 6: # Sunday
                num_orders = random.randint(50, 75)
            else:
                num_orders = random.randint(30, 55)

            for _ in range(num_orders):
                # Peak hours logic
                if random.random() < 0.3:
                    hour = random.randint(12, 14) # Lunch
                else:
                    hour = random.randint(18, 22) # Dinner
                minute = random.randint(0, 59)
                order_time = order_date.replace(hour=hour, minute=minute, second=0)

                order_type = random.choices(
                    [OrderType.DINE_IN, OrderType.TAKEOUT, OrderType.DELIVERY],
                    weights=[65, 20, 15]
                )[0]

                # Goat Mandi, Sticky Wings, Passion Mojito are top sellers
                num_items = random.randint(2, 6)
                
                total = 0
                order = Order(
                    restaurant_id=rid,
                    status=random.choices([OrderStatus.SERVED, OrderStatus.CANCELLED], weights=[90, 10])[0],
                    order_type=order_type,
                    table_number=random.randint(1, 14) if order_type == OrderType.DINE_IN else None,
                    customer_name=f"Guest_{random.randint(1000, 9999)}",
                    total=0,
                    created_at=order_time,
                    completed_at=order_time + timedelta(minutes=random.randint(20, 50)) if order_type != OrderType.DELIVERY else None,
                )
                db.add(order)
                db.flush()

                for _ in range(num_items):
                    # Weight top sellers higher
                    item = random.choices(
                        menu_items,
                        weights=[20, 18, 15] + [5]*(len(menu_items)-3)
                    )[0]
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

                    actual_prep = item.avg_prep_minutes + random.uniform(-4, 8)
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

            # Daily Stock Movements
            for inv in inv_items:
                daily_use = random.uniform(1.0, 5.0)
                db.add(StockMovement(
                    inventory_item_id=inv.id,
                    movement_type=StockMovementType.OUT,
                    quantity=round(daily_use, 1),
                    reason="sale",
                    created_at=order_date,
                ))
                # Restock every Monday
                if weekday == 0:
                    restock = random.uniform(20, 40)
                    db.add(StockMovement(
                        inventory_item_id=inv.id,
                        movement_type=StockMovementType.IN,
                        quantity=round(restock, 1),
                        reason="purchase",
                        created_at=order_date,
                    ))

            # Reservations
            num_res = random.randint(5, 15)
            for _ in range(num_res):
                res_time = time(hour=random.choice([18, 19, 20]), minute=random.choice([0, 30]))
                db.add(Reservation(
                    restaurant_id=rid,
                    table_id=random.choice(tables).id,
                    customer_name=f"Res_{random.randint(100, 999)}",
                    customer_phone=f"+2547{random.randint(10000000, 99999999)}",
                    party_size=random.randint(2, 8),
                    reservation_date=order_date.date(),
                    reservation_time=res_time,
                    duration_minutes=random.choice([90, 120]),
                    status=ReservationStatus.COMPLETED,
                    deposit_paid=True,
                ))

        db.commit()
        print(f"\n[SUCCESS] Lavy extensive data generated!")
        print(f"   Login: lavy@leviii.ai")
        print(f"   Password: lavy123")
        print(f"   Generated {total_orders} orders over 30 days.")
        
    except Exception as e:
        db.rollback()
        print(f"[ERROR] {e}")
    finally:
        db.close()

if __name__ == "__main__":
    populate_lavy()
