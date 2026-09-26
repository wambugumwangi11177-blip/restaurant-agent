"""Turn human feedback into candidate eval cases (the 'learning' loop).

Writes every rejected/edited proposal and every 'unhelpful' agent run with its
reason and correction to .tmp/feedback_cases.jsonl. Review them, then promote
the good ones into an eval set. Nothing is promoted automatically: a person
decides what the OS should learn.

Usage: python execution/export_feedback_evals.py --workspace acme [--out .tmp/feedback_cases.jsonl]
"""

import argparse
import json
import sys
from pathlib import Path

import _common  # noqa: F401
from sqlalchemy import select

from app.db import session_factory
from app.kernel.models import AgentRun, Feedback, Proposal, Workspace

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--out", type=Path, default=ROOT / ".tmp" / "feedback_cases.jsonl")
    a = ap.parse_args()
    db = session_factory()()
    try:
        ws = db.execute(select(Workspace).where(Workspace.slug == a.workspace)).scalar_one_or_none()
        if ws is None:
            raise SystemExit(f"No workspace {a.workspace!r}")
        rows = db.execute(select(Feedback).where(
            Feedback.workspace_id == ws.id, Feedback.verdict.in_(["rejected", "edited", "unhelpful"])
        ).order_by(Feedback.id)).scalars().all()
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", encoding="utf-8") as f:
            for fb in rows:
                case = {"feedback_id": fb.id, "verdict": fb.verdict, "reason": fb.reason, "correction": fb.correction}
                if fb.target_type == "proposal":
                    p = db.get(Proposal, fb.target_id)
                    case.update(kind="proposal", tool=p.tool_name, proposed=p.args, final=p.final_args)
                    if p.agent_run_id:
                        run = db.get(AgentRun, p.agent_run_id)
                        case.update(agent=run.agent_name, input=run.input.get("text"))
                else:
                    run = db.get(AgentRun, fb.target_id)
                    case.update(kind="agent_run", agent=run.agent_name, input=run.input.get("text"), output=run.output)
                f.write(json.dumps(case, ensure_ascii=False, default=str) + "\n")
        print(f"Wrote {len(rows)} candidate cases to {a.out}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
