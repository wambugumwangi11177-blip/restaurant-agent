"""
execution/smooth_recent_and_finalize.py
──────────────────────────────────────────
Fast, ADDITIVE final pass for the Lavy showcase (restaurant_id=3):

  1. Smooth the recent revenue trend by TOPPING UP low days in the last N days
     to a healthy weekday/weekend baseline with a gentle upward trend. Purely
     additive (INSERTs only) — deliberately no bulk DELETE, because deleting
     thousands of rows across the unindexed order_items (200k+) and prep_times
     (269k) tables seq-scans and hangs over the network. This removes the deep
     dips that made revenue WoW read -28% (health ~25) without touching
     existing rows.
  2. Apply expiry-aware inventory levels so only a handful of items show
     restock/spoilage alerts (not a wall of red).

Scoped to restaurant_id=3. Re-runnable: it only tops days UP to the baseline,
so a second run adds little/nothing.

Run:  python execution/smooth_recent_and_finalize.py
"""
import os
import sys
import random
from datetime import datetime, timedelta, time

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)
from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

from sqlalchemy import func
from database import SessionLocal
import models

from _guard import require_destructive_confirmation

RID = 3
SMOOTH_DAYS = 16
random.seed(99)
NOW = datetime.utcnow()
TODAY = NOW.date()

HOUR_WEIGHTS = {11: 3, 12: 8, 13: 9, 14: 6, 15: 3, 16: 3, 17: 5, 18: 9, 19: 11, 20: 10, 21: 6, 22: 2}
HOURS, HOUR_W = list(HOUR_WEIGHTS.keys()), list(HOUR_WEIGHTS.values())


def smooth_recent(db):
    print(f"[1] Smoothing recent {SMOOTH_DAYS} days (additive top-up)")
    menu = db.query(models.MenuItem).filter(
        models.MenuItem.restaurant_id == RID, models.MenuItem.is_available == True
    ).all()
    pop = [random.random() ** 2 for _ in menu]

    pm = [models.PaymentMethod.MPESA] * 60 + [models.PaymentMethod.CASH] * 25 + [models.PaymentMethod.CARD] * 15
    ch = ([models.DeliveryChannel.WALK_IN] * 55 + [models.DeliveryChannel.APP] * 20 +
          [models.DeliveryChannel.UBER_EATS] * 12 + [models.DeliveryChannel.BOLT_FOOD] * 8 + [models.DeliveryChannel.GLOVO] * 5)
    ot = [models.OrderType.DINE_IN] * 60 + [models.OrderType.TAKEOUT] * 25 + [models.OrderType.DELIVERY] * 15

    new_orders = []
    for d in range(SMOOTH_DAYS, -1, -1):
        day = TODAY - timedelta(days=d)
        dow = day.weekday()
        trend = 1 + (SMOOTH_DAYS - d) * 0.004          # gentle upward trend toward today
        target = int((250 if dow >= 4 else 190) * trend)
        existing = db.query(func.count(models.Order.id)).filter(
            models.Order.restaurant_id == RID, func.date(models.Order.created_at) == day
        ).scalar() or 0
        need = target - existing
        if need <= 0:
            continue
        for _ in range(need):
            hour = random.choices(HOURS, weights=HOUR_W)[0]
            created = datetime.combine(day, time(hour, random.randint(0, 59), random.randint(0, 59)))
            if created > NOW:
                created = NOW - timedelta(minutes=random.randint(1, 120))
            new_orders.append(models.Order(
                restaurant_id=RID, status=models.OrderStatus.SERVED,
                order_type=random.choice(ot), delivery_channel=random.choice(ch),
                payment_method=random.choice(pm), is_paid=True, total=0,
                created_at=created, completed_at=created + timedelta(minutes=random.randint(12, 45)),
            ))
    if not new_orders:
        print("   Recent days already healthy — nothing to add.")
        return
    db.add_all(new_orders)
    db.flush()

    oi_maps, totals, pt_maps = [], [], []
    mi_by = {m.id: m for m in menu}
    cutoff30 = TODAY - timedelta(days=30)
    for o in new_orders:
        n = random.choices([1, 2, 3, 4], weights=[35, 35, 20, 10])[0]
        total = 0
        for mi in random.choices(menu, weights=pop, k=n):
            qty = random.choices([1, 2, 3], weights=[70, 22, 8])[0]
            oi_maps.append({"order_id": o.id, "menu_item_id": mi.id, "quantity": qty, "unit_price": mi.price})
            total += mi.price * qty
        totals.append({"id": o.id, "total": total})
    db.bulk_insert_mappings(models.OrderItem, oi_maps)
    db.bulk_update_mappings(models.Order, totals)
    db.flush()

    # prep-times for the added recent items (KDS signal), last 30 days only
    added_oi = (
        db.query(models.OrderItem.id, models.OrderItem.menu_item_id, models.Order.created_at)
        .join(models.Order, models.Order.id == models.OrderItem.order_id)
        .filter(models.Order.restaurant_id == RID, models.Order.created_at >= datetime.combine(cutoff30, time.min),
                models.Order.id.in_([o.id for o in new_orders]))
        .all()
    )
    for oi_id, mi_id, created in added_oi:
        mi = mi_by.get(mi_id)
        base = mi.avg_prep_minutes if mi and mi.avg_prep_minutes else 10.0
        actual = round(max(2.0, random.gauss(base, base * 0.25)), 1)
        pt_maps.append({"order_item_id": oi_id, "station": mi.prep_station if mi else "main",
                        "started_at": created, "completed_at": created + timedelta(minutes=actual),
                        "actual_minutes": actual})
    db.bulk_insert_mappings(models.PrepTime, pt_maps)
    db.flush()
    print(f"   Added {len(new_orders)} orders, {len(oi_maps)} items, {len(pt_maps)} prep-times to fill dips.")


KEEP_LOW = {"Chicken", "Tomatoes", "Passion Fruit", "Fish (Tilapia)", "Prawns"}


def fix_inventory(db):
    print("[2] Expiry-aware inventory levels")
    items = db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == RID).all()
    low = 0
    for it in items:
        thr = it.low_stock_threshold or 10
        expiry = it.expiry_days or 30
        if it.item_name in KEEP_LOW:
            it.quantity = round(thr * random.uniform(0.3, 0.6), 1); low += 1
        elif expiry <= 8:
            it.quantity = round(thr * random.uniform(1.0, 1.25), 1)
        else:
            it.quantity = round(thr * random.uniform(1.6, 2.4), 1)
    print(f"   {low} items low (alerts), {len(items)-low} restocked healthy.")


def main():
    require_destructive_confirmation(
        f"INSERTs synthetic orders across the last {SMOOTH_DAYS} days and OVERWRITES "
        f"every inventory quantity for restaurant_id={RID} (the order inserts are "
        f"additive, but the inventory overwrite destroys real stock levels)"
    )
    db = SessionLocal()
    try:
        smooth_recent(db)
        fix_inventory(db)
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
