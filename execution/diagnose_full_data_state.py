"""
Read-only, no-PII diagnostic (2026-07-07): full data-state survey for the
Lavy showcase restaurant (restaurant_id=3). Aggregate counts only — no PII,
no row contents. Tells us what every AI module has to work with so we can
make the demo restaurant show rich insights end to end.

Run: python execution/diagnose_full_data_state.py
"""
import os
import sys
from datetime import datetime, timedelta

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)

from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

from database import SessionLocal
import models
from sqlalchemy import func

RID = 3
db = SessionLocal()


def section(t):
    print("\n" + "=" * 60 + f"\n{t}\n" + "=" * 60)


section("ORDERS — recency")
mx = db.query(func.max(models.Order.created_at)).filter(models.Order.restaurant_id == RID).scalar()
mn = db.query(func.min(models.Order.created_at)).filter(models.Order.restaurant_id == RID).scalar()
total = db.query(func.count(models.Order.id)).filter(models.Order.restaurant_id == RID).scalar()
print(f"  total={total}  first={mx and mn}  last={mx}")
print(f"  wall-clock now = {datetime.utcnow()}")
# last 45 days of ACTUAL data (by day)
recent_cut = (mx or datetime.utcnow()) - timedelta(days=10)
byday = (
    db.query(func.date(models.Order.created_at).label("d"), func.count(models.Order.id))
    .filter(models.Order.restaurant_id == RID, models.Order.created_at >= recent_cut)
    .group_by("d").order_by("d").all()
)
print("  last ~10 days present in data:")
for d, c in byday:
    print(f"    {d}: {c} orders")

section("MENU ITEMS — margin distribution")
items = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == RID).all()
print(f"  total menu items: {len(items)}")
avail = sum(1 for i in items if i.is_available)
print(f"  available: {avail}   unavailable: {len(items)-avail}")
have_cost = sum(1 for i in items if (i.cost_price or 0) > 0)
print(f"  with cost_price>0: {have_cost}")
margins = []
for i in items:
    if i.price and i.cost_price:
        margins.append(round((i.price - i.cost_price) / i.price * 100))
if margins:
    from collections import Counter
    print(f"  margin%% distribution (rounded): {dict(sorted(Counter(margins).items()))}")
    print(f"  below 40%% margin floor: {sum(1 for m in margins if m < 40)}")

section("RESERVATIONS / BOOKINGS")
res_total = db.query(func.count(models.Reservation.id)).filter(models.Reservation.restaurant_id == RID).scalar()
print(f"  total reservations: {res_total}")
if res_total:
    by_status = db.query(models.Reservation.status, func.count(models.Reservation.id)).filter(
        models.Reservation.restaurant_id == RID).group_by(models.Reservation.status).all()
    for s, c in by_status:
        print(f"    {s}: {c}")
    rmax = db.query(func.max(models.Reservation.reservation_date)).filter(models.Reservation.restaurant_id == RID).scalar()
    rmin = db.query(func.min(models.Reservation.reservation_date)).filter(models.Reservation.restaurant_id == RID).scalar()
    print(f"    date range: {rmin} -> {rmax}")

section("INVENTORY")
inv_total = db.query(func.count(models.InventoryItem.id)).filter(models.InventoryItem.restaurant_id == RID).scalar()
print(f"  inventory items: {inv_total}")
try:
    mv = db.query(func.count(models.InventoryMovement.id)).join(
        models.InventoryItem, models.InventoryItem.id == models.InventoryMovement.inventory_item_id
    ).filter(models.InventoryItem.restaurant_id == RID).scalar()
    print(f"  inventory movements: {mv}")
except Exception as e:
    print(f"  movements: n/a ({e})")

section("LABOR SHIFTS")
try:
    ls = db.query(func.count(models.LaborShift.id)).filter(models.LaborShift.restaurant_id == RID).scalar()
    lmax = db.query(func.max(models.LaborShift.shift_date)).filter(models.LaborShift.restaurant_id == RID).scalar()
    print(f"  labor shifts: {ls}   latest: {lmax}")
except Exception as e:
    print(f"  labor: n/a ({e})")

section("SUPPLIERS / PURCHASE ORDERS")
try:
    sup = db.query(func.count(models.Supplier.id)).filter(models.Supplier.restaurant_id == RID).scalar()
    po = db.query(func.count(models.PurchaseOrder.id)).filter(models.PurchaseOrder.restaurant_id == RID).scalar()
    print(f"  suppliers: {sup}   purchase orders: {po}")
except Exception as e:
    print(f"  suppliers/PO: n/a ({e})")

section("TABLES")
tb = db.query(func.count(models.Table.id)).filter(models.Table.restaurant_id == RID).scalar()
print(f"  tables: {tb}")

db.close()
