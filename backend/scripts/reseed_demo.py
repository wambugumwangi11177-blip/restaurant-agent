"""
Scoped, re-runnable re-seed of the demo tenant's TRANSACTIONAL data.

DESTRUCTIVE. Deletes the demo restaurant's orders, order items, prep times,
order audits, kitchen incidents, customer feedback, stock movements and
reservations — then regenerates them via seed_generators (which include
today, so the Overview dashboard shows a coherent "now"). Nothing else is
touched: menu items, inventory items, tables, staff, users, settings and
every other tenant are preserved. Never run this from CI.

Usage (from the backend directory, e.g. via `railway run`):
    python scripts/reseed_demo.py --dry-run                     # counts only
    python scripts/reseed_demo.py --yes-delete-demo-data        # actually wipe+regenerate

A fresh backup MUST exist first (backend/scripts/backup_db.sh or the
db-backup workflow_dispatch; see backend/DISASTER_RECOVERY.md).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    Tenant, Restaurant, MenuItem, Table, InventoryItem,
    Order, OrderItem, OrderAudit, PrepTime, KitchenIncident,
    CustomerFeedback, StockMovement, Reservation,
)
from seed_generators import (  # noqa: E402
    generate_orders, generate_stock_movements, generate_reservations,
)

DEMO_TENANT_NAME = "Leviii Client Demo"


def _counts(db, restaurant_id):
    order_ids = db.query(Order.id).filter(Order.restaurant_id == restaurant_id).scalar_subquery()
    oi_ids = (
        db.query(OrderItem.id)
        .filter(OrderItem.order_id.in_(order_ids))
        .scalar_subquery()
    )
    inv_ids = (
        db.query(InventoryItem.id)
        .filter(InventoryItem.restaurant_id == restaurant_id)
        .scalar_subquery()
    )
    return {
        "orders": db.query(Order).filter(Order.restaurant_id == restaurant_id).count(),
        "order_items": db.query(OrderItem).filter(OrderItem.order_id.in_(order_ids)).count(),
        "order_audits": db.query(OrderAudit).filter(OrderAudit.order_id.in_(order_ids)).count(),
        "prep_times": db.query(PrepTime).filter(PrepTime.order_item_id.in_(oi_ids)).count(),
        "kitchen_incidents": db.query(KitchenIncident).filter(KitchenIncident.restaurant_id == restaurant_id).count(),
        "customer_feedback": db.query(CustomerFeedback).filter(CustomerFeedback.restaurant_id == restaurant_id).count(),
        "stock_movements": db.query(StockMovement).filter(StockMovement.inventory_item_id.in_(inv_ids)).count(),
        "reservations": db.query(Reservation).filter(Reservation.restaurant_id == restaurant_id).count(),
    }


def _print_counts(label, counts):
    print(f"  {label}:")
    for name, n in counts.items():
        print(f"    {name:<18} {n}")


def wipe_restaurant(db, restaurant_id):
    """Delete transactional rows for one restaurant, FK-safe order."""
    order_ids = db.query(Order.id).filter(Order.restaurant_id == restaurant_id).scalar_subquery()
    oi_ids = (
        db.query(OrderItem.id)
        .filter(OrderItem.order_id.in_(order_ids))
        .scalar_subquery()
    )
    inv_ids = (
        db.query(InventoryItem.id)
        .filter(InventoryItem.restaurant_id == restaurant_id)
        .scalar_subquery()
    )

    db.query(KitchenIncident).filter(KitchenIncident.restaurant_id == restaurant_id).delete(synchronize_session=False)
    db.query(CustomerFeedback).filter(CustomerFeedback.restaurant_id == restaurant_id).delete(synchronize_session=False)
    db.query(PrepTime).filter(PrepTime.order_item_id.in_(oi_ids)).delete(synchronize_session=False)
    db.query(OrderAudit).filter(OrderAudit.order_id.in_(order_ids)).delete(synchronize_session=False)
    db.query(OrderItem).filter(OrderItem.order_id.in_(order_ids)).delete(synchronize_session=False)
    db.query(Order).filter(Order.restaurant_id == restaurant_id).delete(synchronize_session=False)
    db.query(StockMovement).filter(StockMovement.inventory_item_id.in_(inv_ids)).delete(synchronize_session=False)
    db.query(Reservation).filter(Reservation.restaurant_id == restaurant_id).delete(synchronize_session=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--tenant", default=DEMO_TENANT_NAME,
                        help="Exact tenant name to re-seed (default: %(default)s)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to generate")
    parser.add_argument("--dry-run", action="store_true", help="Print row counts, change nothing")
    parser.add_argument("--yes-delete-demo-data", action="store_true",
                        help="Required to actually delete and regenerate")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == args.tenant).first()
        if not tenant:
            print(f"[ABORT] No tenant named {args.tenant!r}. Nothing touched.")
            return 2

        restaurants = db.query(Restaurant).filter(Restaurant.tenant_id == tenant.id).all()
        print(f"[INFO] Tenant: {tenant.name} (id={tenant.id})")
        for r in restaurants:
            print(f"[INFO] Restaurant: {r.name} (id={r.id})")
        if not restaurants:
            print("[ABORT] Tenant has no restaurants. Nothing touched.")
            return 2

        for r in restaurants:
            print(f"\n[COUNTS] {r.name} BEFORE:")
            _print_counts("before", _counts(db, r.id))

        if args.dry_run:
            print("\n[DRY-RUN] No changes made.")
            return 0

        if not args.yes_delete_demo_data:
            print("\n[ABORT] Refusing to delete data without --yes-delete-demo-data.")
            print("        Run a fresh backup first (backend/scripts/backup_db.sh or the")
            print("        db-backup workflow_dispatch — see backend/DISASTER_RECOVERY.md),")
            print("        then re-run with the flag. Or use --dry-run to inspect counts.")
            return 2

        for r in restaurants:
            menu_items = db.query(MenuItem).filter(MenuItem.restaurant_id == r.id).all()
            inv_items = db.query(InventoryItem).filter(InventoryItem.restaurant_id == r.id).all()
            tables = db.query(Table).filter(Table.restaurant_id == r.id).all()
            if not menu_items or not inv_items or not tables:
                print(f"[ABORT] {r.name}: missing menu/inventory/tables — not a fully seeded restaurant.")
                return 2

        # One transaction: wipe + regenerate, commit once. Rollback on any error.
        try:
            total_orders = 0
            for r in restaurants:
                wipe_restaurant(db, r.id)
                menu_items = db.query(MenuItem).filter(MenuItem.restaurant_id == r.id).all()
                inv_items = db.query(InventoryItem).filter(InventoryItem.restaurant_id == r.id).all()
                tables = db.query(Table).filter(Table.restaurant_id == r.id).all()

                total_orders += generate_orders(db, r.id, menu_items, days=args.days, include_today=True)
                generate_stock_movements(db, inv_items, days=args.days, include_today=True)
                generate_reservations(db, r.id, tables, days=args.days, include_today=True)

            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[ERROR] Rolled back, nothing changed: {e}")
            raise

        print(f"\n[SUCCESS] Re-seeded {tenant.name}: {total_orders} orders regenerated (incl. today).")
        for r in restaurants:
            print(f"\n[COUNTS] {r.name} AFTER:")
            _print_counts("after", _counts(db, r.id))
        print("\n[NOTE] The /ai/dashboard payload is cached ~120s; restart the app or wait before checking.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
