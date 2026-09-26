"""
app/kernel/approvals.py
───────────────────────
Proposal lifecycle for EXTERNAL actions:

  pending ──approve──▶ approved ──execute──▶ executed | failed
     └────reject────▶ rejected

Every decision writes a Feedback row (approved / edited / rejected + reason).
That table is what "learning" means in this OS: it feeds eval cases and the
autonomy streak below — never model weights.

Autonomy: a tool may be auto-approved only if the founder switched it on for
the workspace (ToolPolicy.auto_approve_enabled) AND its most recent human
decisions are an unbroken streak of `streak_threshold` un-edited approvals.
Any rejection or edit resets the streak to zero. Off by default.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kernel.agents.tools import TOOLS, Effect, InvalidToolArgs, Tool, ToolContext, execute_tool, validate_args
from app.kernel.audit import write_audit
from app.kernel.events import emit
from app.kernel.models import Feedback, Proposal, ToolPolicy
from app.kernel.tenancy import Principal, get_or_404, scoped


def _now() -> datetime:
    return datetime.now(timezone.utc)


def approval_streak(db: Session, workspace_id: int, tool_name: str) -> int:
    """Consecutive most-recent human approvals without edits. Auto-approved
    proposals are ignored: autonomy must be earned from human decisions only."""
    rows = db.execute(
        scoped(Proposal, workspace_id)
        .where(Proposal.tool_name == tool_name, Proposal.decided_at.is_not(None), Proposal.auto_approved.is_(False))
        .order_by(Proposal.decided_at.desc(), Proposal.id.desc())
        .limit(500)
    ).scalars()
    streak = 0
    for p in rows:
        if p.status == "rejected" or p.edited:
            break
        streak += 1
    return streak


def get_policy(db: Session, workspace_id: int, tool_name: str) -> ToolPolicy | None:
    return db.execute(
        scoped(ToolPolicy, workspace_id).where(ToolPolicy.tool_name == tool_name)
    ).scalar_one_or_none()


def auto_approval_allowed(db: Session, workspace_id: int, tool_name: str) -> bool:
    policy = get_policy(db, workspace_id, tool_name)
    if policy is None or not policy.auto_approve_enabled:
        return False
    return approval_streak(db, workspace_id, tool_name) >= policy.streak_threshold


def create_proposal(ctx: ToolContext, tool: Tool, args: dict) -> Proposal:
    db, p = ctx.db, ctx.principal
    summary = tool.summarize(args) if tool.summarize else f"{tool.name}({', '.join(sorted(args))})"
    proposal = Proposal(
        workspace_id=p.workspace_id,
        agent_run_id=ctx.agent_run_id,
        tool_name=tool.name,
        args=args,
        summary=summary,
        requested_by_user_id=p.user_id,
    )
    db.add(proposal)
    db.flush()
    write_audit(db, action="proposal.create", workspace_id=p.workspace_id, entity_type="proposal",
                entity_id=proposal.id, changes={"tool_name": tool.name}, actor_user_id=p.user_id,
                actor_agent_run_id=ctx.agent_run_id)
    emit(db, "proposal.created", workspace_id=p.workspace_id, entity_type="proposal", entity_id=proposal.id,
         payload={"tool_name": tool.name, "summary": summary}, actor_user_id=p.user_id,
         actor_agent_run_id=ctx.agent_run_id)

    if auto_approval_allowed(db, p.workspace_id, tool.name):
        proposal.status = "approved"
        proposal.auto_approved = True
        proposal.final_args = args
        proposal.decided_at = _now()
        write_audit(db, action="proposal.auto_approve", workspace_id=p.workspace_id, entity_type="proposal",
                    entity_id=proposal.id, changes={"tool_name": tool.name})
        emit(db, "proposal.approved", workspace_id=p.workspace_id, entity_type="proposal", entity_id=proposal.id,
             payload={"auto": True})
        _execute(db, p, proposal)
    return proposal


def _execute(db: Session, principal: Principal, proposal: Proposal) -> Proposal:
    ctx = ToolContext(db=db, principal=principal, agent_run_id=proposal.agent_run_id, approval_id=proposal.id)
    outcome = execute_tool(ctx, proposal.tool_name, dict(proposal.final_args or {}))
    proposal.executed_at = _now()
    if outcome["status"] == "ok":
        proposal.status = "executed"
        proposal.result = outcome.get("result")
        event = "proposal.executed"
    else:
        proposal.status = "failed"
        proposal.error = outcome.get("error", "unknown error")
        event = "proposal.failed"
    db.flush()
    write_audit(db, action=event, workspace_id=principal.workspace_id, entity_type="proposal", entity_id=proposal.id,
                changes={"status": proposal.status}, actor_user_id=principal.user_id)
    emit(db, event, workspace_id=principal.workspace_id, entity_type="proposal", entity_id=proposal.id,
         payload={"tool_name": proposal.tool_name, "error": proposal.error}, actor_user_id=principal.user_id)
    return proposal


def decide(
    db: Session,
    principal: Principal,
    proposal_id: int,
    verdict: str,
    reason: str | None = None,
    edited_args: dict | None = None,
) -> Proposal:
    proposal = get_or_404(db, Proposal, proposal_id, principal.workspace_id)
    # Row lock: two concurrent approvals of the same proposal must not both execute it.
    db.execute(select(Proposal.id).where(Proposal.id == proposal.id).with_for_update())
    db.refresh(proposal)
    if proposal.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Proposal is already {proposal.status}")
    tool = TOOLS.get(proposal.tool_name)
    if tool is None or tool.effect is not Effect.EXTERNAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "Proposal refers to a tool that no longer exists")

    proposal.decided_by_user_id = principal.user_id
    proposal.decided_at = _now()
    proposal.decision_reason = reason

    if verdict == "reject":
        if not reason or not reason.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "A reason is required when rejecting — it is the signal the OS learns from")
        proposal.status = "rejected"
        fb_verdict = "rejected"
        event = "proposal.rejected"
    elif verdict == "approve":
        final = proposal.args
        if edited_args is not None and edited_args != proposal.args:
            try:
                final = validate_args(tool.input_schema, edited_args)
            except InvalidToolArgs as e:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
            proposal.edited = True
        proposal.final_args = final
        proposal.status = "approved"
        fb_verdict = "edited" if proposal.edited else "approved"
        event = "proposal.approved"
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "verdict must be 'approve' or 'reject'")

    db.add(Feedback(
        workspace_id=principal.workspace_id, target_type="proposal", target_id=proposal.id, verdict=fb_verdict,
        reason=reason, correction=None if not proposal.edited else str(proposal.final_args), user_id=principal.user_id,
    ))
    db.flush()
    write_audit(db, action=f"proposal.{verdict}", workspace_id=principal.workspace_id, entity_type="proposal",
                entity_id=proposal.id, changes={"status": proposal.status, "edited": proposal.edited},
                actor_user_id=principal.user_id)
    emit(db, event, workspace_id=principal.workspace_id, entity_type="proposal", entity_id=proposal.id,
         payload={"tool_name": proposal.tool_name, "edited": proposal.edited}, actor_user_id=principal.user_id)

    if proposal.status == "approved":
        _execute(db, principal, proposal)
    return proposal


def set_policy(db: Session, principal: Principal, tool_name: str, enabled: bool, threshold: int) -> ToolPolicy:
    tool = TOOLS.get(tool_name)
    if tool is None or tool.effect is not Effect.EXTERNAL:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Autonomy policies apply to EXTERNAL tools only")
    if threshold < 5:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "streak_threshold must be at least 5")
    policy = get_policy(db, principal.workspace_id, tool_name)
    if policy is None:
        policy = ToolPolicy(workspace_id=principal.workspace_id, tool_name=tool_name)
        db.add(policy)
    before = {"auto_approve_enabled": policy.auto_approve_enabled, "streak_threshold": policy.streak_threshold}
    policy.auto_approve_enabled = enabled
    policy.streak_threshold = threshold
    policy.updated_at = _now()
    db.flush()
    write_audit(db, action="autonomy.set", workspace_id=principal.workspace_id, entity_type="tool_policy",
                entity_id=policy.id, changes={"tool_name": tool_name, "from": before,
                                              "to": {"auto_approve_enabled": enabled, "streak_threshold": threshold}},
                actor_user_id=principal.user_id)
    return policy
