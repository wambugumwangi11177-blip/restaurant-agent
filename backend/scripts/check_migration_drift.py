"""
backend/scripts/check_migration_drift.py
------------------------------------------
Fail-fast preflight: detect when the database's Alembic revision stamp
references a migration that does not exist in this build's migration
history -- i.e. the database schema is AHEAD of the deployed code.

Why this exists (see docs/postmortems/2026-07-11-schema-ahead-of-code.md):
on 2026-07-11 a non-production boot had DATABASE_URL pointed at the
production database and ran `alembic upgrade head` from a branch whose
migrations had not been merged or deployed yet. The database ended up
stamped to a revision that the deployed branch's migration chain had
never heard of. The next real deploy then failed `alembic upgrade head`
on every boot attempt with Alembic's raw

    Can't locate revision identified by '<revision>'

which gives no hint about the actual cause. Diagnosing it cost real
downtime.

This script runs as its own step in the Dockerfile CMD chain, BEFORE
`alembic upgrade head` -- deliberately, because the crash it is guarding
against happens *inside* that command itself. By the time any in-process
Python check (e.g. startup_checks.py, which runs inside main.py) would
run, Alembic has already crashed and the container is dead. This script
never modifies the database; it only reads the current stamp and reports.

If this fires, the fix is almost always: deploy the code that matches
(or is newer than) the database's stamp. Do NOT downgrade or re-stamp
the database -- the physical schema the stamp refers to is real; only
the deployed code is stale. See the postmortem above for the full
reasoning on why "fix code up to schema" beats "force schema down to
code" once real constraints are involved.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic.config import Config
from alembic.script import ScriptDirectory

from database import engine


def main() -> int:
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_ini = os.path.join(backend_dir, "alembic.ini")

    if not os.path.exists(alembic_ini):
        # Defensive: if the layout ever changes, don't block boot on this
        # check -- fall through and let `alembic upgrade head` be the
        # source of truth.
        return 0

    cfg = Config(alembic_ini)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    script = ScriptDirectory.from_config(cfg)
    known_revisions = {rev.revision for rev in script.walk_revisions()}

    try:
        with engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ).fetchone()
    except Exception:
        # alembic_version doesn't exist yet (fresh database) -- nothing to
        # check; `alembic upgrade head` will create and stamp it normally.
        return 0
    finally:
        engine.dispose()

    if row is None:
        return 0

    db_revision = row[0]

    if db_revision not in known_revisions:
        sys.stderr.write(
            "\n" + "=" * 78 + "\n"
            "[FATAL] Database schema is AHEAD of this build's code.\n\n"
            "  Database alembic_version: " + repr(db_revision) + "\n"
            "  This revision does not exist in this build's migration\n"
            "  history (backend/alembic/versions/).\n\n"
            "  This almost always means migrations from a DIFFERENT,\n"
            "  newer branch were already run against THIS database --\n"
            "  e.g. a local or CI boot had DATABASE_URL pointed at this\n"
            "  database and ran `alembic upgrade head` from code that\n"
            "  isn't deployed here yet.\n\n"
            "  DO NOT downgrade or re-stamp this database to fix this.\n"
            "  The physical schema is real and correct; only the\n"
            "  deployed code is stale. Deploy the code that matches (or\n"
            "  exceeds) this revision instead.\n\n"
            "  See docs/postmortems/2026-07-11-schema-ahead-of-code.md\n"
            + "=" * 78 + "\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
