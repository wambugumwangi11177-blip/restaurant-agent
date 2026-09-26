"""
app/api/agents.py
─────────────────
List agents, run one, inspect runs (with every tool call), and give feedback on
a run's output.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require
from app.db import get_db
from app.kernel.agents import llm
from app.kernel.agents.registry import AGENTS
from app.kernel.agents.runtime import run_agent
from app.kernel.agents.tools import TOOLS
from app.kernel.models import AgentRun, Feedback, ToolCall
from app.kernel.tenancy import Principal, get_or_404, scoped

router = APIRouter()


def run_out(run: AgentRun, tool_calls: list[ToolCall] | None = None) -> dict:
    out = {
        "id": run.id, "agent": run.agent_name, "status": run.status, "channel": run.channel,
        "input": run.input.get("text"), "output": run.output, "error": run.error, "citations": run.citations,
        "model": run.model, "input_tokens": run.input_tokens, "output_tokens": run.output_tokens,
        "cost_usd": str(run.cost_usd), "latency_ms": run.latency_ms,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    if tool_calls is not None:
        out["tool_calls"] = [
            {"id": t.id, "tool": t.tool_name, "effect": t.effect, "status": t.status, "args": t.args,
             "result": t.result, "proposal_id": t.proposal_id, "latency_ms": t.latency_ms}
            for t in tool_calls
        ]
    return out


@router.get("/agents")
def list_agents(principal: Principal = Depends(require("agents.run"))) -> dict:
    return {
        "llm_provider": llm.provider(),
        "agents": [
            {"name": a.name, "description": a.description, "uses_llm": a.uses_llm,
             "has_fallback": a.fallback is not None, "input_hint": a.input_hint,
             "tools": [{"name": t, "effect": TOOLS[t].effect.value} for t in a.tools]}
            for a in AGENTS.values()
        ],
    }


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str = Field(default="", max_length=8000)


@router.post("/agents/{name}/run")
def run(name: str, body: RunIn, principal: Principal = Depends(require("agents.run")),
        db: Session = Depends(get_db)) -> dict:
    result = run_agent(db, principal, name, body.input)
    db.commit()
    calls = list(db.execute(select(ToolCall).where(ToolCall.agent_run_id == result.id).order_by(ToolCall.id)).scalars())
    return run_out(result, calls)


@router.get("/agents/runs")
def list_runs(limit: int = Query(default=50, ge=1, le=200), agent: str | None = None,
              principal: Principal = Depends(require("agents.read_runs")), db: Session = Depends(get_db)) -> list[dict]:
    stmt = scoped(AgentRun, principal.workspace_id)
    if agent:
        stmt = stmt.where(AgentRun.agent_name == agent)
    return [run_out(r) for r in db.execute(stmt.order_by(AgentRun.id.desc()).limit(limit)).scalars()]


@router.get("/agents/runs/{run_id}")
def get_run(run_id: int, principal: Principal = Depends(require("agents.read_runs")),
            db: Session = Depends(get_db)) -> dict:
    r = get_or_404(db, AgentRun, run_id, principal.workspace_id)
    calls = list(db.execute(select(ToolCall).where(ToolCall.agent_run_id == r.id).order_by(ToolCall.id)).scalars())
    return run_out(r, calls)


class RunFeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["helpful", "unhelpful"]
    reason: str | None = Field(default=None, max_length=2000)
    correction: str | None = Field(default=None, max_length=8000)


@router.post("/agents/runs/{run_id}/feedback", status_code=201)
def run_feedback(run_id: int, body: RunFeedbackIn, principal: Principal = Depends(require("feedback.write")),
                 db: Session = Depends(get_db)) -> dict:
    r = get_or_404(db, AgentRun, run_id, principal.workspace_id)
    fb = Feedback(workspace_id=principal.workspace_id, target_type="agent_run", target_id=r.id,
                  verdict=body.verdict, reason=body.reason, correction=body.correction, user_id=principal.user_id)
    db.add(fb)
    db.commit()
    return {"id": fb.id, "verdict": fb.verdict}
