"""
Company agents. They only ever call kernel.propose(); they never execute.
Deterministic planners: drafts are templated from recorded facts, so there is
nothing for a model (or a customer message) to invent or inject.
"""
from datetime import timedelta

import models
from time_utils import utcnow
from ai.continuity.scorecard import platform_scorecard
from . import kernel, tools  # noqa: F401 - importing tools registers them

CHECKIN_COOLDOWN_DAYS = 7


def _recent_checkin(db, restaurant_id: int) -> bool:
    since = utcnow() - timedelta(days=CHECKIN_COOLDOWN_DAYS)
    return db.query(models.CompanyProposal).filter(
        models.CompanyProposal.tool == "client_checkin",
        models.CompanyProposal.restaurant_id == restaurant_id,
        models.CompanyProposal.status.in_(["pending", "executed"]),
        models.CompanyProposal.created_at >= since,
    ).first() is not None


def digest_agent(db) -> list:
    return [kernel.propose(db, "digest_agent", "scorecard_digest", {}, "Daily company scorecard digest")]


def client_success_agent(db) -> list:
    """Draft a check-in for each red restaurant (once per cooldown window)."""
    out = []
    for r in platform_scorecard(db)["restaurants"]:
        if r["status"] != "red" or _recent_checkin(db, r["restaurant_id"]):
            continue
        reasons = "; ".join(r["reasons"]) or "activity looks low"
        message = (f"Hi, we noticed {reasons} at {r['name']}. "
                   "Is anything blocking you? Reply here and we'll help get you back on track.")
        out.append(kernel.propose(
            db, "client_success_agent", "client_checkin",
            {"restaurant_id": r["restaurant_id"], "message": message},
            f"Check in with {r['name']} (health {r['score']})",
            restaurant_id=r["restaurant_id"]))
    return out


def run_company_cycle(db) -> dict:
    """The daily loop. No-op unless FEATURE_COMPANY_OS is on."""
    import feature_flags
    if not feature_flags.is_enabled("company_os"):
        return {"ran": False, "reason": "company_os flag off"}
    made = digest_agent(db) + client_success_agent(db)
    return {"ran": True, "proposals": len(made),
            "executed": sum(1 for p in made if p.status == "executed"),
            "pending": sum(1 for p in made if p.status == "pending")}
