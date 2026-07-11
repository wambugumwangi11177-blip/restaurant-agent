# Leviii AI — Engineering Standards

| | |
|---|---|
| **Reference** | LAI-ENG-001 |
| **Classification** | Internal |
| **Audience** | Engineers, technical due diligence |
| **Version** | 1.0 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose & scope

How code moves from change to production safely: source control, CI gates, security
scanning, testing, releases, hotfixes, rollback, and incident review. Grounded in
`.github/workflows/ci.yml`, the Alembic migration history, and the runbook. Items that are a
**policy/practice** rather than a machine-enforced gate are labelled as such — where a
setting lives outside this repo (e.g. GitHub branch-protection), it is marked **verify in
GitHub settings** rather than asserted.

---

## 1. Source control & branching

- **GitHub is the source of truth.** Railway and Vercel deploy from it.
- Work happens on **feature branches** (e.g. `feat/...`); changes reach `master` via pull
  request. (Observed convention; `master` is the default/deploy branch.)
- **Branch protection** on `master` (require PR, require CI green, no force-push) —
  **policy; verify/enable in GitHub repo settings.** Not encoded in this repo.

## 2. CI requirements (`.github/workflows/ci.yml`)

Runs on every `push` to main/master and every `pull_request`. Four jobs:

| Job | Tool | Gate |
|---|---|---|
| `pytest` | pytest + coverage | **Blocking** on test failure. Coverage measured (`--cov`), not yet gated on a floor |
| `dependency-audit` | `pip-audit` | **Blocking**; 6 advisories ignored explicitly by id with documented justification (no blanket `continue-on-error`) |
| `sast` | Bandit (`-ll`) | **Blocking** at medium+ severity; currently clean |
| `frontend-ci` | `npm run build` + `tsc --noEmit` + `npm audit` | Build/typecheck **blocking**; `npm audit --audit-level=high` non-blocking pending baseline triage |

**Standing rules encoded in CI comments:**
- New dependency CVEs fail the build (each ignore has a reason + tracking note).
- New medium/high Bandit findings fail the build; the one benign finding (`0.0.0.0` bind,
  required in-container) carries an inline `# nosec` with justification.

## 3. Security in the SDLC

| Stage | Control |
|---|---|
| Design | Threat model maintained ([security/threat-model.md](security/threat-model.md)) |
| Code | ORM parameterization; typed Pydantic input; secrets via env only |
| Review | PR review before merge (**policy**); security-relevant diffs get explicit scrutiny |
| Build | pip-audit + Bandit SAST + frontend build/typecheck (all in CI) |
| Test | pytest suite incl. auth brute-force, tenant-isolation (IDOR), RBAC, payment/webhook |
| Deploy | Fail-closed startup config guard (`backend/startup_checks.py`) |
| Run | Sentry monitoring; append-only AI-action audit log |
| Respond | Incident Response Plan (LAI-IRP-001), lessons-learned within 7 days |

## 4. Testing requirements

- **Suite:** 31 `test_*.py` files under `backend/tests/`, run in CI.
- **Isolation:** each test gets a throwaway SQLite DB and resets process-wide singletons
  (rate limiter, event bus, caches) via `conftest.py` — so tests are order-independent.
- **Security-critical tests are mandatory** for auth, tenancy, and payments:
  `test_auth_security.py` (lockout + rate-limit → 429), `test_tenant_isolation.py` (IDOR),
  `test_rbac.py` (role gating + password policy), `test_mpesa_*` / `test_*_webhook.py`.
- **Expectation:** a change to auth, tenant scoping, RBAC, or payments **must** ship with or
  update a test. Coverage is measured; a `--cov-fail-under` floor will be set once the
  baseline is characterised.

## 5. Database migrations

- All schema changes go through **Alembic** (`backend/alembic/versions/`), currently through
  revision `017`. No ad-hoc schema edits.
- Data-integrity constraints are added via migration and back-filled safely (e.g.
  `016_add_integrity_constraints.py` applies CHECKs `NOT VALID` then validates).

## 6. Release, hotfix & rollback

- **Release:** merge to `master` → CI green → Railway (API) and Vercel (frontend) deploy.
- **Rollback:** Railway redeploys any prior GitHub commit (one click); Vercel keeps full
  deployment history (instant rollback). Database restore via Neon point-in-time recovery.
  Procedures: `backend/DISASTER_RECOVERY.md` and the BCP (LAI-BCP-001 §04).
- **Hotfix:** branch from `master`, minimal fix + test, fast-track PR, deploy, then
  backport/verify. SEV-1 timelines per SLA (LAI-SLA-001 §04).

## 7. Incident review

- Every SEV-1 triggers a mandatory **lessons-learned within 7 days** (IRP §03, BCP §07).
- Findings update controls, tests, and these standards. Postmortems are archived
  ([../docs/postmortems/](.) — starts at first incident).

## 8. Coding conventions (observed)

- Deterministic business logic in Python; **the LLM never computes a figure.** It is confined
  to two non-computing roles — WhatsApp free-text replies and grounded narration of an
  already-computed analytics payload (unbacked numbers are redacted). Label AI-vs-deterministic
  honestly — a standing project rule.
- Shared dependencies extracted (e.g. `routers/deps.py`) to avoid divergent copies.
- Comments explain *why* (security rationale, edge cases), not just *what*.

## Open items

- Set `--cov-fail-under` once baseline coverage is known.
- Confirm/enable GitHub branch protection on `master`.
- Make `npm audit` blocking after baseline triage.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial standards from CI + repo audit |
