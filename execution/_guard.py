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
