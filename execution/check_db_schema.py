"""Read-only schema-drift check: deployed Neon DB vs what this branch expects.

Deterministic execution tool (Layer 3). Safe to run any time — only SELECTs.
Answers: is the production schema missing tables/columns this branch's code needs?

Usage:  cd backend
        python ..\execution\check_db_schema.py

NOTE: parses backend/.env directly for DATABASE_URL. A plain load_dotenv()
from a script outside backend/ walks up the tree and can find the ROOT .env
(localhost dev DB) instead of backend/.env (Neon) — happened 2026-09-01.
"""
import os
import re

import psycopg2

# Parse backend/.env directly (deterministic) — a plain load_dotenv() from a
# script inside .tmp/ walks up and finds the ROOT .env instead, whose
# DATABASE_URL is a localhost dev DB that isn't running.
env_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", ".env"
)
url = None
with open(env_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line.startswith("DATABASE_URL") and "=" in line and not line.startswith("#"):
            url = line.split("=", 1)[1].strip().strip("'\"")
assert url, f"No active DATABASE_URL found in {env_path}"
print("DB host:", re.search(r"@([^:/?]+)", url).group(1))

conn = psycopg2.connect(url)

cur = conn.cursor()

cur.execute(
    "select table_name from information_schema.tables "
    "where table_schema='public' order by table_name"
)
tables = {r[0] for r in cur.fetchall()}
print("total public tables:", len(tables))

# Tables created by this branch's untracked 030_add_operational_core_tables
# migration + the 001 agent tables (exact names from the migration file).
for t in [
    "order_payments",
    "modifier_groups",
    "modifier_options",
    "menu_item_modifier_groups",
    "order_item_modifiers",
    "till_sessions",
    "inventory_counts",
    "inventory_count_lines",
    "waste_logs",
    "restaurant_settings",
    "pricing_recommendations",
    "agent_messages",
    "orders",
    "users",
]:
    print(("PRESENT" if t in tables else "MISSING"), t)

cur.execute(
    "select column_name from information_schema.columns "
    "where table_name='orders'"
)
order_cols = {r[0] for r in cur.fetchall()}
for c in [
    "discount_cents",
    "discount_reason",
    "void_reason",
    "refund_cents",
    "refund_reason",
    "tax_cents",
    "service_charge_cents",
]:
    print(("orders." + c + " PRESENT") if c in order_cols else ("orders." + c + " MISSING"))

cur.execute("select version_num from alembic_version")
print("alembic_version:", cur.fetchone()[0])

conn.close()
