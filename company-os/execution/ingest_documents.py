"""Ingest .md/.txt files (or whole folders) into a workspace's company memory.

Usage:
  python execution/ingest_documents.py --workspace acme docs/ handbook.md
Idempotent: unchanged files are skipped (same content = same document).
Actions are attributed to the workspace's first founder in the audit log.
"""

import argparse
import sys
from pathlib import Path

import _common  # noqa: F401
from sqlalchemy import select

from app.db import session_factory
from app.kernel.evals import doc_title
from app.kernel.memory.service import ingest_text
from app.kernel.models import Membership, Role, Workspace
from app.kernel.tenancy import Principal

SUFFIXES = {".md", ".markdown", ".txt"}


def founder_principal(db, slug: str) -> Principal:
    ws = db.execute(select(Workspace).where(Workspace.slug == slug)).scalar_one_or_none()
    if ws is None:
        raise SystemExit(f"No workspace {slug!r}")
    m = db.execute(select(Membership).where(Membership.workspace_id == ws.id, Membership.role == Role.FOUNDER.value)
                   .order_by(Membership.id)).scalars().first()
    return Principal(user_id=m.user_id, workspace_id=ws.id, role=m.role)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args()
    files: list[Path] = []
    for p in map(Path, a.paths):
        files += sorted(f for f in p.rglob("*") if f.suffix.lower() in SUFFIXES) if p.is_dir() else [p]
    db = session_factory()()
    try:
        principal = founder_principal(db, a.workspace)
        created = skipped = failed = 0
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
                doc, new = ingest_text(db, principal, doc_title(text, f.stem), text, source=str(f))
                db.commit()
                created += new
                skipped += not new
                print(("added   " if new else "skipped ") + f"{f} -> document {doc.id}")
            except Exception as e:  # noqa: BLE001 — report and continue with the next file
                db.rollback()
                failed += 1
                print(f"FAILED  {f}: {e}", file=sys.stderr)
        print(f"\n{created} added, {skipped} unchanged, {failed} failed")
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
