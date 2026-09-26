"""
app/kernel/agents/tools.py
──────────────────────────
Tool registry and THE approval gate.

Every tool has an Effect:
  READ      — reads workspace data. Runs immediately.
  INTERNAL  — writes inside the OS (task, note...). Runs immediately; audited.
  EXTERNAL  — reaches the outside world (email, WhatsApp...). NEVER runs
              without an approved Proposal whose final_args match exactly.

`execute_tool` is the only way any tool runs — for agents and for the
approvals flow alike — so the gate cannot be bypassed by a new code path that
"forgets" it. EXTERNAL handlers additionally call `require_approval(ctx)` as a
second, independent check.
"""

from __future__ import annotations

import enum
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.kernel.models import Proposal, ToolCall
from app.kernel.rbac import role_has
from app.kernel.tenancy import Principal, get_scoped


class Effect(str, enum.Enum):
    READ = "read"
    INTERNAL = "internal"
    EXTERNAL = "external"


@dataclass
class ToolContext:
    db: Session
    principal: Principal
    agent_run_id: int | None = None
    approval_id: int | None = None
    # Filled by tools that read memory, so the run can report its sources.
    citations: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    effect: Effect
    input_schema: dict
    handler: Callable[[ToolContext, dict], dict]
    permission: str
    summarize: Callable[[dict], str] | None = None


TOOLS: dict[str, Tool] = {}


def register_tool(tool: Tool) -> Tool:
    existing = TOOLS.get(tool.name)
    if existing is not None and existing is not tool:
        raise ValueError(f"Tool {tool.name!r} already registered")
    if tool.input_schema.get("type") != "object":
        raise ValueError(f"Tool {tool.name!r} input_schema must be an object schema")
    TOOLS[tool.name] = tool
    return tool


class ApprovalRequired(PermissionError):
    pass


def require_approval(ctx: ToolContext) -> None:
    if ctx.approval_id is None:
        raise ApprovalRequired("EXTERNAL tool invoked without an approved proposal")


# ── Minimal JSON-schema validation (the subset tool schemas use) ─────────────

_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


class InvalidToolArgs(ValueError):
    pass


def validate_args(schema: dict, args: Any) -> dict:
    if not isinstance(args, dict):
        raise InvalidToolArgs("arguments must be an object")
    props: dict = schema.get("properties", {})
    missing = [k for k in schema.get("required", []) if k not in args]
    if missing:
        raise InvalidToolArgs(f"missing required argument(s): {', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        extra = sorted(set(args) - set(props))
        if extra:
            raise InvalidToolArgs(f"unexpected argument(s): {', '.join(extra)}")
    for key, value in args.items():
        spec = props.get(key)
        if not spec:
            continue
        expected = _TYPES.get(spec.get("type", ""))
        if expected and (not isinstance(value, expected) or (spec["type"] in ("integer", "number") and isinstance(value, bool))):
            raise InvalidToolArgs(f"argument {key!r} must be of type {spec['type']}")
        if "enum" in spec and value not in spec["enum"]:
            raise InvalidToolArgs(f"argument {key!r} must be one of {spec['enum']}")
        if spec.get("type") == "string" and "maxLength" in spec and len(value) > spec["maxLength"]:
            raise InvalidToolArgs(f"argument {key!r} is longer than {spec['maxLength']} characters")
    return args


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)


def _log(ctx: ToolContext, tool_name: str, effect: str, args: dict, status: str,
         result: dict | None = None, proposal_id: int | None = None, started: float | None = None) -> None:
    ctx.db.add(ToolCall(
        workspace_id=ctx.principal.workspace_id,
        agent_run_id=ctx.agent_run_id,
        tool_name=tool_name,
        effect=effect,
        args=args,
        result=result,
        status=status,
        proposal_id=proposal_id,
        latency_ms=int((time.monotonic() - started) * 1000) if started else None,
    ))
    ctx.db.flush()


def execute_tool(ctx: ToolContext, name: str, args: dict, *, allowed: set[str] | None = None) -> dict:
    """Run a tool through the gate. Returns a JSON-able dict; never raises for
    tool-level failures (the caller — often a model — needs a readable result)."""
    tool = TOOLS.get(name)
    if tool is None or (allowed is not None and name not in allowed):
        _log(ctx, name, "unknown", args if isinstance(args, dict) else {}, "denied")
        return {"status": "denied", "error": f"tool {name!r} is not available to this agent"}
    if not role_has(ctx.principal.role, tool.permission):
        _log(ctx, name, tool.effect.value, args, "denied")
        return {"status": "denied", "error": f"your role cannot use {name!r}"}
    try:
        args = validate_args(tool.input_schema, args)
    except InvalidToolArgs as e:
        _log(ctx, name, tool.effect.value, args if isinstance(args, dict) else {}, "error", {"error": str(e)})
        return {"status": "error", "error": str(e)}

    if tool.effect is Effect.EXTERNAL:
        if ctx.approval_id is None:
            from app.kernel.approvals import create_proposal  # local import: approvals imports this module

            proposal = create_proposal(ctx, tool, args)
            _log(ctx, name, tool.effect.value, args, "pending_approval", proposal_id=proposal.id)
            if proposal.status == "executed":  # auto-approved under an enabled autonomy policy
                return {"status": "executed", "proposal_id": proposal.id, "result": proposal.result}
            if proposal.status == "failed":
                return {"status": "failed", "proposal_id": proposal.id, "error": proposal.error}
            return {
                "status": "pending_approval",
                "proposal_id": proposal.id,
                "message": "Proposal created; it runs only after the founder approves it in the approval inbox.",
            }
        proposal = get_scoped(ctx.db, Proposal, ctx.approval_id, ctx.principal.workspace_id)
        if (
            proposal is None
            or proposal.status != "approved"
            or proposal.tool_name != name
            or _canonical(proposal.final_args or {}) != _canonical(args)
        ):
            _log(ctx, name, tool.effect.value, args, "denied", {"error": "approval does not match"})
            return {"status": "denied", "error": "approval id does not match an approved proposal for these exact arguments"}

    started = time.monotonic()
    try:
        with ctx.db.begin_nested():
            result = tool.handler(ctx, args)
    except ApprovalRequired as e:
        _log(ctx, name, tool.effect.value, args, "denied", {"error": str(e)}, started=started)
        return {"status": "denied", "error": str(e)}
    except Exception as e:  # noqa: BLE001 — surfaced to caller as a tool error, logged below
        _log(ctx, name, tool.effect.value, args, "error", {"error": f"{type(e).__name__}: {e}"},
             proposal_id=ctx.approval_id, started=started)
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    _log(ctx, name, tool.effect.value, args, "ok", result, proposal_id=ctx.approval_id, started=started)
    return {"status": "ok", "result": result}
