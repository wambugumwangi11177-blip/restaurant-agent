"""Run scheduled department jobs (for cron / a Railway cron service).

Usage:
  python execution/run_jobs.py daily_brief                  # every workspace with the department enabled
  python execution/run_jobs.py sla_check --workspace acme
  python execution/run_jobs.py --list
Suggested schedule (times in the workspace's zone; see each job's hint in --list):
  daily_brief 07:00 · collections_check 08:00 · obligations_check 08:00 · sla_check every 15 min
Each workspace runs in its own transaction; one failing workspace does not stop the others.
"""

import argparse
import sys

import _common  # noqa: F401
from sqlalchemy import select

from app.db import session_factory
from app.kernel.audit import write_audit
from app.kernel.departments import JOBS
from app.kernel.models import Workspace
from app.kernel.workspaces import department_enabled
from app.main import bootstrap


def main() -> int:
    bootstrap()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", nargs="?")
    ap.add_argument("--workspace")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.job:
        for j in JOBS.values():
            print(f"{j.name:20} {j.department:10} {j.schedule_hint}")
        return 0
    job = JOBS.get(a.job)
    if job is None:
        print(f"Unknown job {a.job!r}; use --list", file=sys.stderr)
        return 2
    db = session_factory()()
    failures = 0
    try:
        stmt = select(Workspace).order_by(Workspace.id)
        if a.workspace:
            stmt = stmt.where(Workspace.slug == a.workspace)
        for ws in db.execute(stmt).scalars().all():
            if not department_enabled(db, ws.id, job.department):
                continue
            try:
                summary = job.fn(db, ws.id)
                write_audit(db, action="job.run", workspace_id=ws.id, entity_type="job",
                            changes={"job": job.name, "summary": summary[:500], "manual": False})
                db.commit()
                print(f"{ws.slug}: {summary}")
            except Exception as e:  # noqa: BLE001 — report and continue with the next workspace
                db.rollback()
                failures += 1
                print(f"{ws.slug}: FAILED {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        db.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
