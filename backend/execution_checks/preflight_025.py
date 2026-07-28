"""
backend/execution_checks/preflight_025.py
──────────────────────────────────────────
Read-only pre-flight check for migration 025 (tenant FK integrity +
owner_phone uniqueness). Run this against a real database BEFORE deploying
025 — it never issues DDL, only SELECTs, so it's always safe to run.

Migration 025 skips (rather than fails) any column/constraint where this
script would report a problem, so a clean run here is the only way to know
those constraints will actually take effect instead of silently no-op'ing.

Usage:
    DATABASE_URL=postgresql://... python execution_checks/preflight_025.py

Exit code 0 = clean (safe to deploy 025 and expect full enforcement).
Exit code 1 = dirty data found (025 will still deploy safely, but will skip
              the affected constraint(s) — reconcile the rows listed below
              first if you want full enforcement).
"""

import os
import sys

from sqlalchemy import create_engine, inspect, text

# Tenant-scoping FK columns migration 025 adds a NOT VALID CHECK to.
_FK_COLUMNS = [
    ("users", "tenant_id"),
    ("restaurants", "tenant_id"),
    ("tables", "restaurant_id"),
    ("menu_items", "restaurant_id"),
    ("inventory_items", "restaurant_id"),
    ("orders", "restaurant_id"),
    ("reservations", "restaurant_id"),
]


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set — refusing to guess which database to check.")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def check_nulls(engine) -> list[str]:
    problems = []
    inspector = inspect(engine)
    with engine.connect() as conn:
        for table, col in _FK_COLUMNS:
            if not inspector.has_table(table):
                continue
            # table/col come only from the hardcoded _FK_COLUMNS list above —
            # never from user input — so there is no injection surface despite
            # the string interpolation bandit flags here (identifiers can't be
            # bind parameters in SQL; only values can).
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")  # nosec B608
            ).scalar()
            if count:
                problems.append(f"{table}.{col}: {count} row(s) with NULL")
    return problems


def check_owner_phone_dupes(engine) -> list[str]:
    problems = []
    inspector = inspect(engine)
    if not inspector.has_table("restaurants"):
        return problems
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT owner_phone, COUNT(*) AS n FROM restaurants "
                "WHERE owner_phone IS NOT NULL "
                "GROUP BY owner_phone HAVING COUNT(*) > 1"
            )
        ).fetchall()
        for owner_phone, n in rows:
            problems.append(f"restaurants.owner_phone = {owner_phone!r}: {n} restaurants share this number")
    return problems


def main() -> int:
    url = _database_url()
    engine = create_engine(url)

    print(f"[preflight_025] checking {engine.url.render_as_string(hide_password=True)}")

    null_problems = check_nulls(engine)
    dupe_problems = check_owner_phone_dupes(engine)

    if not null_problems and not dupe_problems:
        print("[preflight_025] clean — no NULLs in tenant FK columns, no duplicate owner_phone values.")
        print("[preflight_025] migration 025 will fully enforce every constraint.")
        return 0

    print("[preflight_025] DIRTY DATA FOUND — migration 025 will deploy safely but will")
    print("[preflight_025] SKIP enforcement for the affected column(s)/constraint below:")
    for p in null_problems:
        print(f"  - NOT NULL check on {p}")
    for p in dupe_problems:
        print(f"  - UNIQUE index on {p}")
    print("[preflight_025] reconcile these rows, then re-run this script to confirm clean.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
