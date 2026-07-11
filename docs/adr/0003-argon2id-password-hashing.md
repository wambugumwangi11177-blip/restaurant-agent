# ADR 0003 — Argon2id for password hashing

**Status:** Accepted · **Date:** 2026-07-11 (documenting an existing decision)

## Context
Password storage must resist offline cracking. Options: bcrypt, scrypt, Argon2.

## Decision
Use Argon2 via passlib, pinned to the **Argon2id** variant (`argon2__type="ID"`) — the
OWASP-recommended memory-hard function. Pinning makes the variant explicit rather than
relying on a library default that could change.

## Consequences
- Strong resistance to GPU/ASIC cracking; per-hash cost tunable.
- Slightly heavier CPU/memory per login than bcrypt — acceptable at our login volume.

## References
`backend/auth.py` (`pwd_context`), [control-evidence-matrix.md](../trust/control-evidence-matrix.md)
