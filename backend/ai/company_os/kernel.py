"""
Company OS Kernel.

One mechanism governs every agent action (report: "an approval log, a threshold,
and authority widened one action at a time when the evidence supports it"):

  READ       run immediately; nothing is written.
  INTERNAL   run immediately, but always recorded (e.g. a digest to the operator).
  EXTERNAL   touches a customer. Waits as a Proposal until the tool has earned
             autonomy: AUTONOMY_THRESHOLD consecutive approvals with NO edit.
             An edit, a rejection or a failure resets the streak and demotes it.
  RESTRICTED money out, deletions, new contacts, policy statements. Always waits;
             can never earn autonomy.

Kill switch: FEATURE_COMPANY_OS_AUTONOMY=false puts everything with a side
effect into draft-only mode. Agents never execute anything outside this module.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

import feature_flags
import models
from time_utils import utcnow

logger = logging.getLogger("company_os")

AUTONOMY_THRESHOLD = 20

READ, INTERNAL, EXTERNAL, RESTRICTED = "read", "internal", "external", "restricted"
_TIERS = {READ, INTERNAL, EXTERNAL, RESTRICTED}


@dataclass(frozen=True)
class Tool:
    name: str
    tier: str
    run: Callable[[Session, dict], dict]
    description: str = ""


_REGISTRY: dict[str, Tool] = {}


def register(name: str, tier: str, description: str = ""):
    """Decorator registering `run(db, payload) -> dict` as a governed tool."""
    if tier not in _TIERS:
        raise ValueError(f"unknown tier {tier!r}")

    def deco(fn):
        _REGISTRY[name] = Tool(name, tier, fn, description)
        return fn
    return deco


def get_tool(name: str) -> Tool:
    if name not in _REGISTRY:
        raise KeyError(f"unknown tool {name!r}")
    return _REGISTRY[name]


def tools() -> list[Tool]:
    return list(_REGISTRY.values())


def _autonomy_row(db: Session, tool: str) -> models.CompanyToolAutonomy:
    row = db.get(models.CompanyToolAutonomy, tool)
    if row is None:
        row = models.CompanyToolAutonomy(tool=tool, streak=0, autonomous=False)
        db.add(row)
        db.flush()
    return row


def is_autonomous(db: Session, tool: Tool) -> bool:
    if tool.tier != EXTERNAL:
        return False
    row = db.get(models.CompanyToolAutonomy, tool.name)
    return bool(row and row.autonomous)


def _execute(db: Session, proposal: models.CompanyProposal, tool: Tool, payload: dict) -> None:
    try:
        result = tool.run(db, payload)
        proposal.status = "executed"
        proposal.result = json.dumps(result, default=str)
        proposal.error = None
    except Exception as exc:  # noqa: BLE001 - recorded, never raised into the scheduler
        logger.warning("[company_os] tool %s failed: %s", tool.name, exc)
        proposal.status = "failed"
        proposal.error = str(exc)[:500]
        if tool.tier == EXTERNAL:
            row = _autonomy_row(db, tool.name)
            row.streak, row.autonomous, row.updated_at = 0, False, utcnow()
    proposal.decided_at = utcnow()


def propose(
    db: Session, agent: str, tool_name: str, payload: dict, summary: str,
    restaurant_id: int | None = None,
) -> models.CompanyProposal:
    """The only way an agent acts. Returns the recorded proposal (any status)."""
    tool = get_tool(tool_name)
    proposal = models.CompanyProposal(
        agent=agent, tool=tool.name, tier=tool.tier, summary=summary[:250],
        payload=json.dumps(payload, default=str), restaurant_id=restaurant_id,
        status="pending",
    )
    db.add(proposal)
    db.flush()

    draft_only = not feature_flags.is_enabled("company_os_autonomy")
    if tool.tier == READ:
        auto = True
    elif draft_only:
        auto = False
    elif tool.tier == INTERNAL:
        auto = True
    elif tool.tier == EXTERNAL:
        auto = is_autonomous(db, tool)
    else:
        auto = False

    if auto:
        proposal.auto_executed = True
        _execute(db, proposal, tool, payload)
    db.commit()
    return proposal


def decide(
    db: Session, proposal_id: int, approve: bool, user: models.User,
    edited_payload: dict | None = None,
) -> models.CompanyProposal:
    proposal = db.get(models.CompanyProposal, proposal_id)
    if proposal is None:
        raise LookupError("proposal not found")
    if proposal.status != "pending":
        raise ValueError(f"proposal is already {proposal.status}")
    tool = get_tool(proposal.tool)
    proposal.decided_by_id = user.id

    if not approve:
        proposal.status = "rejected"
        proposal.decided_at = utcnow()
        if tool.tier == EXTERNAL:
            row = _autonomy_row(db, tool.name)
            row.streak, row.autonomous, row.updated_at = 0, False, utcnow()
        db.commit()
        return proposal

    payload = json.loads(proposal.payload)
    edited = edited_payload is not None and edited_payload != payload
    if edited:
        payload = edited_payload
        proposal.payload = json.dumps(payload, default=str)
        proposal.edited = True
    _execute(db, proposal, tool, payload)

    if tool.tier == EXTERNAL and proposal.status == "executed":
        row = _autonomy_row(db, tool.name)
        row.streak = 0 if edited else row.streak + 1
        if row.streak >= AUTONOMY_THRESHOLD:
            row.autonomous = True
        row.updated_at = utcnow()
    db.commit()
    return proposal


def revoke_autonomy(db: Session, tool_name: str) -> None:
    row = _autonomy_row(db, tool_name)
    row.streak, row.autonomous, row.updated_at = 0, False, utcnow()
    db.commit()


def status(db: Session) -> dict:
    rows = {r.tool: r for r in db.query(models.CompanyToolAutonomy).all()}
    return {
        "enabled": feature_flags.is_enabled("company_os"),
        "draft_only": not feature_flags.is_enabled("company_os_autonomy"),
        "threshold": AUTONOMY_THRESHOLD,
        "pending": db.query(models.CompanyProposal).filter_by(status="pending").count(),
        "tools": [
            {"name": t.name, "tier": t.tier, "description": t.description,
             "streak": rows[t.name].streak if t.name in rows else 0,
             "autonomous": bool(rows[t.name].autonomous) if t.name in rows else False}
            for t in tools()
        ],
    }
