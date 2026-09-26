"""Run the retrieval eval.

Default: ingest the OS's own directives + ADRs into a throwaway workspace INSIDE
a transaction that is rolled back (nothing persists), run
evals/retrieval/kernel_docs.jsonl, compare with baseline.json. Exit 1 below it.

Against your live memory (read-only):
  python execution/run_evals.py --workspace acme --cases evals/retrieval/company_docs.jsonl [--min 0.8]
"""

import argparse
import json
import sys
from pathlib import Path

import _common  # noqa: F401
from sqlalchemy import select

from app.db import session_factory
from app.kernel.evals import EVALS_DIR, baseline, ingest_files, kernel_corpus_files, load_cases, run_retrieval_eval
from app.kernel.models import Membership, User, Workspace
from app.kernel.tenancy import Principal
from app.security import hash_password


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", help="evaluate this workspace's existing memory instead of the kernel corpus")
    ap.add_argument("--cases", type=Path)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--min", type=float, help="minimum hit rate (default: baseline.json for the kernel corpus, 0.8 otherwise)")
    a = ap.parse_args()

    db = session_factory()()
    try:
        if a.workspace:
            ws = db.execute(select(Workspace).where(Workspace.slug == a.workspace)).scalar_one_or_none()
            if ws is None:
                raise SystemExit(f"No workspace {a.workspace!r}")
            cases = load_cases(a.cases or EVALS_DIR / "company_docs.jsonl")
            if not cases:
                raise SystemExit("No cases yet: add 20+ lines to evals/retrieval/company_docs.jsonl")
            result = run_retrieval_eval(db, ws.id, cases, a.k)
            floor = a.min if a.min is not None else 0.8
        else:
            ws = Workspace(slug="eval-scratch", name="Eval scratch")
            user = User(email="eval-scratch@example.com", full_name="Eval", password_hash=hash_password("x"))
            db.add_all([ws, user])
            db.flush()
            db.add(Membership(workspace_id=ws.id, user_id=user.id, role="founder"))
            principal = Principal(user_id=user.id, workspace_id=ws.id, role="founder")
            ingest_files(db, principal, kernel_corpus_files())
            result = run_retrieval_eval(db, ws.id, load_cases(a.cases or EVALS_DIR / "kernel_docs.jsonl"), a.k)
            floor = a.min if a.min is not None else baseline()
    finally:
        db.rollback()  # never persist anything from an eval run
        db.close()

    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    ok = result.hit_rate >= floor
    print(f"\nhit rate {result.hit_rate:.3f} (floor {floor:.3f}) -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
