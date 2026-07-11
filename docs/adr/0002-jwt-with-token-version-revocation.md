# ADR 0002 — Stateless JWT with `token_version` revocation

**Status:** Accepted · **Date:** 2026-07-11 (documenting an existing decision)

## Context
Stateless JWTs scale well but can't be revoked before expiry — a problem for leaked tokens or
forced logout. We didn't want a session store on every request.

## Decision
Keep stateless JWTs (HS256, 8h expiry) but embed a `ver` claim equal to the user's
`token_version` column. `get_current_user` rejects any token whose `ver` ≠ the current
`token_version`. `/logout-all` bumps the column, revoking every prior token at once.

## Consequences
- Revocation without a per-request session lookup; one extra column + a cheap comparison.
- Global-per-user granularity (not per-device). Acceptable given 8h expiry.
- Tokens minted before the feature carry no `ver` → default 0 → still valid until next bump.

## References
`backend/auth.py`, `backend/routers/auth.py`, `backend/models.py`, migration `017`
