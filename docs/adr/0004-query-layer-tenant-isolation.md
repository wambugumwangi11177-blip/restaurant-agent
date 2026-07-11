# ADR 0004 — Query-layer tenant isolation

**Status:** Accepted · **Date:** 2026-07-11 (documenting an existing decision)

## Context
Multi-tenant SaaS must guarantee one tenant can never read/modify another's data. Options:
Postgres row-level security (RLS), or application-layer query scoping.

## Decision
Enforce isolation at the **application query layer**: resolve the caller's restaurant from
their tenant (`routers/deps.py`) and filter every query by `restaurant_id`; a request for
another tenant's record id returns 404. Back it with an automated IDOR test suite that runs
in CI.

## Consequences
- Simple, explicit, and testable; no dependency on DB-role plumbing.
- Discipline required: every new query must scope by `restaurant_id`. The IDOR suite is the
  safety net; RLS remains a possible future defence-in-depth layer.
- Known limitation: multi-restaurant tenants resolve to the first restaurant (tech-debt).

## References
`backend/routers/deps.py`, `backend/tests/test_tenant_isolation.py`
