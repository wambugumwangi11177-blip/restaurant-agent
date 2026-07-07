"""
execution/seed_showcase_restaurant.py
───────────────────────────────────────
Turn the Lavy restaurant (restaurant_id=3) into a complete, CURRENT,
insight-rich enterprise showcase so every AI module demonstrates real ROI.

Why (2026-07-07): the AI-generated demo data left several gaps that made the
app look broken to a prospective enterprise customer:
  • Orders were dense through 2026-04 then stopped (2 straggler rows) — the
    sales page (wall-clock "today" filter) and every wall-clock metric showed 0.
  • Every menu item had an identical 62% margin — the pricing and profit
    engines correctly found nothing to recommend, so both showed 0 insights.
  • Reservations ended 2026-04-26 — the bookings page (upcoming) showed 0.
  • Inventory, labor, and supply-chain tables were completely empty — those
    three AI modules had nothing to analyse.

This script fixes all of that. It is IDEMPOTENT and SCOPED to restaurant_id=3:
each section guards itself so re-running is safe, and it only ever touches
this one restaurant's rows. Runs in a single transaction with before/after
integrity checks.

Sections:
  1. Shift orders (+completed_at) and reservations so the data ends TODAY.
  2. Vary menu-item margins so pricing/profit find real opportunities.
  3. Seed inventory items + stock movements (some low/critical).
  4. Seed staff + labor shifts for the last 30 days (some overtime).
  5. Seed suppliers + purchase orders (some overdue).
  6. Add upcoming reservations (today .. +14 days).

Run:  python execution/seed_showcase_restaurant.py
"""
import os
import sys
import random
from datetime import datetime, timedelta, time, date

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)

from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

from sqlalchemy import func
from database import SessionLocal
import models

RID = 3
random.seed(42)  # deterministic
TODAY = datetime.utcnow().replace(hour=20, minute=0, second=0, microsecond=0)


def log(msg):
    print(f"  {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. MAKE ORDERS + RESERVATIONS CURRENT
# ─────────────────────────────────────────────────────────────────────────────
def make_data_current(db):
    print("\n[1] Making orders + reservations current")

    # Find the last DENSE day (>= 50 orders) — the straggler tail sits after it.
    dense = (
        db.query(func.date(models.Order.created_at).label("d"), func.count(models.Order.id).label("c"))
        .filter(models.Order.restaurant_id == RID)
        .group_by("d")
        .having(func.count(models.Order.id) >= 50)
        .order_by(func.date(models.Order.created_at).desc())
        .first()
    )
    if not dense:
        log("No dense order history found — skipping shift.")
        return

    dense_max = dense.d if isinstance(dense.d, date) else datetime.strptime(str(dense.d), "%Y-%m-%d").date()
    log(f"Last dense order day: {dense_max}")

    # Delete straggler orders after the dense tail (their order_items cascade).
    stragglers = (
        db.query(models.Order)
        .filter(models.Order.restaurant_id == RID, func.date(models.Order.created_at) > dense_max)
        .all()
    )
    for o in stragglers:
        db.delete(o)
    log(f"Deleted {len(stragglers)} straggler order(s) after the dense tail.")

    shift_days = (TODAY.date() - dense_max).days
    if shift_days <= 0:
        log("Data already current — no shift needed.")
    else:
        delta = timedelta(days=shift_days)
        log(f"Shifting all orders + reservations forward by {shift_days} days so data ends today.")
        dialect = db.bind.dialect.name
        if dialect == "postgresql":
            # One server-side UPDATE — fast for 100k+ rows over the network,
            # instead of round-tripping every row. `make_interval` is standard
            # Postgres; this path is Postgres-only because the same expression
            # corrupts SQLite's string-stored datetimes.
            from sqlalchemy import text
            db.execute(
                text(
                    "UPDATE orders "
                    "SET created_at = created_at + make_interval(days => :d), "
                    "    completed_at = completed_at + make_interval(days => :d) "
                    "WHERE restaurant_id = :rid"
                ),
                {"d": shift_days, "rid": RID},
            )
        else:
            # SQLite (local tests): shift in Python via bulk_update_mappings.
            rows = (
                db.query(models.Order.id, models.Order.created_at, models.Order.completed_at)
                .filter(models.Order.restaurant_id == RID)
                .all()
            )
            db.bulk_update_mappings(models.Order, [
                {
                    "id": r.id,
                    "created_at": (r.created_at + delta) if r.created_at else None,
                    "completed_at": (r.completed_at + delta) if r.completed_at else None,
                }
                for r in rows
            ])
        # Reservations are Date/Time; shift the date component (both dialects).
        for r in db.query(models.Reservation).filter(models.Reservation.restaurant_id == RID).all():
            if r.reservation_date:
                r.reservation_date = r.reservation_date + delta
    db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# 2. VARY MENU MARGINS  (unlock pricing + profit insights)
# ─────────────────────────────────────────────────────────────────────────────
def vary_menu_margins(db):
    print("\n[2] Varying menu-item margins")
    items = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == RID).order_by(models.MenuItem.id).all()
    if not items:
        log("No menu items — skipping.")
        return

    # Deterministic spread tuned for a CREDIBLE enterprise demo — a healthy,
    # thriving restaurant with clear optimisation upside, not one in crisis.
    # ~12% modestly below the 40% margin floor (real REPRICE/profit-leak
    # targets, but 33-39% margin so blended food cost stays realistic ~33-35%,
    # not "CRITICAL"), ~58% healthy, ~30% high-margin (puzzles/stars). Based on
    # id bucket so re-running is stable.
    below = healthy = high = 0
    for i, item in enumerate(items):
        if not item.price:
            continue
        bucket = i % 100
        if bucket < 12:         # 12% — modestly undermargin: triggers REPRICE + leak
            margin = random.uniform(0.33, 0.39)
            below += 1
        elif bucket < 70:       # 58% — healthy
            margin = random.uniform(0.58, 0.68)
            healthy += 1
        else:                   # 30% — high margin (puzzles if low velocity)
            margin = random.uniform(0.68, 0.80)
            high += 1
        item.cost_price = int(round(item.price * (1 - margin)))
    db.flush()
    log(f"Set margins: {below} undermargin (<40%), {healthy} healthy, {high} high-margin.")


