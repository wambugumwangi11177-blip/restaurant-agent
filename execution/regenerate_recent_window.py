"""
execution/regenerate_recent_window.py
────────────────────────────────────────
Replace the most recent ~40 days of orders for the Lavy showcase
(restaurant_id=3) with a clean, realistic, HEALTHY pattern so the AI's
"last 30 days" analytics tell a credible enterprise story.

Why (2026-07-07): shifting the historical dataset forward landed a choppy,
declining tail in the recent window (a real dip that came from late-April
data), which read as a struggling restaurant (revenue WoW -28%, health ~25).
Every "last 30 days" analytic reads this window, so it's worth making it
pristine: steady weekday volume, weekend peaks, a gentle upward trend, and
prep-time records so the KDS module has data too. The 2+ years of history
BEFORE this window are left untouched for total-revenue context.

Scoped to restaurant_id=3. Regenerates deterministically (seeded), so it's
safe to re-run — it always clears the last WINDOW_DAYS days first.

Run:  python execution/regenerate_recent_window.py
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

RID = 3
WINDOW_DAYS = 40
random.seed(2026)
NOW = datetime.utcnow()
TODAY = NOW.date()

# Hour weights: lunch (12-14) and dinner (18-21) peaks over an 11:00-22:00 day.
HOUR_WEIGHTS = {11: 3, 12: 8, 13: 9, 14: 6, 15: 3, 16: 3, 17: 5, 18: 9, 19: 11, 20: 10, 21: 6, 22: 2}
HOURS = list(HOUR_WEIGHTS.keys())
HOUR_W = list(HOUR_WEIGHTS.values())


def main():
    db = SessionLocal()
    try:
        window_start = datetime.combine(TODAY - timedelta(days=WINDOW_DAYS), time.min)

        menu = db.query(models.MenuItem).filter(
            models.MenuItem.restaurant_id == RID, models.MenuItem.is_available == True
        ).all()
        if not menu:
            print("[ERROR] No menu items — aborting.")
            return
        # Popularity weights so some items are Stars and some are Dogs.
        pop = [random.random() ** 2 for _ in menu]  # skewed → a few big sellers

        # ── 1. Clear the recent window (prep_times → order_items → orders) ──
        old_orders = db.query(models.Order.id).filter(
            models.Order.restaurant_id == RID, models.Order.created_at >= window_start
        ).all()
        old_ids = [o.id for o in old_orders]
        print(f"Clearing {len(old_ids)} existing orders in the last {WINDOW_DAYS} days...")
        if old_ids:
            oi_ids = [r.id for r in db.query(models.OrderItem.id).filter(models.OrderItem.order_id.in_(old_ids)).all()]
            if oi_ids:
                db.query(models.PrepTime).filter(models.PrepTime.order_item_id.in_(oi_ids)).delete(synchronize_session=False)
            db.query(models.OrderItem).filter(models.OrderItem.order_id.in_(old_ids)).delete(synchronize_session=False)
            db.query(models.Order).filter(models.Order.id.in_(old_ids)).delete(synchronize_session=False)
            db.flush()

        # ── 2. Regenerate a clean, healthy pattern ──
        order_rows = []
        for d in range(WINDOW_DAYS, -1, -1):
            day = TODAY - timedelta(days=d)
            dow = day.weekday()  # 0=Mon
            base = 250 if dow >= 4 else 180          # Fri/Sat/Sun busier
            trend = 1 + (WINDOW_DAYS - d) * 0.0025    # ~10% gentle growth over window
            n_orders = int(base * trend * random.uniform(0.92, 1.08))
            for _ in range(n_orders):
                hour = random.choices(HOURS, weights=HOUR_W)[0]
                created = datetime.combine(day, time(hour, random.randint(0, 59), random.randint(0, 59)))
                if created > NOW:  # don't create future-timestamped orders today
                    created = NOW - timedelta(minutes=random.randint(1, 90))
                order_rows.append(created)

        print(f"Generating {len(order_rows)} orders across {WINDOW_DAYS+1} days...")

        # Insert orders first (need IDs for items). Build ORM objects in bulk.
        pm_choices = [models.PaymentMethod.MPESA] * 60 + [models.PaymentMethod.CASH] * 25 + [models.PaymentMethod.CARD] * 15
        ch_choices = ([models.DeliveryChannel.WALK_IN] * 55 + [models.DeliveryChannel.APP] * 20 +
                      [models.DeliveryChannel.UBER_EATS] * 12 + [models.DeliveryChannel.BOLT_FOOD] * 8 +
                      [models.DeliveryChannel.GLOVO] * 5)
        ot_choices = [models.OrderType.DINE_IN] * 60 + [models.OrderType.TAKEOUT] * 25 + [models.OrderType.DELIVERY] * 15

        orders = []
        for created in order_rows:
            o = models.Order(
                restaurant_id=RID, status=models.OrderStatus.SERVED,
                order_type=random.choice(ot_choices),
                delivery_channel=random.choice(ch_choices),
                payment_method=random.choice(pm_choices), is_paid=True,
                total=0, created_at=created,
                completed_at=created + timedelta(minutes=random.randint(12, 45)),
            )
            orders.append(o)
        db.add_all(orders)
        db.flush()  # assigns order IDs

        # Order items + prep times (bulk mappings for speed).
        oi_maps, total_updates = [], []
        for o in orders:
            n_items = random.choices([1, 2, 3, 4], weights=[35, 35, 20, 10])[0]
            chosen = random.choices(menu, weights=pop, k=n_items)
            total = 0
            for mi in chosen:
                qty = random.choices([1, 2, 3], weights=[70, 22, 8])[0]
                oi_maps.append({"order_id": o.id, "menu_item_id": mi.id, "quantity": qty, "unit_price": mi.price})
                total += mi.price * qty
            total_updates.append({"id": o.id, "total": total})
        db.bulk_insert_mappings(models.OrderItem, oi_maps)
        db.bulk_update_mappings(models.Order, total_updates)
        db.flush()

        # Prep times for KDS — one per order item for the last 30 days (enough
        # signal without excessive volume). Load the freshly-inserted items.
        cutoff = datetime.combine(TODAY - timedelta(days=30), time.min)
        recent_oi = (
            db.query(models.OrderItem.id, models.OrderItem.menu_item_id, models.Order.created_at)
            .join(models.Order, models.Order.id == models.OrderItem.order_id)
            .filter(models.Order.restaurant_id == RID, models.Order.created_at >= cutoff)
            .all()
        )
        mi_map = {m.id: m for m in menu}
        pt_maps = []
        for oi_id, mi_id, created in recent_oi:
            mi = mi_map.get(mi_id)
            base_min = (mi.avg_prep_minutes if mi and mi.avg_prep_minutes else 10.0)
            actual = round(max(2.0, random.gauss(base_min, base_min * 0.25)), 1)
            started = created
            pt_maps.append({
                "order_item_id": oi_id,
                "station": (mi.prep_station if mi else "main"),
                "started_at": started,
                "completed_at": started + timedelta(minutes=actual),
                "actual_minutes": actual,
            })
        db.bulk_insert_mappings(models.PrepTime, pt_maps)
        db.flush()

        new_total = db.query(func.count(models.Order.id)).filter(models.Order.restaurant_id == RID).scalar()
        print(f"Inserted {len(orders)} orders, {len(oi_maps)} items, {len(pt_maps)} prep-times.")
        print(f"Restaurant {RID} total orders now: {new_total}")
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
