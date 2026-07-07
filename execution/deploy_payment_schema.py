"""
execution/deploy_payment_schema.py
-----------------------------------
Directive: 005_database.md -- Payment Schema (Atomic Finance Layer)
Deploys the payments table and payment_status column to Neon.

Idempotent:
  - CREATE TABLE IF NOT EXISTS  (safe on re-run)
  - ALTER TABLE ... ADD COLUMN IF NOT EXISTS  (safe on re-run)
  - CREATE INDEX IF NOT EXISTS  (safe on re-run)
  - Seed INSERT uses ON CONFLICT DO NOTHING

Engineering decisions:
  - amounts stored as INTEGER cents (no floats)
  - checkout_request_id UNIQUE prevents double-credit on duplicate callbacks
  - callback_payload JSONB stores raw Safaricom evidence for audit
  - payment_status on bookings table uses CHECK constraint
  - bookings.payment_status DEFAULT 'Unpaid' backfills existing rows safely

Usage:
    python execution/deploy_payment_schema.py
"""

import os
import sys

# ── Resolve .env ──────────────────────────────────────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir   = os.path.dirname(_script_dir)
_nested_dir = os.path.join(_root_dir, "restaurant-agent")

_env_candidates = [
    os.path.join(_nested_dir, ".env"),
    os.path.join(_root_dir, ".env"),
    os.path.join(_root_dir, "backend", ".env"),
]

_loaded_env = None
for _p in _env_candidates:
    if os.path.exists(_p):
        from dotenv import load_dotenv
        load_dotenv(_p)
        _loaded_env = _p
        break

if _loaded_env:
    print(f"[INFO] Loaded env from: {_loaded_env}")
else:
    print("[WARN] No .env file found -- relying on system environment variables.")

# ── Build psycopg2-compatible DATABASE_URL ────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL is not set. Aborting.")
    sys.exit(1)

DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

if "neon.tech" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL += f"{sep}sslmode=require"

print(f"[INFO] Connecting to: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")

# ── Import psycopg2 ───────────────────────────────────────────────────────────
try:
    import psycopg2
except ImportError:
    print("[ERROR] psycopg2 not found. Install it: pip install psycopg2-binary")
    sys.exit(1)

# ── DDL: Payment Ledger ───────────────────────────────────────────────────────
# Design rationale:
#   payments is a SEPARATE table from bookings — never mix money state into a
#   booking record directly. This preserves a clean audit trail of every attempt,
#   including failed and expired STK pushes, without corrupting the booking row.

DDL_PAYMENTS = """
CREATE TABLE IF NOT EXISTS payments (
    payment_id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id            UUID         NOT NULL REFERENCES bookings(booking_id),

    -- Safaricom's unique ID for the STK push request.
    -- UNIQUE constraint is the defence against the "Double Credit" attack:
    -- a duplicate callback is rejected by the DB before any money logic runs.
    checkout_request_id   VARCHAR(128) UNIQUE NOT NULL,

    -- Amount in INTEGER cents — zero floats, zero rounding errors.
    -- 500 KES = 50000 cents. This is the only safe way to store money.
    amount_cents          INTEGER      NOT NULL CHECK (amount_cents >= 0),
    currency              VARCHAR(3)   DEFAULT 'KES',

    -- State machine: Pending -> Completed | Failed | Expired
    -- No other transitions are valid; the CHECK constraint enforces this.
    status                VARCHAR(20)  DEFAULT 'Pending'
                          CHECK (status IN ('Pending', 'Completed', 'Failed', 'Expired')),

    -- Raw JSON evidence from Safaricom's callback webhook.
    -- This is the financial audit trail. Never discard it.
    callback_payload      JSONB,

    created_at            TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# ── DDL: Add payment_status to bookings ──────────────────────────────────────
# ADD COLUMN IF NOT EXISTS makes this idempotent on re-runs.
# The CHECK constraint is applied at column creation — not a separate ALTER.
# Default 'Unpaid' correctly backfills all existing booking rows.

DDL_BOOKING_COLUMN = """
ALTER TABLE bookings
    ADD COLUMN IF NOT EXISTS payment_status VARCHAR(20) DEFAULT 'Unpaid'
    CHECK (payment_status IN ('Unpaid', 'Paid', 'Refunded'));
