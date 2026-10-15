"""
execution/reseed_demo.py — regenerate the "Demo Restaurant" (two branches, 120 days) with the deterministic generator
(backend/demo/generator.py). Directive: docs/v2/SPEC.md §6, S2.1.

DESTRUCTIVE for the demo tenant only: its orders, stock, shifts, bookings, counts and derived rows are deleted and
rewritten (backend/demo/wipe.py lists exactly which tables). Every other tenant is untouched; the script refuses to
run if the tenant it would wipe is not the one named "Demo Restaurant".

Target database: --database-url, else the DATABASE_URL environment variable, else a local SQLite file
(backend/local_dev.db). backend/.env is NEVER read for the target — in this repository it points at the live database.

  python execution/reseed_demo.py --yes --owner-password '<strong password>'
  python execution/reseed_demo.py --yes --seed 7 --days 120 --owner-password '…'

A database that is not on this machine is refused unless you pass --allow-remote, set ALLOW_DESTRUCTIVE=1 and type the
sentence the script prints (see backend/demo/safety.py).
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from demo import safety  # noqa: E402  (no database import: `demo` and `demo.safety` are pure)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Regenerate the Demo Restaurant (deterministic, two branches, 120 days).")
    p.add_argument("--database-url", default=None, help="default: $DATABASE_URL, else sqlite backend/local_dev.db")
    p.add_argument("--owner-email", default=os.getenv("DEMO_RESTAURANT_OWNER_EMAIL", "owner@demo-restaurant.example"))
    p.add_argument("--owner-password", default=os.getenv("DEMO_RESTAURANT_OWNER_PASSWORD"))
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--yes", action="store_true", help="confirm that the demo tenant's data may be deleted and rewritten")
    p.add_argument("--allow-remote", action="store_true", help="allow a database that is not on this machine (see the docstring)")
    p.add_argument("--dry-run", action="store_true", help="print the target and what would happen; write nothing")
    args = p.parse_args(argv)

    url = args.database_url or os.getenv("DATABASE_URL") or f"sqlite:///{os.path.join(BACKEND, 'local_dev.db')}"
    kind = safety.classify(url)
    print(f"target: {safety.describe(url)}  ({kind})")
    if args.dry_run:
        print("dry run: would wipe and regenerate the Demo Restaurant tenant (two branches); nothing written.")
        return 0

    typed = None
    if kind == "remote" and args.allow_remote and args.yes:
        print(f"This is NOT a local database. Type exactly:  {safety.required_sentence(url)}")
        typed = input("> ") if sys.stdin.isatty() else ""
    try:
        safety.require_safe_target(url, yes=args.yes, allow_remote=args.allow_remote, typed=typed)
    except safety.UnsafeTarget as exc:
        print(f"[ABORT] {exc}", file=sys.stderr)
        return 2
    if not args.owner_password:
        print("[ABORT] --owner-password (or DEMO_RESTAURANT_OWNER_PASSWORD) is required", file=sys.stderr)
        return 2

    os.environ["DATABASE_URL"] = url            # database.py honours an existing variable over backend/.env
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker

    import models
    from demo.generator import DEFAULT_SEED, build

    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if not inspect(engine).has_table("tenants"):
        if kind != "local":
            print("[ABORT] the remote database has no tables; run the migrations first", file=sys.stderr)
            return 2
        models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=True)()
    try:
        summary = build(session, args.owner_email, args.owner_password, seed=args.seed if args.seed is not None else DEFAULT_SEED,
                        days=args.days)
    finally:
        session.close()
    print(json.dumps(summary.as_dict(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
