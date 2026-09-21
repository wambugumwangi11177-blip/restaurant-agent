"""
Build the daily reporting facts for every restaurant, once.

WHY THIS EXISTS
backend/reporting/rollup.py speeds the yearly report from ~1.6 s of database
work to ~7 ms by reading daily_sales_facts / daily_item_sales_facts instead of
scanning orders and order_items. Those tables start EMPTY after migration 048.

Nothing breaks while they are empty — every read in rollup.py checks coverage
and falls back to the live query — but nothing is faster either. The nightly
`reporting_rollup` job only re-aggregates the last 7 complete days, so without
this script the history fills in at one week per week, and the yearly report
stays slow essentially forever.

Run it ONCE after deploying migration 048. It is idempotent: running it again
recomputes the same rows from the same orders.

WHAT IT WRITES
  daily_sales_facts        one row per (restaurant, Nairobi day) — including
                           days with no sales, because presence is what marks a
                           day as built
  daily_item_sales_facts   one row per (restaurant, Nairobi day, menu item)

WHAT IT READS
  orders, order_items — read-only. No transactional row is modified.

SAFETY
  Deliberately NOT wrapped in execution/_guard.py's
  require_destructive_confirmation. That guard exists for scripts that delete
  business data, and demanding ALLOW_DESTRUCTIVE=1 here would blunt the signal
  it carries — the next operator should not learn that the destructive prompt
  is routine. This script only writes a derived cache that rollup.py can
  rebuild from orders at any time, and dropping both tables costs report
  latency and nothing else.

  It still requires --yes, because it writes to whatever DATABASE_URL points
  at, and it prints that target first. --dry-run reports the work and exits.

  After building, it runs rollup.verify() over each restaurant's full range and
  reports drift. A backfill that silently disagreed with the live query would
  be worse than no backfill at all.

USAGE
    python execution/backfill_reporting_facts.py --dry-run
    python execution/backfill_reporting_facts.py --yes
    python execution/backfill_reporting_facts.py --yes --restaurant 3
"""
import argparse
import os
import sys
import time
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from _guard import _safe_target  # noqa: E402  — reuse its DATABASE_URL redaction

import models  # noqa: E402
from database import SessionLocal  # noqa: E402
from reporting import rollup  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="confirm writing to the target below")
    ap.add_argument("--dry-run", action="store_true", help="report the work and exit")
    ap.add_argument("--restaurant", type=int, default=None, help="one restaurant id (default: all)")
    args = ap.parse_args()

    print("=" * 72)
    print("backfill_reporting_facts")
    print(f"  target : {_safe_target()}")
    print("  effect : rebuilds daily_sales_facts / daily_item_sales_facts from orders")
    print("           (derived cache — no transactional row is modified)")
    print("=" * 72)

    if not (args.yes or args.dry_run):
        print("[ABORT] pass --yes to write, or --dry-run to preview.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        q = db.query(models.Restaurant)
        if args.restaurant is not None:
            q = q.filter(models.Restaurant.id == args.restaurant)
        restaurants = q.all()
        if not restaurants:
            print("No restaurants matched — nothing to do.")
            return 0

        failures = 0
        for r in restaurants:
            first = db.query(models.Order.created_at).filter(
                models.Order.restaurant_id == r.id
            ).order_by(models.Order.created_at.asc()).first()
            if first is None:
                print(f"[{r.id}] {r.name}: no orders — skipped")
                continue

            first_day = rollup.business_date_of(first[0])
            today = rollup.business_date_of(rollup.utcnow())
            span = (today - first_day).days
            if args.dry_run:
                print(f"[{r.id}] {r.name}: would build {span} days from {first_day}")
                continue

            t0 = time.time()
            built = rollup.backfill(db, r.id)
            print(f"[{r.id}] {r.name}: built {built} days from {first_day} "
                  f"in {time.time() - t0:.1f}s")

            # Prove it. A cache that disagrees with the source is worse than none.
            start = rollup.day_bounds_utc(first_day)[0]
            end = rollup.day_bounds_utc(today)[0]
            result = rollup.verify(db, r.id, start, end)
            if result["status"] == "clean":
                print(f"      verify: clean (source={result['source']})")
            else:
                failures += 1
                print(f"      verify: MISMATCH revenue_drift_kes="
                      f"{result['revenue_drift_kes']} "
                      f"order_count_drift={result['order_count_drift']}", file=sys.stderr)

        if failures:
            print(f"\n{failures} restaurant(s) failed verification — facts disagree with "
                  f"orders. Reads still fall back to the live query, so reports remain "
                  f"correct; investigate before relying on the facts.", file=sys.stderr)
            return 2
        if not args.dry_run:
            print("\nAll restaurants verified clean.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