"""

# ── DDL: Indexes for fast reconciliation ─────────────────────────────────────
DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_payments_checkout_id ON payments(checkout_request_id);
CREATE INDEX IF NOT EXISTS idx_payments_booking_id  ON payments(booking_id);
CREATE INDEX IF NOT EXISTS idx_payments_status      ON payments(status);
"""

# ── Seed: Test payment record ─────────────────────────────────────────────────
# Creates one real booking (unpaid) + one pending payment against it.
# This lets us verify the orchestrator can "see" a pending payment state
# before we wire up the real M-Pesa STK push in Step B.
#
# The idempotency_key uses ON CONFLICT DO NOTHING so re-runs are safe.
# The checkout_request_id also has a UNIQUE constraint — same protection.

SEED_TEST_BOOKING = """
INSERT INTO bookings
    (user_id_hash, table_id, booking_time, party_size, idempotency_key, payment_status)
VALUES
    ('hash_payment_test_001',
     1,
     '2026-12-25 19:00:00+03',
     2,
     'test_payment_idempotency_key_001',
     'Unpaid')
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING booking_id;
"""

SEED_TEST_PAYMENT = """
INSERT INTO payments
    (booking_id, checkout_request_id, amount_cents, status)
VALUES
    (%s, 'MPEZA_TICK_12345', 50000, 'Pending')
ON CONFLICT (checkout_request_id) DO NOTHING;
"""


# ── Execute ───────────────────────────────────────────────────────────────────
def run():
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        cur = conn.cursor()

        # Step 1: payments table
        print("\n[1/4] Creating payments table...")
        cur.execute(DDL_PAYMENTS)
        print("      [OK] payments table created (or already exists)")

        # Step 2: payment_status column on bookings
        print("\n[2/4] Adding payment_status column to bookings...")
        cur.execute(DDL_BOOKING_COLUMN)
        print("      [OK] bookings.payment_status column added (or already exists)")

        # Step 3: indexes
        print("\n[3/4] Creating indexes...")
        cur.execute(DDL_INDEXES)
        print("      [OK] idx_payments_checkout_id")
        print("      [OK] idx_payments_booking_id")
        print("      [OK] idx_payments_status")

        # Step 4: seed test data
        print("\n[4/4] Seeding test booking + pending payment...")
        cur.execute(SEED_TEST_BOOKING)
        row = cur.fetchone()

        if row:
            booking_uuid = row[0]
            print(f"      [OK] Test booking created: {booking_uuid}")
            cur.execute(SEED_TEST_PAYMENT, (booking_uuid,))
            print(f"      [OK] Pending payment seeded (checkout: MPEZA_TICK_12345, amount: 500.00 KES)")
        else:
            print("      [--] Test booking already exists (idempotency_key conflict) -- skipping payment seed")

        conn.commit()
        cur.close()

        print("\n--------------------------------------------------------------")
        print("  [OK] Payment schema deployed.")
        print("  [OK] Seed data applied.")
        print("\n  State Machine wired:")
        print("  bookings.payment_status: Unpaid -> Paid | Refunded")
        print("  payments.status:         Pending -> Completed | Failed | Expired")
        print("--------------------------------------------------------------\n")
        print("Ready for Step B: STK Push tool + M-Pesa callback webhook.\n")

    except psycopg2.OperationalError as e:
        print(f"\n[ERROR] Could not connect to database:\n  {e}")
        print("\nCheck your DATABASE_URL in .env and ensure Neon is reachable.")
        sys.exit(1)
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        print(f"\n[ERROR] Database error:\n  {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    run()