# ─────────────────────────────────────────────────────────────────────────────
# 3. INVENTORY + STOCK MOVEMENTS
# ─────────────────────────────────────────────────────────────────────────────
INVENTORY = [
    # name, unit, cost_per_unit(cents), low_threshold, expiry_days, stock_ratio (qty/threshold)
    ("Chicken", "kg", 4500, 20, 3, 0.35),      # low + short shelf life -> critical/spoilage
    ("Beef", "kg", 6800, 15, 4, 0.8),
    ("Goat Meat", "kg", 7200, 12, 4, 0.5),
    ("Rice (Basmati)", "kg", 1800, 50, 180, 2.5),
    ("Cooking Oil", "L", 3200, 20, 120, 1.2),
    ("Tomatoes", "kg", 900, 25, 5, 0.3),        # low + short shelf life
    ("Onions", "kg", 700, 30, 20, 1.8),
    ("Potatoes", "kg", 600, 40, 30, 2.0),
    ("Wheat Flour", "kg", 1100, 40, 150, 1.5),
    ("Milk", "L", 800, 30, 5, 0.6),
    ("Cheese", "kg", 5500, 8, 21, 1.0),
    ("Butter", "kg", 4800, 6, 30, 1.3),
    ("Eggs", "tray", 4000, 15, 21, 0.9),
    ("Passion Fruit", "kg", 2500, 10, 7, 0.25), # low + short shelf life
    ("Mango", "kg", 1500, 12, 7, 0.7),
    ("Coffee Beans", "kg", 6000, 5, 200, 2.2),
    ("Sugar", "kg", 1300, 30, 365, 2.0),
    ("Salt", "kg", 400, 10, 730, 3.0),
    ("Fish (Tilapia)", "kg", 5000, 10, 3, 0.4),
    ("Prawns", "kg", 9500, 6, 3, 0.5),
    ("Lettuce", "kg", 1200, 12, 5, 0.35),
    ("Bell Peppers", "kg", 1800, 10, 8, 0.6),
    ("Garlic", "kg", 3000, 6, 30, 1.4),
    ("Ginger", "kg", 2800, 5, 30, 1.1),
    ("Coconut Milk", "L", 2200, 15, 90, 1.6),
    ("Pasta", "kg", 1600, 25, 300, 1.9),
    ("Beef Sausages", "kg", 5200, 8, 14, 0.7),
    ("Bacon", "kg", 6500, 6, 14, 0.5),
    ("Bread", "loaf", 600, 20, 4, 0.8),
    ("Soda (assorted)", "crate", 8000, 10, 180, 1.5),
]


