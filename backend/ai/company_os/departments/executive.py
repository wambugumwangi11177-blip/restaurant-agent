"""Chief of staff: one daily brief so the operator reads one thing, not six."""
import models
from time_utils import utcnow
from ai.continuity.scorecard import platform_scorecard
from .. import kernel, tools  # noqa: F401

NAME = "executive"


def founder_load(db) -> dict:
    """Items that still need a human. The report's headline number: it should fall over time."""
    pending = db.query(models.CompanyProposal).filter_by(status="pending").all()
    failed = db.query(models.CompanyProposal).filter_by(status="failed").count()
    by_dept: dict[str, int] = {}
    for p in pending:
        by_dept[p.agent.split(".")[0]] = by_dept.get(p.agent.split(".")[0], 0) + 1
    return {"pending": len(pending), "failed": failed, "by_department": by_dept}


def run(db, today=None):
    out = []
    card = platform_scorecard(db)
    load = founder_load(db)
    s = card["summary"]
    lines = [f"{s['red']} red / {s['amber']} amber / {s['green']} green restaurants.",
             f"{load['pending']} actions awaiting your approval, {load['failed']} failed."]
    if load["by_department"]:
        lines.append("Waiting by department: " + ", ".join(f"{k} {v}" for k, v in sorted(load["by_department"].items())) + ".")
    if s["needs_human_call"]:
        lines.append("More than 20% of restaurants are red - a human call is warranted.")
    out.append(kernel.propose(
        db, "executive.chief_of_staff", "chief_of_staff_brief",
        {"title": f"Daily brief: {load['pending']} awaiting you", "body": " ".join(lines)},
        f"Daily brief {utcnow():%Y-%m-%d}"))
    return out
