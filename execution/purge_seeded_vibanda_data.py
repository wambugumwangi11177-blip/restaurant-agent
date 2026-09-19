"""
Remove the generated (fake) Vibanda Village data, leaving a real empty account.

WHY THIS EXISTS
Vibanda Village was populated by backend/seed_vibanda.py, which builds its
orders, stock movements and reservations with `random` (see
backend/seed_generators.py). Those numbers are invented. While they sit in the
database, the owner's Home page shows revenue, covers and stock levels that
look real and are not — behind a 10px "Prototype data" label nobody reads.

Once MacSoft's feed is delivering, the invented rows must go, or real and fake
figures are summed together and every total is wrong in a way nobody can
untangle.

WHAT IT DELETES (for the Vibanda tenant only)
  Transactions : orders, order items, order audits, prep times, kitchen incidents
  Stock        : stock movements, transfers, counts
  Front of house: reservations, cash drawer counts
  Staff        : labour shifts
  Catalogue    : menu items, menu ingredients, inventory items  (MacSoft supplies these)
  AI state     : attention decisions, agent predictions/executions tied to the restaurant

WHAT IT KEEPS
  The tenant, the owner's login, the restaurant record, tables and staff
  members. Deleting those would lock the owner out and require re-onboarding.

SAFETY
  Guarded by execution/_guard.py: needs BOTH `--yes` and ALLOW_DESTRUCTIVE=1.
  Runs in ONE transaction — it either removes everything or nothing.
  Pass --dry-run to print the counts it would delete and exit without writing.

USAGE
  # See what would go, touching nothing:
  DATABASE_URL=<railway-url> python execution/purge_seeded_vibanda_data.py --dry-run

  # Actually do it:
  DATABASE_URL=<railway-url> ALLOW_DESTRUCTIVE=1 \
    python execution/purge_seeded_vibanda_data.py --yes

TAKE A BACKUP FIRST — backend/scripts/backup_db.sh.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from _guard import require_destructive_confirmation  # noqa: E402

TENANT_NAME = "Vibanda Village"
DRY_RUN = "--dry-run" in sys.argv

if not DRY_RUN:
    require_destructive_confirmation(
        f"deletes ALL generated transactional data, menu items and inventory for "
        f"the '{TENANT_NAME}' tenant. The tenant, its login, the restaurant "
        f"record, tables and staff are kept."
    )

import models  # noqa: E402
from database import SessionLocal  # noqa: E402

db = SessionLocal()
try:
    tenant = db.query(models.Tenant).filter(models.Tenant.name == TENANT_NAME).one_or_none()
    if tenant is None:
        print(f"[SKIP] No tenant named {TENANT_NAME!r} — nothing to do.")
        raise SystemExit(0)

    rids = [r.id for r in db.query(models.Restaurant.id)
            .filter(models.Restaurant.tenant_id == tenant.id).all()]
    if not rids:
        print(f"[SKIP] Tenant {TENANT_NAME!r} has no restaurants — nothing to do.")
        raise SystemExit(0)
    print(f"tenant id={tenant.id}  restaurants={rids}")

    order_ids = [o.id for o in db.query(models.Order.id)
                 .filter(models.Order.restaurant_id.in_(rids)).all()]
    item_ids = [m.id for m in db.query(models.MenuItem.id)
                .filter(models.MenuItem.restaurant_id.in_(rids)).all()]
    inv_ids = [i.id for i in db.query(models.InventoryItem.id)
               .filter(models.InventoryItem.restaurant_id.in_(rids)).all()]
    order_item_ids = [oi.id for oi in db.query(models.OrderItem.id)
                      .filter(models.OrderItem.order_id.in_(order_ids)).all()]

    # Children before parents. OrderItem holds ondelete=RESTRICT on MenuItem, so
    # the catalogue cannot go until the transactions referencing it have gone;
    # PrepTime hangs off OrderItem (not Order) and CashDrawerCount off
    # LaborShift, so both need their parent's ids collected above first.
    plan = [
        ("prep times",          models.PrepTime,        models.PrepTime.order_item_id.in_(order_item_ids)),
        ("kitchen incidents",   models.KitchenIncident, models.KitchenIncident.restaurant_id.in_(rids)),
        ("order items",         models.OrderItem,       models.OrderItem.order_id.in_(order_ids)),
        ("order audits",        models.OrderAudit,      models.OrderAudit.restaurant_id.in_(rids)),
        ("orders",              models.Order,           models.Order.restaurant_id.in_(rids)),
        ("stock movements",     models.StockMovement,   models.StockMovement.inventory_item_id.in_(inv_ids)),
        ("stock transfers",     models.StockTransfer,   models.StockTransfer.restaurant_id.in_(rids)),
        ("stock counts",        models.StockCount,      models.StockCount.restaurant_id.in_(rids)),
        ("reservations",        models.Reservation,     models.Reservation.restaurant_id.in_(rids)),
        ("cash drawer counts",  models.CashDrawerCount, models.CashDrawerCount.restaurant_id.in_(rids)),
        ("labour shifts",       models.LaborShift,      models.LaborShift.restaurant_id.in_(rids)),
        ("attention decisions", models.AttentionDecision, models.AttentionDecision.tenant_id == tenant.id),
        ("agent predictions",   models.AgentPrediction, models.AgentPrediction.restaurant_id.in_(rids)),
        ("agent executions",    models.AgentExecution,  models.AgentExecution.restaurant_id.in_(rids)),
        ("menu ingredients",    models.MenuIngredient,  models.MenuIngredient.menu_item_id.in_(item_ids)),
        ("menu items",          models.MenuItem,        models.MenuItem.restaurant_id.in_(rids)),
        ("inventory items",     models.InventoryItem,   models.InventoryItem.restaurant_id.in_(rids)),
    ]

    total = 0
    for label, model, condition in plan:
        q = db.query(model).filter(condition)
        n = q.count()
        total += n
        if n:
            print(f"  {'would delete' if DRY_RUN else 'deleting':<13} {n:>7,}  {label}")
        if not DRY_RUN and n:
            q.delete(synchronize_session=False)

    if DRY_RUN:
        print(f"\n[DRY RUN] {total:,} rows would be deleted. Nothing was written.")
        raise SystemExit(0)

    db.commit()
    print(f"\n[DONE] {total:,} rows deleted. Tenant, login, restaurant, tables and staff kept.")
    print("The dashboard will now show its honest empty state until MacSoft data arrives.")
except SystemExit:
    raise
except Exception:
    db.rollback()
    print("\n[ROLLED BACK] Nothing was deleted.", file=sys.stderr)
    raise
finally:
    db.close()