def seed_inventory(db):
    print("\n[3] Seeding inventory + stock movements")
    existing = db.query(func.count(models.InventoryItem.id)).filter(models.InventoryItem.restaurant_id == RID).scalar()
    if existing:
        log(f"Inventory already has {existing} items — skipping.")
        return

    created_items = []
    for name, unit, cost, thresh, expiry, ratio in INVENTORY:
        qty = round(thresh * ratio, 1)
        it = models.InventoryItem(
            restaurant_id=RID, item_name=name, quantity=qty, unit=unit,
            cost_per_unit=cost, low_stock_threshold=thresh, expiry_days=expiry,
        )
        db.add(it)
        created_items.append((it, thresh))
    db.flush()

    # Stock movements over the last 30 days: a weekly restock (IN) + daily
    # usage (OUT) so the depletion/velocity engine has a real consumption trend.
    move_count = 0
    for it, thresh in created_items:
        daily_use = max(thresh * 0.12, 0.5)
        for d in range(30, 0, -1):
            day = TODAY - timedelta(days=d)
            if d % 7 == 0:  # weekly restock
                db.add(models.StockMovement(
                    inventory_item_id=it.id, movement_type=models.StockMovementType.IN,
                    quantity=round(thresh * 1.5, 1), reason="purchase", created_at=day,
                ))
                move_count += 1
            db.add(models.StockMovement(
                inventory_item_id=it.id, movement_type=models.StockMovementType.OUT,
                quantity=round(daily_use * random.uniform(0.7, 1.3), 1), reason="sale", created_at=day,
            ))
            move_count += 1
    db.flush()
    log(f"Created {len(created_items)} inventory items + {move_count} stock movements.")


# ─────────────────────────────────────────────────────────────────────────────
# 4. LABOR — STAFF + SHIFTS
# ─────────────────────────────────────────────────────────────────────────────
# Roster sized for an enterprise restaurant doing ~KES 500k/day: a real
# operation this size runs ~40 staff, which lands labor cost at the industry-
# standard ~25-30% of revenue. (Too few staff made labor read an implausible
# ~5%.) name, role, hourly_rate(cents).
STAFF = (
    [("Head Chef", 90000)] + [("Sous Chef", 65000)] * 2 + [("Line Cook", 45000)] * 8 +
    [("Prep Cook", 38000)] * 4 + [("Waiter", 35000)] * 12 + [("Cashier", 38000)] * 3 +
    [("Host", 33000)] * 2 + [("Bartender", 42000)] * 2 + [("Dishwasher", 28000)] * 3 +
    [("Cleaner", 28000)] * 2 + [("Shift Manager", 60000)] * 2
)
_FIRST = ["James", "Mary", "Peter", "Grace", "David", "Susan", "Brian", "Faith", "Samuel",
          "Ann", "Kevin", "Lucy", "Paul", "Nancy", "Dennis", "Ruth", "Victor", "Mercy",
          "John", "Esther", "Michael", "Joyce", "Daniel", "Caroline", "Stephen", "Winnie",
          "George", "Beatrice", "Anthony", "Rose", "Charles", "Jane", "Patrick", "Alice",
          "Simon", "Diana", "Francis", "Mercy", "Eric", "Sharon"]
_LAST = ["Kariuki", "Wanjiru", "Otieno", "Achieng", "Mwangi", "Njeri", "Kiprop", "Mueni",
         "Barasa", "Kamau", "Mutua", "Chebet", "Wafula", "Kilonzo", "Omondi", "Cheruiyot"]


