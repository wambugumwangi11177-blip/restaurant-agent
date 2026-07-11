# Control Evidence Matrix

| | |
|---|---|
| **Reference** | LAI-EVID-001 |
| **Classification** | Confidential — shared under NDA |
| **Version** | 1.1 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose

This document is the evidence backing for every security and reliability control
claimed in the Leviii AI legal/security pack (LAI-SEC-001, LAI-DPA-001, LAI-BCP-001,
LAI-AI-001, LAI-IRP-001). For each control it records **what is implemented**, **how it
is verified**, **where the evidence lives** (file path + line, or CI job), and the **date
last verified against the codebase**.

It answers the question a technical due-diligence reader always asks next:
*"You say the control exists — show me."*

## Scope & method

- Verified against the live backend at `backend/` (the git-tracked FastAPI application).
- The abandoned duplicate tree under `restaurant-agent/` is git-ignored and out of scope.
- "Last verified" = date of the most recent manual code audit. Automated controls
  (tests, CI jobs) additionally re-verify themselves on every push and pull request.
- Evidence paths are relative to the repository root.

## Status legend

- **Production** — implemented, exercised in the running system, evidence cited.
- **Partial** — implemented in part; a named limitation applies.
- **Planned** — claimed in a document but not yet enforced in code; tracked for build.

---

## 1. Authentication & access control

| Control | Status | Implementation | Verification | Evidence | Last verified |
|---|---|---|---|---|---|
| Password hashing (Argon2id) | Production | `passlib` CryptContext, `argon2` scheme pinned to type ID (`argon2__type="ID"`); hashes on register, verifies on login | Auth security tests exercise hash/verify | `backend/auth.py` (`pwd_context`) | 2026-07-11 |
| JWT bearer tokens, HS256 | Production | `python-jose` encode/decode, `ALGORITHM = "HS256"` | Token issued on login, validated on every protected request | `backend/auth.py:32,53,66` | 2026-07-11 |
| 8-hour token expiry | Production | `ACCESS_TOKEN_EXPIRE_HOURS` default 8, applied as `exp` claim | — | `backend/auth.py:33,49-52` | 2026-07-11 |
| Session revocation (`token_version`) | Production | Token embeds a `ver` claim; `get_current_user` rejects any token whose `ver` ≠ the user's current `token_version`. `/logout-all` bumps it | `test_versioning_and_sessions.py` | `backend/models.py:85`, `backend/auth.py:82-83`, `backend/routers/auth.py:173-191` | 2026-07-11 |
| Per-IP login rate limit (10/min → 429) | Production | SlowAPI `@limiter.limit("10/minute")` on login; 429 handler registered app-wide. Register limited to `5/hour` | `test_auth_security.py` asserts 429 after threshold | `backend/routers/auth.py:66,119`, `backend/main.py` (SlowAPI handler) | 2026-07-11 |
| Per-account lockout (5 attempts / 15 min) | Production | `failed_login_attempts` + `locked_until`; lockout checked before password verification (no timing signal to locked accounts) | `test_auth_security.py::test_account_locks_after_max_failed_attempts` | `backend/routers/auth.py:33-34,125-137`, `backend/models.py:78-79` | 2026-07-11 |
| RBAC — role enforcement (SUPERADMIN/ADMIN/STAFF) | Production (coverage expanding) | `require_role(...)` dependency enforces roles (SUPERADMIN always passes). Applied to admin-sensitive routes: data export/erasure, AI usage, restaurant-profile update. Broader per-route coverage is rolling out | `test_rbac.py` asserts STAFF → 403 and ADMIN/SUPERADMIN → allowed | `backend/auth.py` (`require_role`), `backend/routers/export.py`, `backend/routers/ai.py:297-302`, `backend/routers/auth.py` (PUT /restaurant) | 2026-07-11 |
| Password complexity at registration | Production | `require_strong_password` enforces min-8 length + at least one letter and one digit, called at the top of `register` | `test_rbac.py::test_register_rejects_weak_passwords` / `::test_register_accepts_strong_password` | `backend/auth.py` (`require_strong_password`), `backend/routers/auth.py::register` | 2026-07-11 |

## 2. Data isolation & multi-tenancy

| Control | Status | Implementation | Verification | Evidence | Last verified |
|---|---|---|---|---|---|
| Tenant model, restaurant→tenant binding | Production | `Tenant` owns `restaurants` and `users`; every operational record carries `restaurant_id` resolving to exactly one tenant | ORM relationships | `backend/models.py:61-69,92-108` | 2026-07-11 |
| Query-layer tenant scoping | Production | Endpoints resolve the caller's restaurant via `get_or_create_restaurant`/`get_restaurant_or_none`, then filter every query by `restaurant_id`; a mismatched ID returns 404 | Cross-tenant test suite | `backend/routers/deps.py:20-42`, `backend/routers/orders.py:122-126` | 2026-07-11 |
| Cross-tenant IDOR test suite | Production | Tests enumerate another tenant's order/reservation/inventory IDs and assert 404 + unchanged state | Runs on every push/PR in the `pytest` CI job | `backend/tests/test_tenant_isolation.py` | 2026-07-11 |
| Within-tenant multi-restaurant scoping | Partial | `get_or_create_restaurant` returns the *first* restaurant for a tenant; a tenant owning multiple restaurants always resolves to one. Not a cross-tenant leak; fix tracked (Track B) | — | `backend/routers/deps.py:40-42` | 2026-07-11 |

