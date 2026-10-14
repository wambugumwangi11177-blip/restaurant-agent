"""
Company OS entry point. Departments (ai/company_os/departments) own the work; this
runs them in order, isolating failures so one broken department never stops the rest.
Agents only ever call kernel.propose(); nothing here executes a tool directly.
"""
import logging

import feature_flags
from . import kernel, tools  # noqa: F401 - importing tools registers them
from .departments import DEPARTMENTS, customer_success

logger = logging.getLogger("company_os")

# Kept for callers/tests that used the first two agents directly.
client_success_agent = customer_success.health_agent


def digest_agent(db) -> list:
    return [kernel.propose(db, "executive.digest_agent", "scorecard_digest", {}, "Daily company scorecard digest")]


def run_company_cycle(db, today=None) -> dict:
    """The daily loop. No-op unless FEATURE_COMPANY_OS is on."""
    if not feature_flags.is_enabled("company_os"):
        return {"ran": False, "reason": "company_os flag off"}
    made, errors = [], {}
    for dept in DEPARTMENTS:
        try:
            made += dept.run(db, today)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors[dept.NAME] = str(exc)[:200]
            logger.error("[company_os] department %s failed: %s", dept.NAME, exc, exc_info=True)
    return {"ran": True, "proposals": len(made),
            "executed": sum(1 for p in made if p.status == "executed"),
            "pending": sum(1 for p in made if p.status == "pending"),
            "department_errors": errors}