def seed_labor(db):
    print("\n[4] Seeding staff + labor shifts")
    existing = db.query(models.StaffMember).filter(models.StaffMember.restaurant_id == RID).all()
    if len(existing) >= 30:
        log(f"Staff already sized ({len(existing)}) — skipping.")
        return
    if existing:
        # Replace an undersized earlier seed: clear shifts then staff (FK order).
        db.query(models.LaborShift).filter(models.LaborShift.restaurant_id == RID).delete(synchronize_session=False)
        for s in existing:
            db.delete(s)
        db.flush()
        log(f"Cleared {len(existing)} undersized staff to re-seed a realistic roster.")

    staff = []
    for i, (title, rate) in enumerate(STAFF):
        name = f"{_FIRST[i % len(_FIRST)]} {_LAST[i % len(_LAST)]}"
        s = models.StaffMember(restaurant_id=RID, name=name, role_title=title, hourly_rate=rate, is_active=True)
        db.add(s)
        staff.append(s)
    db.flush()

    shift_count = 0
    for d in range(30, 0, -1):
        day = (TODAY - timedelta(days=d)).date()
        # ~80% of staff work each day
        working = random.sample(staff, k=int(len(staff) * 0.8))
        for s in working:
            # Most shifts 8h; ~25% run 9-10h (overtime > 8h)
            hours = random.choice([8, 8, 8, 9, 9, 10])
            start = datetime.combine(day, time(10, 0))
            end = start + timedelta(hours=hours)
            cost = int(round(hours * s.hourly_rate))
            db.add(models.LaborShift(
                restaurant_id=RID, staff_member_id=s.id, shift_date=day,
                scheduled_start=start, scheduled_end=start + timedelta(hours=8),
                actual_start=start, actual_end=end,
                scheduled_hours=8.0, actual_hours=float(hours), labor_cost=cost,
            ))
            shift_count += 1
    db.flush()
    log(f"Created {len(staff)} staff + {shift_count} shifts (last 30 days, with overtime).")


# ─────────────────────────────────────────────────────────────────────────────
# 5. SUPPLIERS + PURCHASE ORDERS
# ─────────────────────────────────────────────────────────────────────────────
SUPPLIERS = [
    ("Fresh Farms Produce", 1.0, 92.0),
    ("Nairobi Meats Ltd", 2.0, 78.0),      # less reliable
    ("Dairy Direct", 1.0, 96.0),
    ("Grain & Staples Co", 3.0, 88.0),
    ("Coastal Seafood", 2.0, 70.0),        # least reliable
]


def seed_suppliers(db):
    print("\n[5] Seeding suppliers + purchase orders")
    existing = db.query(func.count(models.Supplier.id)).filter(models.Supplier.restaurant_id == RID).scalar()
    if existing:
        log(f"Suppliers already seeded ({existing}) — skipping.")
        return

    suppliers = []
    for name, lead, rel in SUPPLIERS:
        sup = models.Supplier(restaurant_id=RID, name=name, avg_lead_days=lead,
                              reliability_score=rel, is_active=True)
        db.add(sup)
        suppliers.append(sup)
    db.flush()

    inv_items = db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == RID).all()
    po_count = 0
    for d in range(60, 0, -3):
        sup = random.choice(suppliers)
        item = random.choice(inv_items) if inv_items else None
        ordered = TODAY - timedelta(days=d)
        expected = ordered + timedelta(days=sup.avg_lead_days)
        qty = round(random.uniform(10, 60), 1)
        cost = item.cost_per_unit if item else 2000
        # Reliability-driven: reliable suppliers mostly on-time; unreliable often late.
        on_time = random.random() < (sup.reliability_score / 100.0)
        po = models.PurchaseOrder(
            restaurant_id=RID, supplier_id=sup.id,
            inventory_item_id=item.id if item else None,
            quantity_ordered=qty, quantity_received=qty, unit=item.unit if item else "kg",
            cost_per_unit=int(cost), total_cost=int(cost * qty),
            status="DELIVERED", ordered_at=ordered, expected_at=expected,
            delivered_at=expected + (timedelta(days=0) if on_time else timedelta(days=random.randint(1, 4))),
        )
        db.add(po)
        po_count += 1

    # A few currently-open, overdue POs -> supply-chain overdue alerts.
    for _ in range(3):
        sup = random.choice(suppliers)
        item = random.choice(inv_items) if inv_items else None
        ordered = TODAY - timedelta(days=random.randint(4, 8))
        expected = ordered + timedelta(days=sup.avg_lead_days)  # already in the past
        qty = round(random.uniform(10, 40), 1)
        cost = item.cost_per_unit if item else 2000
        db.add(models.PurchaseOrder(
            restaurant_id=RID, supplier_id=sup.id,
            inventory_item_id=item.id if item else None,
            quantity_ordered=qty, unit=item.unit if item else "kg",
            cost_per_unit=int(cost), total_cost=int(cost * qty),
            status="SENT", ordered_at=ordered, expected_at=expected,
        ))
        po_count += 1
    db.flush()
    log(f"Created {len(suppliers)} suppliers + {po_count} purchase orders (incl. 3 overdue).")


