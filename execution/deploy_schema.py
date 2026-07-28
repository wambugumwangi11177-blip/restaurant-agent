"""
Directive: 005_database.md — Step A: Deploy Core Schema + Seed Data
----------------------------------------------------------------------
Deploys the restaurant_tables, menu_items, and bookings DDL to Neon.
Idempotent: uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.
Seed data uses INSERT ... ON CONFLICT DO NOTHING to be safe on re-runs.

Usage:
    python execution/deploy_schema.py
"""

import os
import sys

# ── Resolve .env (look in repo root first, then restaurant-agent sub-project) ──
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir   = os.path.dirname(_script_dir)
_nested_dir = os.path.join(_root_dir, "restaurant-agent")

_env_candidates = [
    os.path.join(_root_dir, ".env"),
    os.path.join(_nested_dir, ".env"),
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
    print("[WARN] No .env file found — relying on system environment variables.")

# ── Build the psycopg2-compatible DATABASE_URL ──────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL is not set. Aborting.")
    sys.exit(1)

# Neon .env uses asyncpg driver — psycopg2 needs the plain postgresql:// form
DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

# Append ?sslmode=require if not already present (Neon requires SSL)
if "neon.tech" in DATABASE_URL and "sslmode" not in DATABASE_URL:
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL += f"{sep}sslmode=require"

print(f"[INFO] Connecting to: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")

# ── Import psycopg2 ─────────────────────────────────────────────────────────
try:
    import psycopg2
    from psycopg2 import sql as pgsql
except ImportError:
    print("[ERROR] psycopg2 not found. Install it with: pip install psycopg2-binary")
    sys.exit(1)

# ── DDL: Core Schema ────────────────────────────────────────────────────────
DDL = """
-- 1. Tables Management
CREATE TABLE IF NOT EXISTS restaurant_tables (
    table_id       SERIAL PRIMARY KEY,
    table_number   VARCHAR(10)  UNIQUE NOT NULL,
    capacity       INTEGER      NOT NULL CHECK (capacity > 0),
    zone           VARCHAR(50)  NOT NULL,
    current_status VARCHAR(20)  DEFAULT 'Available'
                   CHECK (current_status IN ('Available','Occupied','Reserved','Maintenance')),
    last_updated   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Menu Management (price in cents — no float errors)
CREATE TABLE IF NOT EXISTS menu_items (
    item_id      SERIAL PRIMARY KEY,
    item_name    VARCHAR(100) NOT NULL,
    category     VARCHAR(50)  NOT NULL,
    price_cents  INTEGER      NOT NULL CHECK (price_cents >= 0),
    is_available BOOLEAN      DEFAULT TRUE,
    calories     INTEGER,
    description  TEXT,
    updated_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Booking Ledger (privacy-safe: no PII, only hashed user ref)
CREATE TABLE IF NOT EXISTS bookings (
    booking_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id_hash    VARCHAR(64)  NOT NULL,
    table_id        INTEGER      REFERENCES restaurant_tables(table_id),
    booking_time    TIMESTAMP WITH TIME ZONE NOT NULL,
    party_size      INTEGER      NOT NULL CHECK (party_size > 0),
    status          VARCHAR(20)  DEFAULT 'Confirmed'
                    CHECK (status IN ('Confirmed','Cancelled','Completed','No-Show')),
    idempotency_key VARCHAR(128) UNIQUE NOT NULL,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- High-performance indexes
CREATE INDEX IF NOT EXISTS idx_bookings_user   ON bookings(user_id_hash);
CREATE INDEX IF NOT EXISTS idx_bookings_time   ON bookings(booking_time);
CREATE INDEX IF NOT EXISTS idx_tables_status   ON restaurant_tables(current_status);
"""

# ── Seed Data ───────────────────────────────────────────────────────────────
# NOTE: restaurant_tables and bookings are fresh (created by this script).
# menu_items already existed in Neon (deployed by SQLAlchemy/Alembic).
# Its columns are: id, restaurant_id, name, price, category, is_available, etc.
# The CREATE TABLE IF NOT EXISTS above is a no-op for menu_items.
# We seed using the EXISTING column names (name, price) — not item_name/price_cents.
SEED_TABLES = """
INSERT INTO restaurant_tables (table_number, capacity, zone, current_status) VALUES
    ('T1', 2, 'Window',    'Available'),
    ('T2', 4, 'Main Hall', 'Available'),
    ('T3', 8, 'Garden',    'Available')
ON CONFLICT (table_number) DO NOTHING;
"""

SEED_MENU = """
INSERT INTO menu_items (name, category, price, is_available) VALUES
    ('Nyama Choma', 'Main',  150000, true),
    ('Kachumbari',  'Side',   20000, true),
    ('Dawa',        'Drink',  40000, true)
ON CONFLICT DO NOTHING;
"""

# ── Execute ──────────────────────────────────────────────────────────────────
def run():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        cur = conn.cursor()
        print("\n[1/3] Deploying DDL schema...")
        cur.execute(DDL)
        print("      [OK] restaurant_tables created (or already exists)")
        print("      [OK] menu_items created (or already exists)")
        print("      [OK] bookings created (or already exists)")
        print("      [OK] Indexes created (or already exist)")

        print("\n[2/3] Seeding restaurant_tables...")
        cur.execute(SEED_TABLES)
        print(f"      [OK] {cur.rowcount} row(s) inserted (0 = already seeded)")

        print("\n[3/3] Seeding menu_items...")
        cur.execute(SEED_MENU)
        print(f"      [OK] {cur.rowcount} row(s) inserted (0 = already seeded)")

        conn.commit()
        cur.close()
        conn.close()
        print("\n----------------------------------------------")
        print("  [OK] Schema deployed. [OK] Seed data applied.")
        print("----------------------------------------------\n")

    except psycopg2.OperationalError as e:
        print(f"\n[ERROR] Could not connect to database:\n  {e}")
        print("\nCheck your DATABASE_URL in .env and ensure Neon is reachable.")
        sys.exit(1)
    except psycopg2.Error as e:
        if 'conn' in dir() and conn:
            conn.rollback()
        print(f"\n[ERROR] Database error:\n  {e}")
        sys.exit(1)

if __name__ == "__main__":
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from _guard import require_write_confirmation
    require_write_confirmation("creates core schema tables and seeds reference rows")
    run()
