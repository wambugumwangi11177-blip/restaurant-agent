"""
execution/backfill_reservation_created_at.py
────────────────────────────────────────────────
150 seeded reservations for the Lavy showcase had created_at=None, which made
the /reservations response fail validation (500 → empty bookings page). The
schema is now tolerant, but backfill realistic booking timestamps too: a
reservation is booked a few days BEFORE its date. Scoped to restaurant_id=3.

Run: python execution/backfill_reservation_created_at.py
"""
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)
from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _guard import require_write_confirmation
require_write_confirmation("backfills created_at on existing reservation rows")

from database import engine
from sqlalchemy import text

with engine.begin() as c:
    n = c.execute(text("""
        UPDATE reservations
           SET created_at = (reservation_date - INTERVAL '3 days')
                            + INTERVAL '10 hours'
         WHERE restaurant_id = 3 AND created_at IS NULL
    """))
    remaining = c.execute(text(
        "SELECT count(*) FROM reservations WHERE restaurant_id = 3 AND created_at IS NULL"
    )).scalar()
    print(f"[OK] Backfilled created_at on {n.rowcount} reservations. Remaining null: {remaining}")
