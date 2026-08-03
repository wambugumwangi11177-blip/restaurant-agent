# Changelog

Notable changes to the Leviii AI platform and its documentation. Newest first. Derived from
git history on `feat/phase1-production-hardening`.

## 2026-08-02 — Platform audit & remediation

Graded the codebase against a generic + construction + EdTech SaaS audit checklist
(externally sourced, adapted to this product); see `docs/platform-audit.md` for the full
scorecard and disposition of every finding.

### Added
- `docs/platform-audit.md` — the audit record: as-found scorecard, disposition of every
  fail, and the post-remediation re-grade.
- Staff account deactivation — `User.is_active`, `POST/PUT /users/{id}/deactivate|activate`,
  blocks both new logins and already-issued tokens (tech-debt D18).
- AI/LLM spend cap (`backend/ai/spend_guard.py`) — DB-backed per-tenant daily/monthly budget,
  wired into narration and the strategy agent; `@limiter.limit` added to all 9 LLM-invoking
  routes; `/ai/usage` now surfaces remaining budget (tech-debt D14).
- POS offline order queue (`frontend/src/lib/offlineQueue.ts`) with a client-generated
  idempotency key (`Order.idempotency_key`) so a retried submission after a network drop
  can't create a duplicate order (tech-debt D15).
- Shared-device PIN quick-switch — attribution-only by design (never a second auth boundary;
  see `security/threat-model.md` T15), `POST /auth/pin/{set,verify}`, `GET /auth/pin/roster`
  (tech-debt D16).
- Frontend error boundaries (`error.tsx`, `global-error.tsx`) (tech-debt D22).
- Frontend test scaffolding — Vitest + React Testing Library, 19 tests across cart math,
  money formatters, and `AuthContext`, wired non-blocking into CI (tech-debt D17).
- 13 new tech-debt-register entries (D14–D26), 2 `external-hardening-checklist.md` items
  (§7), 1 threat-model entry (T15).

### Changed
- CORS tightened from `allow_methods/allow_headers=["*"]` to the API's actual verb/header set.
- Frontend axios client retries once on `429`, honoring `Retry-After`.
- `execution/emit_capability_manifest.py`'s two dangling doc citations repointed to docs that
  actually exist.
- Stale Alembic revision reference fixed in `engineering-standards.md` §5 (was `017`,
  actual `024`); an already-resolved `npm audit`-blocking item (old D7) removed from
  tech-debt-register.md, and a currently-red `npm audit` gate from unrelated new advisories
  tracked as D27.

### Fixed
- POS order form no longer silently swallows a failed submission (`console.error`-only,
  zero user feedback) — now shows an error toast, or queues the order for automatic retry on
  a network failure (tech-debt D19).

### Notes
- Full backend test suite: **382 passing** (up from 372 before this work; 10 new tests).
- Full frontend test suite: **19 passing** (new — no framework existed before).
- 4 new Alembic migrations (`025`–`028`), verified via a full upgrade → downgrade →
  re-upgrade round-trip against a freshly bootstrapped database, not just the test suite's
  `create_all()` path — caught and fixed a real SQLite named-FK-constraint reflection bug in
  migration `028`'s downgrade path along the way.

## Unreleased — Documentation & hardening (2026-07-11)

### Added
- **Trust documentation set** under `docs/`: Control Evidence Matrix, Technical & Client
  Trust Centers, Architecture, Engineering Standards, Operations & Reliability, AI
  Governance, Threat Model + Risk Register, Compliance Matrix, FAQ, ADRs, this changelog,
  and a tech-debt register. Grounded in the codebase; operational actuals marked TBD.
- **Legal-pack redline change-list** for the externally-generated 12-document legal set.
- **RBAC enforcement** — `require_role` dependency applied to admin-sensitive routes
  (data export/erasure, `/api/v1/ai/usage`, restaurant profile) with `test_rbac.py`.
- **Password policy at registration** — minimum 8 chars incl. letters + digits.
- Argon2id variant pinned explicitly (`argon2__type="ID"`).

### Changed
- **AI documentation reconciled with shipped code** across the doc set (architecture,
  AI governance, ADR 0005, both trust centers, control-evidence matrix, threat model,
  compliance matrix, engineering standards, FAQ): the LLM is now documented as used in
  **two** non-computing roles — WhatsApp free-text **and** a grounded reasoning/narration
  layer over the deterministic analytics — with the "LLM never computes" invariant and the
  grounding-redaction control stated explicitly, plus the Groq→Anthropic Claude tiered
  upgrade path.

### Notes
- Full backend test suite: **206 passing**.

## Prior (from git history)

- `79908e8` — AIOps: `GET /api/v1/ai/usage` (token spend, agent latency, grounding).
- `638a61a` — `/api/v1` versioning + JWT session revocation (`token_version`).
- `29f188b` — Fail-closed startup config guard + green test suite.
- `cb97fae` — Stock-alert tests pinned to deterministic service hours.
- `4362786` — DB integrity constraints + disaster-recovery runbook.

## Conventions

- Group entries under Added / Changed / Fixed / Security.
- Reference the commit or PR. Move "Unreleased" to a dated version on release.

_Owner: Engineering · Contact: leviiiaikenya@gmail.com_
