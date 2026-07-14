# Business Intelligence Roadmap — the agentic layer above the analytics

## Why this exists
Security and CI were never the moat. The differentiator is **business intelligence**:
turning the existing deterministic analytics into *decisions*, *simulations*, and a
*strategy* an owner can act on — and, above that, an agentic operating system
(knowledge graph, workflow engine, autonomous planning, marketplace).

This directive tracks that build. It sits on top of, and obeys, the standing rules in
`012_agentic_roadmap.md`:
- **Layer 3 (execution) stays deterministic.** The decision ranking, simulation
  engine, digital twin, knowledge graph, and workflow executor are pure Python over
  the DB — **no LLM in the math**.
- **LLM lives only at Layer 2 orchestration/narration.** The CEO/Strategy agent is the
  only genuinely new LLM surface; it calls the deterministic agents + simulator + graph
  **as read-only tools**, grounds output via `ai/reasoning/grounding.py`, scrubs via
  `ai/pii_scrub.py`, and meters tokens to `token_usage`.
- **Read-only tools; human approval for mutations.** Applying a price change, sending a
  campaign, or creating a purchase order always goes through the existing approval hop.
- Additive & flag-gated (`feature_flags.py`); degrades cleanly with no LLM provider.

## Standing labelling rule (from 012)
Before calling anything "AI," say whether it calls an LLM or is deterministic, in code
and copy. Everything below except Phase 3's strategist narration is deterministic.

---

## Phases (all DONE — full test suite green, `next build` clean, migrations idempotent)

- **P1 Decision Intelligence** — `ai/decisions/{model,ranking,adapters}.py`. Every agent's
  recommendations → one ranked `Decision` stream (impact/confidence/risk/effort).
  `GET /ai/decisions`. UI: `components/ai/DecisionCard.tsx`.
- **P2 Simulation Engine** — `ai/simulation/engine.py`. Deterministic what-if
  (price/promo/cost) with a bounded elasticity model tied to each item's own velocity.
  `POST /ai/simulate`. UI: `WhatIfSimulator.tsx`.
- **P3 CEO/Strategy Agent** — `ai/orchestrator/strategist.py`. Goal-driven LLM tool-loop
  over the deterministic agents; grounded, metered, audit-traced; deterministic fallback
  when no provider. `POST /ai/strategy`. UI: `StrategyAgent.tsx`. Flag: `strategy_agent`.
- **P4 Digital Twin** — `ai/simulation/{twin,signals}.py`. Forward revenue projection =
  forecaster baseline × offline calendar signals (KE public holidays + school terms).
  Weather/sports are stubbed behind the same provider interface (no keys → no-op).
  `GET /ai/forecast/twin`. UI: `DigitalTwin.tsx`.
- **P5 Cost→money + learning loop + scorecards** — `ai/cost_model.py` (per-model USD/KES),
  `ai/evaluation/learning.py` (record→score daily via scheduler), scorecards in
  `tracker.get_ai_ops_summary`. UI: `/dashboard/ai-ops`.
- **P6 Knowledge Graph** — `ai/graph/{build,traverse}.py`. Projection over existing tables
  (supplier→ingredient→dish→category); critical-path revenue-at-risk. `GET /ai/graph/impact`.
- **P7 Multi-model Router** — `ai/routing/router.py`. need→engine policy; forecast/
  deterministic tasks route to **no LLM**.
- **P8 Workflow Engine** — `ai/workflows/` + `WorkflowRun`/`WorkflowStep` (migration 023).
  Durable state machine; `human_approval`/`wait_external` are first-class pauses; mutating
  steps gated behind approval. `POST /ai/workflows/{template}/start|resume|cancel`.
- **P9 Planning + Self-Evaluation** — `strategist.plan()` (time-phased, monitored) +
  `ai/evaluation/feedback.py` (classify why a forecast missed; per-agent reliability that
  down-weights poor agents in P1 ranking). `POST /ai/strategy/plan`, `GET /ai/feedback`.
- **P10 Enterprise Admin** — `Organization`/`Region` (migration 024) + `ai/enterprise/`
  (benchmarking, audit center). `routers/enterprise.py`, tenant-scoped.
- **P11 Marketplace/Plugin SDK** — `ai/plugins/`. Read-only `PluginContext`, declared
  scopes, approval-gated mutation, fault isolation; read-only "decisions" plugins join the
  P1 ranking. `GET /ai/plugins`, `POST /ai/plugins/{name}/invoke`.
  **Security caveat (honest):** this is an in-process COOPERATIVE capability boundary, not
  an OS sandbox — a plugin is ordinary Python in the host process and could reach around the
  context (e.g. `import database`). The guardrails are real for FIRST-PARTY / reviewed
  plugins; running genuinely untrusted third-party code safely needs a hard isolation
  boundary (subprocess / container / WASM). Until that exists, register only vetted plugins.

## Deliberately NOT built (needs a human decision, not autonomous code)
- **Cross-account support impersonation (part of P10).** Issuing a token to act as another
  user is a privilege-escalation surface — scope, time-box, full audit, and revocation must
  be designed under security review before it ships. Documented in `ai/enterprise/__init__.py`.
- **Hard plugin isolation (part of P11).** The current SDK is a cooperative boundary for
  vetted plugins. A real third-party marketplace needs process/container/WASM isolation
  before it can run untrusted code — see the P11 security caveat above.
- **Live weather / sports feeds (part of P4).** Interface exists; wire real providers +
  API keys when a deployment wants them.
- **Anthropic provider.** Router prefers it for reasoning/vision, but it stays gated behind
  the same "client has paid" decision as in 012 — Groq is the active provider today.

## Verification baseline (2026-07-12)
`backend` pytest: 354 passing (added ~100 tests incl. `test_agentic_e2e.py`, which drives
all 11 phases over HTTP). `frontend`: `next build` clean (18 routes). Migrations 023/024
run idempotently over `create_all` (they coexist with it via inspector checks, like 021/022).