## 3. Input handling & injection defense

| Control | Status | Implementation | Verification | Evidence | Last verified |
|---|---|---|---|---|---|
| SQL parameterization (no raw string SQL) | Production | All data access via SQLAlchemy ORM. Only raw SQL is a parameterless health probe (`SELECT 1`) and migration DDL over a fixed whitelist | Bandit SAST + code review | `backend/routers/health.py:26` (sole `text()`), ORM throughout | 2026-07-11 |
| Request-body validation (Pydantic) | Production | Typed Pydantic schemas bound to request bodies across routers | Schema validation at request time; tests | `backend/schemas.py`, `backend/routers/orders.py:118`, `reservations.py:40` | 2026-07-11 |
| Strict/extra-field rejection (`extra="forbid"`) | **Planned** | Schemas are typed but do not yet reject unexpected fields. Optional hardening (Track B) | Pending | `backend/schemas.py` | 2026-07-11 |

## 4. Encryption & secrets

| Control | Status | Implementation | Verification | Evidence | Last verified |
|---|---|---|---|---|---|
| TLS in transit | Production | TLS terminated at the Railway edge in front of the app; TLS auto-renew documented | Provider-managed | `backend/DISASTER_RECOVERY.md` (SSL/TLS section) | 2026-07-11 |
| HSTS header | Production | `Strict-Transport-Security: max-age=63072000; includeSubDomains` set on every response | Header present on API responses | `backend/middleware/security_headers.py:26` | 2026-07-11 |
| Encryption at rest (AES-256) | Production (provider-managed) | Managed by Neon PostgreSQL; not an in-repo control, so no code evidence — see Neon SOC 2 report | Neon platform | Provider — Neon | 2026-07-11 |
| Secrets via environment only | Production | Config read from environment (`os.getenv`); `SECRET_KEY` crashes startup if unset; `.env` git-ignored | `startup_checks` + `.gitignore` | `backend/auth.py:25-30`, `backend/.gitignore`, `backend/.env.example` | 2026-07-11 |

## 5. HTTP security headers

| Control | Status | Implementation | Verification | Evidence | Last verified |
|---|---|---|---|---|---|
| `X-Content-Type-Options: nosniff` | Production | Security-headers middleware | Header present on all responses | `backend/middleware/security_headers.py:22` | 2026-07-11 |
| `X-Frame-Options: DENY` | Production | " | " | `backend/middleware/security_headers.py:23` | 2026-07-11 |
| `Referrer-Policy: strict-origin-when-cross-origin` | Production | " | " | `backend/middleware/security_headers.py:24` | 2026-07-11 |
| `Permissions-Policy: geolocation=(), microphone=(), camera=()` | Production | " | " | `backend/middleware/security_headers.py:25` | 2026-07-11 |
| Middleware registered app-wide | Production | `app.add_middleware(SecurityHeadersMiddleware)` | — | `backend/main.py` (middleware registration) | 2026-07-11 |

## 6. Software supply chain & CI security

| Control | Status | Implementation | Verification | Evidence | Last verified |
|---|---|---|---|---|---|
| Dependency vulnerability scan (pip-audit) | Production | `pip-audit` runs on every push/PR, **blocking**; 6 advisories ignored explicitly by id with documented justification (no blanket `continue-on-error`) | CI job `dependency-audit` | `.github/workflows/ci.yml:33-78` | 2026-07-11 |
| Static analysis (Bandit SAST) | Production | `bandit -r . -ll` on every push/PR, **blocking and currently clean** at medium+ severity | CI job `sast` | `.github/workflows/ci.yml:80-102` | 2026-07-11 |
| Automated test suite in CI | Production | 31 `test_*.py` files run under `pytest` with coverage on every push/PR (coverage measured, not yet gated) | CI job `pytest` | `.github/workflows/ci.yml:9-31`, `backend/tests/` | 2026-07-11 |
| Frontend build + typecheck + npm audit | Production | `npm run build`, `tsc --noEmit`, and `npm audit --audit-level=high` (audit non-blocking pending baseline triage) | CI job `frontend-ci` | `.github/workflows/ci.yml:104-141` | 2026-07-11 |
| IDOR isolation tests in CI | Production | Cross-tenant suite runs within the `pytest` job on every change | CI job `pytest` | `backend/tests/test_tenant_isolation.py` + `ci.yml:9-31` | 2026-07-11 |

## 7. API versioning & operability