# ─────────────────────────────────────────────────────────────────────────────
# 6. UPCOMING RESERVATIONS
# ─────────────────────────────────────────────────────────────────────────────
FIRST_NAMES = ["Aisha", "Brian", "Grace", "David", "Faith", "Samuel", "Mercy", "John",
               "Lucy", "Kevin", "Nancy", "Paul", "Ann", "Dennis", "Ruth", "Victor"]
LAST_NAMES = ["Mohamed", "Mwangi", "Wambui", "Otieno", "Njeri", "Barasa", "Kamau",
              "Achieng", "Mutua", "Chebet", "Wafula", "Kilonzo"]


def seed_upcoming_reservations(db):
    print("\n[6] Seeding upcoming reservations")
    upcoming = (
        db.query(func.count(models.Reservation.id))
        .filter(models.Reservation.restaurant_id == RID,
                models.Reservation.reservation_date >= TODAY.date())
        .scalar()
    )
    if upcoming and upcoming >= 15:
        log(f"Already {upcoming} upcoming reservations — skipping.")
        return

    tables = db.query(models.Table).filter(models.Table.restaurant_id == RID).all()
    slots = [time(12, 0), time(13, 0), time(18, 30), time(19, 0), time(19, 30), time(20, 0), time(20, 30)]
    made = 0
    for d in range(0, 15):
        day = (TODAY + timedelta(days=d)).date()
        for _ in range(random.randint(2, 5)):
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            db.add(models.Reservation(
                restaurant_id=RID,
                table_id=random.choice(tables).id if tables else None,
                customer_name=name,
                customer_phone=f"+2547{random.randint(10000000, 99999999)}",
                party_size=random.choice([2, 2, 3, 4, 4, 6, 8]),
                reservation_date=day,
                reservation_time=random.choice(slots),
                duration_minutes=90,
                status=models.ReservationStatus.CONFIRMED,
                deposit_paid=random.random() < 0.4,
            ))
            made += 1
    db.flush()
    log(f"Created {made} upcoming reservations (today .. +14 days).")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    db = SessionLocal()
    try:
        print("=" * 64)
        print(f"SHOWCASE SEED — restaurant_id={RID}  (now={TODAY})")
        print("=" * 64)

        before_orders = db.query(func.count(models.Order.id)).filter(models.Order.restaurant_id == RID).scalar()

        make_data_current(db)
        vary_menu_margins(db)
        seed_inventory(db)
        seed_labor(db)
        seed_suppliers(db)
        seed_upcoming_reservations(db)

        after_orders = db.query(func.count(models.Order.id)).filter(models.Order.restaurant_id == RID).scalar()
        new_max = db.query(func.max(models.Order.created_at)).filter(models.Order.restaurant_id == RID).scalar()

        print("\n" + "-" * 64)
        print(f"Orders: {before_orders} -> {after_orders}  (delta = stragglers removed)")
        print(f"New latest order date: {new_max}")
        print("Committing...")
        db.commit()
        print("[OK] Committed.")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Rolled back: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
