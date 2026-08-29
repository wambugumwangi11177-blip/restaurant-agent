"""
backend/dev_snapshot.py — one-time (or refreshable) local dev database snapshot
────────────────────────────────────────────────────────────────────────────────
Copies the ENTIRE remote production database (Neon Postgres, wherever
REMOTE_DATABASE_URL points) into a local SQLite file so local dev queries run
in milliseconds instead of crossing an ocean per page view.

Why: the heaviest AI endpoints ship a month+ of order history per call. Against
a same-region DB (Railway -> Neon) that's fine; from a laptop an ocean away it
made every dashboard page take 30-120s. This snapshot makes local dev instant
while leaving production untouched.

Usage:
    venv/bin/python dev_snapshot.py            # refresh local_dev.db from remote
    venv/bin/python dev_snapshot.py --force    # same, but recreate the file

The local copy is a SANDBOX: orders/POS actions/etc. taken while on it stay
local and never touch production. To go back to live remote data, set
DATABASE_URL back to the postgres URL in .env (see RUNBOOK.md).

Idempotent: re-running replaces the local file's contents table-by-table
(remote rows are the source of truth for the copy).
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

REMOTE_URL = os.getenv("REMOTE_DATABASE_URL") or (
    os.getenv("DATABASE_URL")
    if (os.getenv("DATABASE_URL") or "").startswith(("postgres://", "postgresql://"))
    else None
)
LOCAL_URL = os.getenv("LOCAL_DATABASE_URL", "sqlite:///./local_dev.db")
BATCH = 10_000

if not REMOTE_URL:
    sys.exit("Set REMOTE_DATABASE_URL (or point DATABASE_URL at Postgres) in .env — "
             "nothing to copy from.")


def main(force: bool = False) -> None:
    from sqlalchemy import create_engine, select, delete, func
    from models import Base

    if force and LOCAL_URL.startswith("sqlite:///") and os.path.exists(LOCAL_URL.replace("sqlite:///", "", 1)):
        os.remove(LOCAL_URL.replace("sqlite:///", "", 1))

    src = create_engine(REMOTE_URL)
    dst = create_engine(LOCAL_URL)

    print(f"[snapshot] remote: {REMOTE_URL.split('@')[-1]}")
    print(f"[snapshot] local : {LOCAL_URL}")

    Base.metadata.create_all(bind=dst)

    tables = Base.metadata.sorted_tables  # FK-safe topological order
    t_start = time.time()
    total_rows = 0
    with src.connect() as s_conn, dst.begin() as d_conn:
        # wipe local tables children-first (reversed topological order), then
        # copy remote rows parents-first.
        for table in reversed(tables):
            d_conn.execute(delete(table))
        for table in tables:
            pk = table.primary_key.columns[0]
            last_id, copied = -1, 0
            while True:
                rows = s_conn.execute(
                    select(table).where(pk > last_id).order_by(pk).limit(BATCH)
                ).mappings().all()
                if not rows:
                    break
                d_conn.execute(table.insert(), [dict(r) for r in rows])
                last_id = rows[-1][pk.name]
                copied += len(rows)
            total_rows += copied
            if copied:
                print(f"[snapshot] {table.name}: {copied} rows")
    print(f"[snapshot] done: {total_rows} rows in {time.time()-t_start:.0f}s")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