| Control | Status | Implementation | Verification | Evidence | Last verified |
|---|---|---|---|---|---|
| `/api/v1` versioning | Production | Routers mounted under `/api/v1`; legacy unversioned mount retained but hidden from schema | — | `backend/main.py` (`prefix="/api/v1"`), `backend/routers/auth.py:26` | 2026-07-11 |
| AI observability endpoint (`GET /api/v1/ai/usage`) | Production | Exposes LLM token spend by model, per-agent latency (p50/p95) + success rate, grounding trust rate | — | `backend/routers/ai.py:297-311` | 2026-07-11 |
| Fail-closed startup config guard | Production | `enforce_startup_checks()` raises and refuses to boot in production if `SECRET_KEY` missing, or `MPESA_CALLBACK_TOKEN` unset while M-Pesa configured | Called at boot | `backend/startup_checks.py:72-91`, `backend/main.py` (startup) | 2026-07-11 |
| Error monitoring (Sentry) | Production | `sentry_sdk.init` when `SENTRY_DSN` set, 20% trace sample | — | `backend/main.py:30-36` | 2026-07-11 |

## 8. AI governance

| Control | Status | Implementation | Verification | Evidence | Last verified |
|---|---|---|---|---|---|
| Append-only AI-action audit log | Production | `AgentAuditLog` records action_type, agent, before/after state, reasoning, data_sources, approved_by; written insert-only from the orchestrator | `write_audit_log()` is insert-only | `backend/models.py:596-629`, `backend/ai/evaluation/tracker.py:254-288` | 2026-07-11 |
| Audit-log retention ("90-day rolling" per DPA) | **Planned** | The table is append-only with **no automated purge** in code, so a 90-day rolling window is not yet enforced. Reconcile DPA wording or implement TTL (Track B / redlines) | Pending | `backend/models.py:596-629` | 2026-07-11 |
| WhatsApp command-router isolation (LLM only on unmatched free-text) | Production | Structured commands (SALES, STOCK, APPROVE, REJECT, PROMO…) dispatched by a deterministic router; only unmatched free-form text reaches the LLM | Command-router tests | `backend/ai/whatsapp/brain.py:703-742`, `backend/ai/llm_client.py:57,125-134` | 2026-07-11 |
| LLM never computes; narration is grounded and redacted | Production | The deterministic engines produce every figure; the reasoning layer only narrates an already-computed payload, and `grounding.verify()` redacts any number not present in that payload before it reaches an owner. Trust rate surfaced via `get_trust_stats()` | Grounding verifier + redaction on every narrative; trust-rate metric | `backend/ai/reasoning/narrator.py:223,241`, `backend/ai/reasoning/grounding.py`, `backend/routers/ai.py`, `backend/routers/analytics.py` | 2026-07-11 |
| Human-in-the-loop for data-changing actions | Production | Pricing and similar changes take effect only on explicit approval; each recorded in the audit log with `approved_by` | Orchestrator write path | `backend/ai/orchestrator/executive.py` (audit writes), `backend/models.py:620` | 2026-07-11 |

## 9. Reliability & recovery

| Control | Status | Implementation | Verification | Evidence | Last verified |
|---|---|---|---|---|---|
| DB integrity constraints | Production | CHECK constraints (non-negative totals/prices, positive quantities/party size), UNIQUE (restaurant_id, table_number), pervasive FKs/NOT NULL; back-filled via migration | Migration + model definitions | `backend/models.py:124,148-149,185,202-203,287`, `backend/alembic/versions/016_add_integrity_constraints.py` | 2026-07-11 |
| Disaster-recovery runbook | Production | Documented backup config, point-in-time restore, and recovery playbooks | — | `backend/DISASTER_RECOVERY.md` | 2026-07-11 |
| Point-in-time restore / backups | Production (provider-managed) | Neon WAL + daily snapshots; documented in the runbook | Neon platform | `backend/DISASTER_RECOVERY.md` | 2026-07-11 |

---

## Open items (remaining "Planned"/"Partial" rows)

1. **RBAC coverage** — extend `require_role` from the admin-sensitive routes it now guards
   to the full set implied by "STAFF = POS/KDS only" (gate remaining analytics/pricing/
   inventory-write routes). Enforcement mechanism is shipped; coverage is expanding.
2. **`extra="forbid"` on request schemas** — reject unexpected fields to make the
   "strict validation" claim literal. (Not yet done.)
3. **Audit-log retention** — either implement a 90-day purge or reconcile the DPA wording
   to "append-only" without a rolling window. (Redline R-06.)
4. **Multi-restaurant tenant scoping** — resolve restaurant explicitly rather than
   first-match in `routers/deps.py`. (Not yet done.)

*Closed since v1.0:* RBAC enforcement mechanism (B1) and password-complexity validation
(B2) shipped and are now marked Production above; Argon2id variant is pinned explicitly.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial matrix from full `backend/` code audit |
| 1.1 | 2026-07-11 | Engineering | RBAC + password-complexity shipped (Track B1/B2) → Production; Argon2id pinned; open items updated |
