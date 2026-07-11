# ADR 0006 — RBAC via a `require_role` dependency

**Status:** Accepted · **Date:** 2026-07-11

## Context
Roles (SUPERADMIN/ADMIN/STAFF) existed as data but nothing enforced them; the security docs
described role-based access that wasn't real. We needed enforcement without a heavy
framework.

## Decision
Add a `require_role(*roles)` FastAPI dependency factory (`backend/auth.py`) that composes
with `get_current_user`; SUPERADMIN always passes, otherwise 403. Apply it first to the
admin-sensitive surfaces (data export/erasure, AI usage, restaurant profile) and expand
coverage from there. Cover with `test_rbac.py`.

## Consequences
- Real, tested authorization on the highest-risk routes; the doc claim becomes true.
- Coverage is incremental — not yet applied to every operational route (tracked as tech-debt
  so "STAFF = POS/KDS only" becomes literally true).

## References
`backend/auth.py`, `backend/routers/export.py`, `backend/routers/ai.py`,
`backend/routers/auth.py`, `backend/tests/test_rbac.py`
