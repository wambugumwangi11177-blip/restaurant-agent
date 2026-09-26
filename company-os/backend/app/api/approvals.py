"""
app/api/approvals.py
────────────────────
The approval inbox. Agents *and people* propose EXTERNAL actions through the
same gate; only founders decide. Autonomy policies (per tool) are managed here.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import require
from app.db import get_db
from app.kernel import approvals
from app.kernel.agents.tools import TOOLS, Effect, ToolContext, execute_tool
from app.kernel.models import Proposal
from app.kernel.tenancy import Principal, get_or_404, scoped

router = APIRouter()


def proposal_out(p: Proposal) -> dict:
    return {
        "id": p.id, "tool": p.tool_name, "summary": p.summary, "status": p.status, "args": p.args,
        "final_args": p.final_args, "edited": p.edited, "auto_approved": p.auto_approved,
        "agent_run_id": p.agent_run_id, "requested_by_user_id": p.requested_by_user_id,
        "decided_by_user_id": p.decided_by_user_id, "decision_reason": p.decision_reason,
        "decided_at": p.decided_at.isoformat() if p.decided_at else None,
        "executed_at": p.executed_at.isoformat() if p.executed_at else None,
        "result": p.result, "error": p.error, "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("/approvals")
def list_proposals(
    status_: Literal["pending", "approved", "rejected", "executed", "failed", "all"] = Query(default="pending", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require("approvals.read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = scoped(Proposal, principal.workspace_id)
    if status_ != "all":
        stmt = stmt.where(Proposal.status == status_)
    return [proposal_out(p) for p in db.execute(stmt.order_by(Proposal.id.desc()).limit(limit)).scalars()]


@router.get("/approvals/{proposal_id}")
def get_proposal(proposal_id: int, principal: Principal = Depends(require("approvals.read")),
                 db: Session = Depends(get_db)) -> dict:
    return proposal_out(get_or_404(db, Proposal, proposal_id, principal.workspace_id))


class ProposeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    args: dict


@router.post("/approvals", status_code=201)
def propose(body: ProposeIn, principal: Principal = Depends(require("approvals.propose")),
            db: Session = Depends(get_db)) -> dict:
    tool = TOOLS.get(body.tool)
    if tool is None or tool.effect is not Effect.EXTERNAL:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only EXTERNAL tools are proposed through the inbox")
    outcome = execute_tool(ToolContext(db=db, principal=principal), body.tool, body.args)
    if outcome["status"] in ("denied", "error"):
        db.commit()  # keep the tool_calls record of the refused attempt
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, outcome.get("error"))
    db.commit()
    return proposal_out(get_or_404(db, Proposal, outcome["proposal_id"], principal.workspace_id))


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=2000)
    edited_args: dict | None = None


@router.post("/approvals/{proposal_id}/decide")
def decide(proposal_id: int, body: DecideIn, principal: Principal = Depends(require("approvals.decide")),
           db: Session = Depends(get_db)) -> dict:
    p = approvals.decide(db, principal, proposal_id, body.verdict, body.reason, body.edited_args)
    db.commit()
    return proposal_out(p)


@router.get("/approvals-policies")
def list_policies(principal: Principal = Depends(require("approvals.read")), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for name, tool in TOOLS.items():
        if tool.effect is not Effect.EXTERNAL:
            continue
        policy = approvals.get_policy(db, principal.workspace_id, name)
        out.append({
            "tool": name,
            "auto_approve_enabled": bool(policy and policy.auto_approve_enabled),
            "streak_threshold": policy.streak_threshold if policy else 20,
            "current_streak": approvals.approval_streak(db, principal.workspace_id, name),
        })
    return out


class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_approve_enabled: bool
    streak_threshold: int = Field(default=20, ge=5, le=1000)


@router.put("/approvals-policies/{tool_name}")
def set_policy(tool_name: str, body: PolicyIn, principal: Principal = Depends(require("autonomy.manage")),
               db: Session = Depends(get_db)) -> dict:
    policy = approvals.set_policy(db, principal, tool_name, body.auto_approve_enabled, body.streak_threshold)
    db.commit()
    return {"tool": tool_name, "auto_approve_enabled": policy.auto_approve_enabled,
            "streak_threshold": policy.streak_threshold,
            "current_streak": approvals.approval_streak(db, principal.workspace_id, tool_name)}
