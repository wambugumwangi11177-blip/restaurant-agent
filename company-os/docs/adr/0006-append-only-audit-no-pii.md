# ADR 0006 — Audit log is append-only and never stores PII

**Status:** Accepted, 2026-09-26

## Decision
- Migration 0001 installs a trigger that rejects `UPDATE` and `DELETE` on `audit_log`.
- `app/kernel/audit.py` computes field diffs. For PII fields (person name, email, phone, notes; user email, name, phone; message addresses and bodies) it records only `{"changed": true}`. Secrets such as password hashes and MFA secrets are never recorded at all.
- Right-to-erasure (Kenya Data Protection Act) scrubs PII in the live tables. The audit log needs no change, because it never held the values.

## Consequences
- History can't be rewritten through the application, even by a bug.
- `TRUNCATE` is not blocked; it needs table-owner rights. Production should run the app as a role that doesn't own the tables. This is tracked in directive 001, because it needs the founder's database access.
