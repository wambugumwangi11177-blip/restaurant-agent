"""
execution/tune_showcase_health.py
───────────────────────────────────
Post-seed health tuning for the Lavy showcase (restaurant_id=3). The initial
seed left two health-score drags that read as "restaurant in crisis" rather
than "thriving restaurant with optimisation upside" for an enterprise demo:

  • 16 of 30 inventory items below their low-stock threshold — the inventory
    health sub-score (100 - 10*low - 25*critical) floored at 0. A credible
    demo shows a FEW predictive restock alerts (the AI's value), not a
    warehouse that's empty. Bump most quantities healthy, leave ~5 genuinely
    low (incl. 2 perishable → spoilage alerts).
  • Past-dated reservations were mostly left CONFIRMED, so the completion rate
    (completed / total) sat at ~16%. Historically, past reservations should be
    COMPLETED (guests showed up) or NO_SHOW — not perpetually "confirmed".
    Convert past CONFIRMED → ~88% COMPLETED / ~12% NO_SHOW so the no-show and
    completion metrics look like a real, well-run book.

Idempotent + scoped to restaurant_id=3. Run:
    python execution/tune_showcase_health.py
"""
import os
import sys
import random
from datetime import datetime

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)
from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

from database import SessionLocal
import models

from _guard import require_destructive_confirmation

RID = 3
random.seed(7)
TODAY = datetime.utcnow().date()

# Items that should stay genuinely low (predictive restock alerts). The first
# two are short-shelf-life perishables → also spoilage-risk alerts.
KEEP_LOW = {"Chicken", "Tomatoes", "Passion Fruit", "Fish (Tilapia)", "Prawns"}

# This script has no main() — it runs on import, so the gate must come before
# the first query. It issues no DELETE, but the mass UPDATEs below irreversibly
# overwrite real inventory quantities and past reservation statuses.
require_destructive_confirmation(
    f"OVERWRITES every inventory quantity and rewrites every past CONFIRMED "
    f"reservation to COMPLETED/NO_SHOW for restaurant_id={RID}"
)

db = SessionLocal()
try:
    # ── Inventory: healthy stock for most, a handful genuinely low ──
    # Expiry-aware: over-stocking a short-shelf-life item creates a spoilage-
    # risk alert, so perishables are kept modestly stocked (enough to clear
    # the low-stock threshold, not so much they'd spoil), while shelf-stable
    # items can carry a fuller buffer. Keeps the demo's alert counts realistic
    # (a few restock + a couple spoilage) instead of a wall of red.
    items = db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == RID).all()
    low_kept = 0
    for it in items:
        thr = it.low_stock_threshold or 10
        expiry = it.expiry_days or 30
        if it.item_name in KEEP_LOW:
            it.quantity = round(thr * random.uniform(0.3, 0.6), 1)   # below threshold → restock alert
            low_kept += 1
        elif expiry <= 8:
            it.quantity = round(thr * random.uniform(1.0, 1.25), 1)  # perishable: modest, avoids spoilage flag
        else:
            it.quantity = round(thr * random.uniform(1.6, 2.4), 1)   # shelf-stable: fuller buffer
    print(f"Inventory: {low_kept} items kept low (restock alerts), {len(items)-low_kept} restocked healthy.")

    # ── Reservations: settle past-dated bookings realistically ──
    past_confirmed = (
        db.query(models.Reservation)
        .filter(
            models.Reservation.restaurant_id == RID,
            models.Reservation.reservation_date < TODAY,
            models.Reservation.status == models.ReservationStatus.CONFIRMED,
        )
        .all()
    )
    completed = no_show = 0
    for r in past_confirmed:
        if random.random() < 0.88:
            r.status = models.ReservationStatus.COMPLETED
            completed += 1
        else:
            r.status = models.ReservationStatus.NO_SHOW
            no_show += 1
    print(f"Reservations: settled {len(past_confirmed)} past bookings -> {completed} completed, {no_show} no-show.")

    db.commit()
    print("[OK] Committed.")
except Exception as e:
    db.rollback()
    print(f"[ERROR] Rolled back: {e}")
    raise
finally:
    db.close()
