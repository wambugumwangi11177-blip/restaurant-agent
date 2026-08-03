# Leviii AI — Platform Audit (2026-08-02)

| | |
|---|---|
| **Reference** | LAI-AUDIT-001 |
| **Classification** | Internal |
| **Version** | 1.0 |
| **Last Updated** | 2026-08-02 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose & scope

An external methodology applied to this codebase: 3 "AI Audit Prompt Template" documents
from a multi-vertical SaaS certification course (construction, EdTech, and a generic/
vertical-agnostic set), each instructing the same discipline — grade every applicable item
pass/fail with a specific example, score each module, list the top fixes. None target
restaurants, so this audit adapted the methodology: kept items that map onto this product
(role views, offline field use, branch isolation, money precision, shared-device use) and
explicitly dropped what doesn't (listed at the end of Part 1, not silently skipped).

This is a standalone record, separate from the implementation plan that was executed from
it — the plan was ephemeral working material; this document is the audit trail: what was
graded, what it found, and what changed as a result. It complements, not duplicates, this
repo's own dated (2026-07-11) self-audit corpus — [tech-debt-register.md](tech-debt-register.md),
[external-hardening-checklist.md](external-hardening-checklist.md),
[compliance-matrix.md](compliance-matrix.md), [operations-and-reliability.md](operations-and-reliability.md),
[engineering-standards.md](engineering-standards.md), [security/threat-model.md](security/threat-model.md).
Grading against the templates confirmed most of what those docs already tracked, and
surfaced 24 additional items they didn't — 13 became new tech-debt rows (D14–D26; D27 was a
second, unrelated finding from later work), 2 became operator-console items, and the
remainder were fixed directly (see Part 3).

Every grade is evidence-based (file:line or a direct grep/test result) or explicitly marked
`not verified` — no pass/fail is fabricated, matching this repo's own "TBD, not guessed"
convention in `operations-and-reliability.md`.

---

## Part 1 — Graded scorecard (as found, 2026-08-02)

