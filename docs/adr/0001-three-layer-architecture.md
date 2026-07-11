# ADR 0001 — Three-layer directive/orchestration/execution architecture

**Status:** Accepted · **Date:** 2026-07-11 (documenting an existing decision)

## Context
LLM reasoning is probabilistic; most restaurant business logic must be deterministic and
consistent. Doing everything in the model compounds error (90%/step ≈ 59% over 5 steps).

## Decision
Separate concerns into three layers: **Directives** (Markdown SOPs, `directives/`),
**Orchestration** (the agent decides routing/ordering), and **Execution** (deterministic
Python in `execution/` and the FastAPI `backend/`). Push complexity into tested code; keep
the model for decision-making.

## Consequences
- High reliability for business logic; the LLM surface is minimized (see ADR 0005).
- Requires discipline: new capability goes into scripts/services, not ad-hoc model calls.

## References
`CLAUDE.md`, [architecture.md](../architecture.md)
