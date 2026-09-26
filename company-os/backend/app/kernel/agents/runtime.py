"""
app/kernel/agents/runtime.py
────────────────────────────
Runs one agent once and records everything about the run: input, every tool
call (tool_calls table), output, citations, model, tokens, cost, latency,
final status.

Statuses: succeeded | failed | llm_unavailable | spend_capped | refused |
          max_steps
The caller owns the transaction (commit after run_agent returns).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.kernel.agents import llm, spend
from app.kernel.agents.registry import AGENTS, AgentSpec
from app.kernel.agents.tools import TOOLS, ToolContext, execute_tool
from app.kernel.agents.untrusted import UNTRUSTED_RULES
from app.kernel.models import AgentRun
from app.kernel.rbac import role_has
from app.kernel.tenancy import Principal

logger = logging.getLogger("kernel.runtime")

MAX_TOOL_RESULT_CHARS = 12_000


def get_agent(name: str) -> AgentSpec:
    spec = AGENTS.get(name)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No agent named {name!r}")
    return spec


def _system_prompt(spec: AgentSpec) -> str:
    return f"{spec.directive().strip()}\n\n{UNTRUSTED_RULES}"


def _finish(run: AgentRun, started: float, status_: str, output: str | None = None, error: str | None = None) -> AgentRun:
    run.status = status_
    run.output = output
    run.error = error
    run.latency_ms = int((time.monotonic() - started) * 1000)
    run.finished_at = datetime.now(timezone.utc)
    return run


def run_agent(
    db: Session,
    principal: Principal,
    name: str,
    input_text: str,
    channel: str = "api",
) -> AgentRun:
    spec = get_agent(name)
    if not role_has(principal.role, spec.permission):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role cannot run {name!r}")
    input_text = (input_text or "").strip()[:8000]

    run = AgentRun(
        workspace_id=principal.workspace_id, agent_name=name, input={"text": input_text},
        channel=channel, triggered_by_user_id=principal.user_id, cost_usd=Decimal("0"),
    )
    db.add(run)
    db.flush()
    started = time.monotonic()
    ctx = ToolContext(db=db, principal=principal, agent_run_id=run.id)

    def deterministic(handler) -> AgentRun:
        try:
            with db.begin_nested():
                output, citations = handler(ctx, input_text)
        except Exception as e:  # noqa: BLE001 — recorded on the run
            logger.exception("agent %s failed", name)
            return _finish(run, started, "failed", error=f"{type(e).__name__}: {e}")
        run.citations = citations
        run.model = run.model or "deterministic"
        return _finish(run, started, "succeeded", output=output)

    if spec.handler is not None:
        return deterministic(spec.handler)

    if not llm.is_available():
        if spec.fallback is not None:
            run.model = "none (fallback: no LLM configured)"
            return deterministic(spec.fallback)
        return _finish(run, started, "llm_unavailable", error="No LLM provider key is configured")

    if spend.over_cap(db, principal.workspace_id):
        return _finish(run, started, "spend_capped", error=f"Daily LLM spend cap (${spend.cap_usd()}) reached")

    tool_specs = [
        llm.ToolSpec(name=t, description=TOOLS[t].description, input_schema=TOOLS[t].input_schema)
        for t in spec.tools
    ]
    try:
        conv = llm.start_conversation(_system_prompt(spec), input_text, tool_specs, spec.tier)
        run.model = conv.model
        allowed = set(spec.tools)
        for _ in range(spec.max_steps):
            turn = conv.send()
            run.model = turn.model
            run.input_tokens += turn.input_tokens
            run.output_tokens += turn.output_tokens
            run.cost_usd = Decimal(run.cost_usd) + llm.cost_usd(turn.model, turn.input_tokens, turn.output_tokens)
            db.flush()
            if turn.stop_reason == "refusal":
                return _finish(run, started, "refused", error=f"The model declined this request ({turn.detail})")
            if turn.stop_reason == "pause_turn":
                continue
            if not turn.tool_uses:
                run.citations = ctx.citations
                return _finish(run, started, "succeeded", output=turn.text)
            results = []
            for use in turn.tool_uses:
                outcome = execute_tool(ctx, use.name, use.input, allowed=allowed)
                content = json.dumps(outcome, default=str, ensure_ascii=False)
                if len(content) > MAX_TOOL_RESULT_CHARS:
                    content = content[:MAX_TOOL_RESULT_CHARS] + "…(truncated)"
                results.append((use.id, content, outcome.get("status") not in ("ok", "pending_approval", "executed")))
            conv.add_tool_results(results)
            if spend.over_cap(db, principal.workspace_id):
                run.citations = ctx.citations
                return _finish(run, started, "spend_capped", output=turn.text or None,
                               error=f"Daily LLM spend cap (${spend.cap_usd()}) reached mid-run")
        run.citations = ctx.citations
        return _finish(run, started, "max_steps", error=f"Stopped after {spec.max_steps} steps without a final answer")
    except llm.LLMError as e:
        run.citations = ctx.citations
        return _finish(run, started, "failed", error=str(e))