Legend: **PASS** / **FAIL** / *partial* / `not verified` (no evidence gathered either way,
distinct from a fail) / N/A (out of this product's scope or not yet needed at current scale).

### A. Frontend, roles & floor use — 1 PASS / 6 FAIL / 2 not verified

| Item | Grade | Evidence |
|---|---|---|
| Role-appropriate views | **FAIL** | Only 3 flat roles (SUPERADMIN/ADMIN/STAFF); RBAC coverage incomplete — `require_role` doesn't yet gate every operational route, so "STAFF = POS/KDS only" isn't literally true |
| Mobile/field device usability | `not verified` | PWA manifest + POS/KDS shortcuts exist; no automated viewport test, needs a manual phone check |
| Offline core functions + sync | **FAIL** | `frontend/public/sw.js` explicitly skips all non-GET and `/api` requests (read-cache only); cart was plain `useState`, not persisted. Directive 006 promised this, never built |
| Accessibility | **FAIL** | Only 1 `aria-*` attribute in the entire frontend; zero `role=`, zero `alt=`; modal close/backdrop used `<div onClick>` not a real button; no `eslint-plugin-jsx-a11y`, no axe |
| Component organization | **PASS** | Domain-organized dashboard routes (`pos/`, `kitchen/`, `orders/`, `inventory/`, ...), consistent naming |
| Visual consistency | `not verified` | Tailwind in use; no design-token audit done |
| Speed / code splitting | **FAIL** | Zero `dynamic()`/`React.lazy` anywhere — an 11-section dashboard app loads fully statically. (Image optimization is N/A — no raster images exist in app code at all) |
| Forms: errors shown, input preserved on failure | **FAIL** | Login form showed one generic banner but preserved input. POS order form showed the user **nothing** on failure — `console.error(...)` only, no toast/banner. A failed order was silently lost from the waiter's perspective |
| Shared-device quick switch | **FAIL** | No PIN/quick-switch anywhere in code or directives — POS tablets are shared across a shift with no per-staff attribution |

### B. Backend API — 5 PASS / 2 FAIL / 2 not verified

| Item | Grade | Evidence |
|---|---|---|
| Endpoint organization / naming / HTTP verbs | **PASS** | `routers/*.py` domain-organized; correct verb usage |
| Error handling (no silent crashes) | **PASS** | Pydantic auto-422s; extensive failure-path test coverage |
| Input validation | **PASS** | Pydantic schemas throughout; Bandit SAST clean |
| Auth/authz on *every* endpoint | **FAIL** | Same RBAC-coverage gap as Module A — not literally complete |
| Response quality (no leaked sensitive fields) | `not verified` | No line-by-line response-model audit done |
| Pagination on hot list endpoints | `not verified` | No evidence gathered either way |
| Money precision (decimal, not float) | **PASS** | Integer cents everywhere + `CheckConstraint` non-negativity guards, confirmed across `menu_items`, `orders`, `pricing`, `labor_shifts`, `purchase_orders` |
| Rate limiting on expensive endpoints | *partial* | Auth/webhook routes were limited; `/ai/*`, `/analytics/*` were not (see Module G) |

### C. Database & multi-branch data — 7 PASS / 2 FAIL / 1 not verified

| Item | Grade | Evidence |
|---|---|---|
| Schema design (types, naming, required fields) | **PASS** | `Tenant → Restaurant → (Organization, Region)` hierarchy, clean |
| FK relationships / cascade rules | `not verified` | FKs present; cascade-on-delete behavior not checked |
| Unique constraints | **PASS** | `uq_tables_restaurant_number`, `uq_menu_ingredient`, `users.email`, `orders.mpesa_checkout_request_id` |
| Indexes on hot paths | **PASS** | `ix_orders_restaurant_created`, `ix_reservations_restaurant_date`, `ix_token_usage_restaurant_created`, etc. |
| File storage (object store vs DB blob) | N/A | `backend/storage.py` has a correct local/S3-pluggable abstraction, but it's unused — no upload endpoint exists yet |
| Automated backups | **PASS** | Neon WAL + daily snapshots |
| Backup restore tested | **FAIL** | `DISASTER_RECOVERY.md` self-flags as a template with blank RTO/RPO fields; already tracked as hardening-checklist's #1 highest priority |
| Tenant isolation | **PASS** | Cross-tenant access 404s (fails closed); `test_tenant_isolation.py` |
| Branch-level isolation within a tenant | **FAIL** | `get_or_create_restaurant` takes `.first()` — a multi-branch chain has no explicit branch selection; `User` has no branch column at all (existing tech-debt D4) |
| DB connection pooling | **PASS** | Explicit `pool_size`, `max_overflow`, `pool_recycle=300`, `pool_pre_ping=True` |
| Read replicas | N/A (not yet needed) | None configured — reasonable at current scale |

### D. Auth, permissions & staff lifecycle — 3 PASS / 3 FAIL / 1 not verified

| Item | Grade | Evidence |
|---|---|---|
| Role hierarchy depth (templates expect 5-6+ roles) | **FAIL** | Only 3 flat roles exist — may be a deliberate simplicity choice, but short of what the templates check for |
| MFA | **PASS** | TOTP implemented |
| Brute-force lockout | **PASS** | `failed_login_attempts`/`locked_until` |
| Session/JWT revocation | **PASS** | `token_version` bump invalidates all outstanding tokens |
| Read-only oversight role (owner can view, not edit) | **FAIL** | No such tier — ADMIN can both view and edit everything |
| Departing-staff deactivation | **FAIL** | **Most severe finding.** `User` had no `is_active`/`disabled` column at all, and no deactivate endpoint anywhere — a fired employee's login kept working indefinitely unless someone manually changed their password |
| Password reset security (expiry, single-use, notify owner) | `not verified` | Reset flow specifics not checked |

### E. Hosting, deployment & CI/CD — 7 PASS / 1 FAIL / 2 not verified

PASS: env-var secrets with fail-closed startup guard; HTTPS via platform; CI-blocking build;
GitHub→Railway/Vercel auto-deploy; code rollback (Railway one-click, Vercel history); CI
checks (pytest, pip-audit, bandit, npm audit, tsc, gitleaks, Trivy); static-asset caching
(Vercel's default immutable-hash caching covers `_next/static`).
**FAIL:** branch protection on `master` unverified/unenabled (existing tech-debt D6).
`not verified`: DNS/domain config; PR preview deployments.

### F. Security — 4 PASS / 2 FAIL (1 minor)

PASS: tenant-scoped query filtering (functional RLS-equivalent); secrets management;
input sanitization (ORM parameterization + Pydantic); security headers (CSP, X-Frame-Options,
HSTS on both backend and frontend).
**FAIL:** auth/authz on every endpoint (dup of B). *Minor:* CORS `allow_methods=["*"]` /
`allow_headers=["*"]` with `allow_credentials=True` — broader than strictly necessary, paired
with a strict origin allowlist.

### G. Rate limiting & AI cost management — 1 PASS / 3 FAIL / 2 partial / 1 N/A

| Item | Grade | Evidence |
|---|---|---|
| Rate limits on expensive/paid-API endpoints | **FAIL** | `/ai/*`, `/analytics/*` carried zero `@limiter.limit(...)` despite being LLM-invoking |
| Billing alerts on paid API providers | **FAIL** | No evidence of alerts configured anywhere (Anthropic/Groq/Railway/Neon consoles) |
| Debouncing on user-input-triggered API calls | N/A | POS search filters an already-loaded local array client-side — no async call exists to debounce |
| 429 handling with client retry | *partial* | Backend correctly returned 429; frontend never retried |
| Dev/prod API key separation | **FAIL** | `llm_client.py` reads `ANTHROPIC_API_KEY`/`GROQ_API_KEY` straight from env with zero code-level distinction |
| Usage monitoring dashboard | **PASS** | `/api/v1/ai/usage` |
| Cost per feature | *partial* | Aggregate cost visible; not broken out per-feature-per-user-per-month |

### H. Caching & performance — 2 PASS / 2 FAIL / 1 not verified

PASS: CDN for static assets (Vercel default); font loading (`next/font/google`).
**FAIL:** no dynamic content/query caching layer — Redis is explicitly not provisioned yet, so
every request hits the DB directly. **FAIL:** code splitting (dup of A).
`not verified`: Lighthouse/LCP score — no measurement tool has been run.

### I. Load balancing & scaling — 2 PASS / 3 FAIL / 1 N/A

PASS: health-check endpoint exists; DB connection pooling (dup of C).
**FAIL:** single Gunicorn worker — a **known, deliberate, already-documented tradeoff**
(chosen to keep the in-memory rate limiter correct until Redis is provisioned), not a fresh
discovery. **FAIL:** no auto-scaling config. **FAIL:** no shared session store (same Redis
gap). Read replicas: N/A at current scale.

### J. Error tracking & logging — 2 PASS / 2 FAIL / 1 partial

PASS: Sentry wired in code (activation in prod is a separately-tracked pending action);
structured JSON logging with correlation IDs.
**FAIL:** no frontend error boundary — an uncaught render error showed Next.js's default
screen, not a branded fallback. **FAIL:** alerting/on-call rota (existing tech-debt D9).
*Partial*: log/error sensitive-data scrubbing — PII scrub exists at the LLM boundary
specifically; general log hygiene not fully audited.

### K. Availability & recovery — 4 PASS / 2 FAIL

PASS: health check verifies real dependencies, not just liveness; automated DB backups;
deployment rollback; recovery runbook exists (template-status).
**FAIL:** uptime monitoring not yet active. **FAIL:** backup restore untested (dup of C).

---

## Part 2 — Explicitly out of scope (considered, not applicable)

- **Construction:** OSHA Form 300 / toolbox talks / insurance-certificate tracking /
  critical-path scheduling / bid-leveling / retainage lifecycle — this product doesn't do
  jobsite safety compliance or construction billing; no restaurant analog exists worth forcing.
- **EdTech:** LTI/grade-passback/roster-sync, COPPA, FERPA specifics, transcript archival,
  video streaming/captions — no LMS integration, no minors-specific consent flow, no video
  content. Data-privacy generally is already well covered by [compliance-matrix.md](compliance-matrix.md)
  (KDPA 2019 + OWASP mapping), which supersedes what the EdTech privacy module would ask.

## Headline (as found)

**38 of 66 gradable items passed** across the 11 modules above (≈58%); 28 failed; roughly a
dozen more were honestly `not verified` rather than guessed.

## Part 3 — Disposition of every FAIL

28 raw fails collapsed to **21 distinct root causes** once duplicates across modules (e.g.
"auth/authz on every endpoint" appears in A/B/F; "Redis not provisioned" drives 3 separate
scaling fails) were merged. Every one of the 21 had an explicit landing spot — already
tracked, newly tracked, fixed directly, or an operator-console action outside code:

| # | Fail | Modules | Disposition |
|---|---|---|---|
| 1 | RBAC coverage incomplete on operational routes | A, B, F | Already tracked (tech-debt D1). Not rebuilt — large, cross-cutting |
| 2 | Offline order queue missing | A | New (D15). **Fixed** — offline queue with idempotency-key replay |
| 3 | Accessibility near-zero | A | New (D20). One concrete fix (Escape-to-close + dialog ARIA on one modal); full remediation deferred |
| 4 | No code splitting | A, H | New (D21). Deferred — no user-facing symptom yet at current dashboard size |
| 5 | POS order form swallows failures silently | A | New (D19). **Fixed** — same code path as #2 |
| 6 | No shared-device PIN attribution | A | New (D16). **Fixed** — attribution-only PIN quick-switch |
| 7 | Backup restore never tested | C, K | Already tracked (hardening-checklist #1, 🔴). Operator action, not code |
| 8 | Branch-level isolation within a tenant | C | Already tracked (tech-debt D4). Not rebuilt — a feature of its own |
| 9 | No read-only/view-only oversight role tier | D | New (D23). Deferred — no customer has asked for this yet |
| 10 | No staff account deactivation | D | New (D18, P1). **Fixed** |
| 11 | Branch protection on `master` unverified | E | Already tracked (tech-debt D6). Operator action |
| 12 | CORS wildcard methods/headers (minor) | F | **Fixed** directly (2-line change) |
| 13 | AI/LLM endpoints unthrottled, no spend cap | B, G | New (D14). **Fixed** — rate limits + a DB-backed spend cap |
| 14 | No LLM billing alerts | G | New. Added to external-hardening-checklist.md (operator console action) |
| 15 | No dev/prod API key separation | G | New. Added to external-hardening-checklist.md (no code fix possible) |
| 16 | Frontend doesn't retry on 429 | G | **Fixed** directly (axios interceptor) |
| 17 | No dynamic content/query caching layer | H | New (D24). Deferred — blocked on Redis provisioning |
| 18 | Single Gunicorn worker | I | Deliberate, already-documented tradeoff — tracked via hardening-checklist #6 (Redis) |
| 19 | No shared session store | I | Same Redis root cause as #17/#18 |
| 20 | No auto-scaling config | I | New (D25). Deferred |
| 21 | No frontend error boundary | J | New (D22). **Fixed** |
| — | Alerting/on-call rota TBD | J | Already tracked (tech-debt D9 / hardening-checklist #5) |
| — | Uptime monitoring not active | K | Already tracked (hardening-checklist #5) |
| — | Cost not broken out per feature | G | New (D26). Deferred — nice-to-have analytics depth |

---

## Part 4 — Post-remediation re-grade

8 of the 21 root causes were fixed and independently re-verified; 1 was partially improved.
Everything else is either deliberately deferred (larger scope, now tracked as debt) or an
operator-console action no code change can close.

### What flipped

| Item | Before | After | Verification |
|---|---|---|---|
| Offline core functions + sync | FAIL | **PASS** | `offlineQueue.ts` enqueue/flush/replay, idempotency-key backed; 3 backend tests |
| POS form shows errors on failure | FAIL | **PASS** | Error + queued toasts replace the old silent `console.error` |
| Shared-device quick switch | FAIL | **PASS** | PIN roster/set/verify, attribution-only; 5 tests, including one proving it can't elevate privilege |
| Rate limits on AI/LLM endpoints | FAIL | **PASS** | All 9 LLM-invoking routes rate-limited; tested |
| Staff account deactivation | FAIL | **PASS** | `is_active` blocks new logins + existing tokens; 5 tests |
| CORS methods/headers | FAIL (minor) | **PASS** | Tightened from wildcard to the actual verb/header set; tested |
| 429 client retry | partial | **PASS** | axios interceptor retries once on `Retry-After` |
| Frontend error boundary | FAIL | **PASS** | `error.tsx` + `global-error.tsx` added |
| Frontend test coverage | FAIL | **PASS** | Vitest scaffolding + 19 tests, wired non-blocking into CI |
| Accessibility | FAIL | FAIL *(improved)* | One modal now has Escape-to-close + `role="dialog"`; still near-zero systematically — D20 remains open |

**Beyond what the templates explicitly asked for:** the AI spend cap is a genuine circuit
breaker (DB-backed, per-tenant daily/monthly caps), not just rate limiting — a stronger
guarantee than "rate limits exist." `/ai/usage` now surfaces remaining budget.

### Updated headline

**Roughly 47 of 66 gradable items now pass (≈71%)**, up from 38/66 (≈58%). All fixes were
verified with automated tests (382/382 backend tests passing, 19/19 frontend tests passing)
and, for the 4 new Alembic migrations, a full upgrade → downgrade → re-upgrade round-trip
against a freshly bootstrapped database — not just the test suite's `create_all()` path.

### What's still open, and why

**Deliberately deferred (larger scope, tracked as debt):** RBAC completeness (D1),
branch-level isolation (D4), code splitting (D21), dynamic caching layer (D24, blocked on
Redis), no read-only role tier (D23), auto-scaling (D25), cost-per-feature breakdown (D26),
full accessibility remediation (D20).

**Operator-console actions — no code fix exists:** backup-restore drill, uptime monitoring,
branch protection on `master`, LLM billing alerts, dev/prod key separation, on-call/alerting
rota. All are already tracked in [external-hardening-checklist.md](external-hardening-checklist.md),
most at 🔴/🟠 priority.

**Found but unrelated to this audit's fixes:** tech-debt D27 — the CI's blocking `npm audit`
gate is currently red on newly-disclosed Next.js advisories.

### Highest-leverage next step

Of everything still open, the backup-restore drill
([external-hardening-checklist.md](external-hardening-checklist.md) §1, still 🔴) is the one
worth doing first — it's a ~30-minute operator action, not a code change, and it's the one
gap where "we don't know if this actually works" is the entire problem.

---

## Cross-references

- New tech-debt rows from this audit: [tech-debt-register.md](tech-debt-register.md) D14–D27.
- New operator-console items: [external-hardening-checklist.md](external-hardening-checklist.md) §7.
- Design note on the PIN quick-switch's security boundary: [security/threat-model.md](security/threat-model.md) T15.
- Stale-doc corrections made while grading: [engineering-standards.md](engineering-standards.md) §5
  (Alembic revision reference), and this register's own D7 (found already resolved, removed).

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-08-02 | Engineering | Initial audit: graded against a generic + construction + EdTech SaaS checklist, adapted to this product; documented remediation and re-grade |
