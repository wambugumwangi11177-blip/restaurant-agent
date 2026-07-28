"""
execution/_guard.py
────────────────────
Confirmation gate for scripts that irreversibly destroy data.

Why this exists: five scripts in `execution/` (`seed_demo_data.py`,
`regenerate_recent_window.py`, `seed_showcase_restaurant.py`,
`tune_showcase_health.py`, `smooth_recent_and_finalize.py`) run `drop_all`,
bulk `DELETE`, or mass `UPDATE` against **whatever `DATABASE_URL` is in
`backend/.env`** — which in this repo is the live Neon Postgres. Any of them
could be run by muscle memory or a stray tab-complete and take production with
it. None asked for confirmation.

The gate deliberately requires *two independent* affirmations, because either
one alone is easy to trip by accident:

  1. `--yes` on the command line  — you meant to run THIS script, and
  2. `ALLOW_DESTRUCTIVE=1` in env — you meant to destroy data at ALL.

Usage (top of the script's entrypoint, AFTER any `load_dotenv`, so the
DATABASE_URL we echo is the one the script will really use):

    from _guard import require_destructive_confirmation
    require_destructive_confirmation("drops ALL tables and reseeds demo data")
"""

import os
import sys
from urllib.parse import urlparse

# backend/ is on sys.path by the time these scripts call in (each one inserts it
# before importing database/auth), but this module can also be imported first —
# so resolve the environment defensively rather than assuming.
def _current_env() -> str:
    try:
        sys.path.insert(0, os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
        from environment import current_env
        return current_env()
    except Exception:
        return "unknown"


def _safe_target() -> str:
    """`DATABASE_URL` with credentials stripped — never print the password."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return "<DATABASE_URL unset — the script's own default will be used>"
    try:
        parsed = urlparse(url)
    except ValueError:
        return "<unparseable DATABASE_URL>"
    if not parsed.hostname:  # e.g. sqlite:///./local.db — no credentials to strip
        return url
    host = parsed.hostname
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path}"


def require_destructive_confirmation(what_it_destroys: str, argv: list[str] | None = None) -> None:
    """
    Abort unless the caller passed `--yes` AND set `ALLOW_DESTRUCTIVE=1`.

    `what_it_destroys` is a plain-English description of the damage, shown to
    the operator before they can proceed (and in the abort message, so a
    mistaken run still explains what it would have done).
    """
    argv = sys.argv if argv is None else argv
    script = os.path.basename(argv[0]) if argv else "<script>"
    target = _safe_target()

    has_flag = "--yes" in argv
    has_env = os.getenv("ALLOW_DESTRUCTIVE", "").strip() == "1"

    if has_flag and has_env:
        print("=" * 72)
        print(f"DESTRUCTIVE: {script}")
        print(f"  target : {target}")
        print(f"  effect : {what_it_destroys}")
        print("  confirmed via --yes + ALLOW_DESTRUCTIVE=1 — proceeding.")
        print("=" * 72)
        return

    missing = []
    if not has_flag:
        missing.append("the --yes flag")
    if not has_env:
        missing.append("ALLOW_DESTRUCTIVE=1 in the environment")

    print("=" * 72, file=sys.stderr)
    print(f"[ABORT] {script} is destructive and was not confirmed.", file=sys.stderr)
    print(f"  target : {target}", file=sys.stderr)
    print(f"  effect : {what_it_destroys}", file=sys.stderr)
    print(f"  missing: {' and '.join(missing)}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Nothing was written. Check the target above is NOT production, then:", file=sys.stderr)
    print(f"      ALLOW_DESTRUCTIVE=1 py execution/{script} --yes", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    sys.exit(1)


def require_write_confirmation(what_it_writes: str, argv: list[str] | None = None) -> None:
    """
    Lighter gate for scripts that WRITE but do not destroy.

    Nine scripts in `execution/` insert, update, or create schema against
    whatever `DATABASE_URL` is in `backend/.env` — which, per this module's
    docstring, is the live Neon Postgres — with no confirmation at all. They
    aren't destructive enough to deserve the two-factor gate above (nothing is
    dropped or mass-deleted), but "I didn't realise that would hit production"
    is just as easy here, and a stray `deploy_schema.py` or `migrate_orders.py`
    still mutates the live database.

    So this requires ONE affirmation (`--yes`) rather than two, and always shows
    the resolved target and environment first. The point is not to make the
    script hard to run; it is to make it impossible to run without having seen
    which database you are pointing at.
    """
    argv = sys.argv if argv is None else argv
    script = os.path.basename(argv[0]) if argv else "<script>"
    target = _safe_target()
    env = _current_env()

    if "--yes" in argv:
        print("=" * 72)
        print(f"WRITES DATA: {script}")
        print(f"  target : {target}")
        print(f"  env    : {env}")
        print(f"  effect : {what_it_writes}")
        print("  confirmed via --yes — proceeding.")
        print("=" * 72)
        return

    print("=" * 72, file=sys.stderr)
    print(f"[ABORT] {script} writes to the database and was not confirmed.", file=sys.stderr)
    print(f"  target : {target}", file=sys.stderr)
    print(f"  env    : {env}", file=sys.stderr)
    print(f"  effect : {what_it_writes}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Nothing was written. Check the target above, then re-run with --yes:", file=sys.stderr)
    print(f"      py execution/{script} --yes", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    sys.exit(1)


def require_non_production(reason: str = "") -> None:
    """
    Refuse to run at all when the resolved environment is production.

    For scripts that are only ever meant for local/demo data — seeding fake
    orders, provisioning showcase logins, resetting a known password. `--yes`
    cannot override this: the answer to "should this run against production" is
    no, not "confirm harder".
    """
    env = _current_env()
    if env != "production":
        return

    script = os.path.basename(sys.argv[0]) if sys.argv else "<script>"
    print("=" * 72, file=sys.stderr)
    print(f"[ABORT] {script} must never run against production.", file=sys.stderr)
    print(f"  target : {_safe_target()}", file=sys.stderr)
    print(f"  env    : {env}", file=sys.stderr)
    if reason:
        print(f"  reason : {reason}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Point DATABASE_URL at a non-production database and try again.", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    sys.exit(1)
