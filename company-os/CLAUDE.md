# Company OS — Agent Instructions

> Also mirror this file as AGENTS.md / GEMINI.md if other AI environments are used.

This is the internal operating system for the company: a Kernel plus departments, built one at a time. Start with `directives/000_company_os_plan.md` (the plan) and `directives/001_kernel.md` (how the Kernel works, and which of its done gates are met).

## The 3 layers (same as restaurant-agent)
- **Directives** (`directives/`): the SOPs. Agent system prompts live in `directives/agents/<name>.md`.
- **Orchestration**: agents and the people using them. LLMs only interpret free text and choose tools.
- **Execution**: deterministic Python (`backend/app/`, `execution/`). Business logic never lives in a prompt.

## Non-negotiable rules
1. **Every tool declares an Effect.** Anything that reaches outside the company is `EXTERNAL` and runs only through an approved Proposal (`app/kernel/agents/tools.py`). Never add a second way for a tool to run.
2. **Every write goes through a Kernel service** (`records.py`, `memory/service.py`, `approvals.py`, `privacy.py`). That is how it gets the workspace filter, an audit row and an event. Never write to business tables straight from a route.
3. **Every query is workspace-scoped** (`tenancy.scoped` / `get_or_404`). A record from another workspace is a 404.
4. **No PII in the audit log.** Add new personal-data fields to `audit.PII_FIELDS`.
5. **Departments never import each other** (ADR 0001). They extend the Kernel only through `register_permissions`, `register_event_types`, `register_tool` and `register_agent`.
6. **Untrusted text reaches a model only through `untrusted.wrap()`.**
7. **Never emit an event nobody consumes.** Register new event types together with their consumer.
8. **Tests run on real Postgres.** Every new write path gets an audit assertion, and every new tool gets a gate test.
9. **Paid LLM calls (evals, live runs) need the founder's OK first.** The deterministic retrieval eval runs in CI for free.

## Checks before any commit
```
cd backend && .venv/bin/python -m pytest -q        # includes the retrieval eval gate
.venv/bin/alembic check                              # models and migrations in sync
cd ../frontend && npx tsc --noEmit && npm run build
```

## Self-anneal
When something breaks: fix it, add a test, then write what you learned in the owning directive's *Learnings log*.
