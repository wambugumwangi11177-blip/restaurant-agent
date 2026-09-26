"""
app/kernel/agents/builtin_agents.py
───────────────────────────────────
Phase 0 agents. Each has a directive in company-os/directives/agents/.

  echo       deterministic — proves the runtime end to end
  status     deterministic — the "what needs me right now" summary (WhatsApp: "status")
  memory_qa  LLM + search_memory — answers from company documents with citations;
             without an LLM key it falls back to returning the best sources
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import ToolContext
from app.kernel.memory.retriever import default_retriever
from app.kernel.models import Decision, Notification, Proposal, Task, Workspace


def _echo(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    return text, []


def status_report(ctx: ToolContext) -> str:
    db, ws_id = ctx.db, ctx.principal.workspace_id
    ws = db.get(Workspace, ws_id)
    today = datetime.now(ZoneInfo(ws.timezone if ws else "Africa/Nairobi")).date()

    def count(stmt) -> int:
        return int(db.execute(stmt).scalar_one())

    open_tasks = count(select(func.count()).select_from(Task).where(
        Task.workspace_id == ws_id, Task.status.in_(["open", "in_progress"])))
    overdue = list(db.execute(select(Task).where(
        Task.workspace_id == ws_id, Task.status.in_(["open", "in_progress"]), Task.due_date < today,
    ).order_by(Task.due_date).limit(5)).scalars())
    due_today = count(select(func.count()).select_from(Task).where(
        Task.workspace_id == ws_id, Task.status.in_(["open", "in_progress"]), Task.due_date == today))
    pending = list(db.execute(select(Proposal).where(
        Proposal.workspace_id == ws_id, Proposal.status == "pending").order_by(Proposal.id).limit(5)).scalars())
    revisit = count(select(func.count()).select_from(Decision).where(
        Decision.workspace_id == ws_id, Decision.status == "accepted", Decision.revisit_on <= today))
    unread = count(select(func.count()).select_from(Notification).where(
        Notification.workspace_id == ws_id, Notification.user_id == ctx.principal.user_id,
        Notification.read_at.is_(None)))

    lines = [f"Status for {ws.name if ws else 'workspace'} — {today.isoformat()}"]
    lines.append(f"• Approvals waiting: {len(pending)}")
    lines += [f"   #{p.id} {p.summary}" for p in pending]
    lines.append(f"• Open tasks: {open_tasks} (due today: {due_today}, overdue: {len(overdue)})")
    lines += [f"   overdue: {t.title} (due {t.due_date.isoformat()})" for t in overdue]
    lines.append(f"• Decisions due for revisit: {revisit}")
    lines.append(f"• Unread notifications: {unread}")
    return "\n".join(lines)


def _status(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    return status_report(ctx), []


def _memory_fallback(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    hits = default_retriever().search(ctx.db, ctx.principal.workspace_id, text, 3)
    if not hits:
        return "No LLM is configured, and no document matched your question.", []
    lines = ["No LLM is configured, so here are the most relevant passages instead of an answer:"]
    for i, h in enumerate(hits, 1):
        lines.append(f"[{i}] {h.heading}: {h.snippet}")
    return "\n".join(lines), [h.as_dict() for h in hits]


def register_builtin_agents() -> None:
    register_agent(AgentSpec(
        name="echo", description="Returns its input. Proves the agent runtime works end to end.",
        handler=_echo, input_hint="Any text",
    ))
    register_agent(AgentSpec(
        name="status", description="What needs your attention right now: approvals, overdue tasks, decisions to revisit.",
        handler=_status, input_hint="(no input needed)",
    ))
    register_agent(AgentSpec(
        name="memory_qa",
        description="Answers questions from company documents, citing every source.",
        tools=("search_memory",),
        fallback=_memory_fallback,
        max_steps=6,
        input_hint="A question about the company's documents",
    ))
