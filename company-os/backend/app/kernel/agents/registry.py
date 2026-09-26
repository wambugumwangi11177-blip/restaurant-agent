"""
app/kernel/agents/registry.py
─────────────────────────────
An agent is data, not a class hierarchy:

  AgentSpec = directive file (its SOP / system prompt)
            + the exact tools it may call
            + model tier (maps to effort / model per provider)
            + either an LLM loop or a deterministic handler
            + optional deterministic fallback when no LLM is configured

Departments register their agents from their own package. Directives live in
company-os/directives/agents/<name>.md so the instruction set stays readable
and versioned alongside the code (CLAUDE.md, Layer 1).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.kernel.agents.llm import TIER_MEDIUM
from app.kernel.agents.tools import TOOLS, ToolContext

# (ctx, input_text) -> (output_text, citations)
Handler = Callable[[ToolContext, str], tuple[str, list[dict]]]

_DEFAULT_DIRECTIVES = Path(__file__).resolve().parents[4] / "directives" / "agents"


def directives_dir() -> Path:
    return Path(os.environ.get("AGENT_DIRECTIVES_DIR", _DEFAULT_DIRECTIVES))


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    tools: tuple[str, ...] = ()
    tier: str = TIER_MEDIUM
    handler: Handler | None = None  # deterministic agent when set
    fallback: Handler | None = None  # used when the agent needs an LLM and none is configured
    max_steps: int = 8
    permission: str = "agents.run"
    input_hint: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def uses_llm(self) -> bool:
        return self.handler is None

    def directive(self) -> str:
        path = directives_dir() / f"{self.name}.md"
        if not path.is_file():
            raise FileNotFoundError(f"Agent {self.name!r} has no directive at {path}")
        return path.read_text(encoding="utf-8")


AGENTS: dict[str, AgentSpec] = {}


def register_agent(spec: AgentSpec) -> AgentSpec:
    if spec.name in AGENTS and AGENTS[spec.name] is not spec:
        raise ValueError(f"Agent {spec.name!r} already registered")
    unknown = [t for t in spec.tools if t not in TOOLS]
    if unknown:
        raise ValueError(f"Agent {spec.name!r} grants unregistered tools: {unknown}")
    if spec.uses_llm:
        spec.directive()  # fail at startup, not at first run, if the SOP is missing
    AGENTS[spec.name] = spec
    return spec
