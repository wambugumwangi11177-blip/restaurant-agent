# Production Hardening — Status (as of 2026-07-11)

Working record of the hardening effort so it can be picked up in a fresh session.
Branch **`feat/phase1-production-hardening`** is **pushed to origin** (6 commits).
Full test suite **green (201 passed)**, Bandit clean. **PR not yet created**
(no `gh`/token in the working env) — open it at:
https://github.com/wambugumwangi11177-blip/restaurant-agent/pull/new/feat/phase1-production-hardening

## Commits on the branch
| SHA | What |
|---|---|
| 83cc3d8 | Phase 1: XFF rate-limit fix, Stripe→501, menu IDOR fix, body-size limit, LLM/Twilio timeouts, gunicorn timeout, DB pool sizing, FK indexes (migration 015), JSON logging + correlation IDs, Bandit/npm-audit/pytest-cov in CI, `.env.example` |
| 4362786 | Phase 2: DB CHECK + composite-unique constraints (migration 016, deploy-safe `NOT VALID`), `backend/DISASTER_RECOVERY.md` |
| cb97fae | Fixed wall-clock-flaky stock tests (deterministic) |
| 29f188b | Startup config guard (`startup_checks.py`) + fixed pre-existing migration-009 test → suite green |
| 638a61a | API versioning (`/api/v1/*` canonical, legacy paths kept but hidden) + JWT session revocation (`token_version`, migration 017, `POST /api/v1/auth/logout-all`) |
| 79908e8 | AIOps `GET /api/v1/ai/usage` (token spend / agent latency / grounding) |
| 3665c7d | Security: `require_role` RBAC enforced (admin-only exports/erasure/profile), registration password policy, Argon2id pin, `test_rbac.py` |
| 7c4cff0 | Marketing: read-only offer engine (`GET /ai/marketing`) + owner-approved promo/win-back sends (background, consent+opt-out gated), narrator task, `test_marketing.py` |
| 6dd8458 | Frontend: AI command-center refactor (shared module primitives) + `/dashboard/marketing` and `/dashboard/ai-ops` pages |

## Done
- **Phase 1 (DO-NOW): complete.** All security/resilience/observability/CI items.
- **Phase 2 (PRE-CLIENT): code parts done** — DB constraints, FK indexes, API
  versioning, JWT revocation, DR runbook, startup guard, AIOps usage endpoint.
- **RBAC** (Phase-3 item, pulled forward): `require_role` now gates admin-only
  routes; registration password policy; Argon2id pinned.
- **Marketing module**: consent-gated offer engine + owner-approved sends.
- **Frontend**: AI command center refactored into independent, self-fetching
  sections; new marketing + AI-ops dashboards.
- **Docs set** added under `docs/` (engineering standards, architecture, ADRs,
  security threat model, trust-center, compliance matrix, governance, etc.).
- (model-version persistence + grounding suppression were already built.)
- **Verification (2026-07-11):** backend suite **212 passed**, Bandit clean at
  `-ll`, frontend `tsc --noEmit` clean, `next build` green (18 routes),
  all internal doc links resolve.

## Not done — needs YOU (ops access) or deliberately deferred
**These four genuinely require your accounts/credentials — no code can do them:**
- [ ] Enable Railway Postgres **backups** + run one **restore drill** (steps in `backend/DISASTER_RECOVERY.md`)
- [ ] Set/verify prod env on Railway: **`MPESA_CALLBACK_TOKEN`** (prod won't boot without it when M-Pesa is configured), **`CORS_ORIGINS`**
- [ ] Sentry alert rules · UptimeRobot on `/health` · OWASP ZAP baseline
- [ ] Confirm/enable GitHub **branch protection** on `master` (require PR + CI green)

**Deferred by design (a product decision or waits for traffic):**
- [ ] **`ON DELETE` cascade** — no delete flow triggers it and erasure keeps orders for tax integrity; needs a decision on delete semantics
- [ ] Migrate frontend to `/api/v1/*`, then drop the legacy mount — legacy mount works today; broad, risky sweep left until deliberately scheduled
- [x] ~~AIOps extras: prompt versioning, quality-drift alarm, written fallback policy~~ **DONE** (commit 7243228, migration 018, docs/ai-governance.md v1.2)
- Phase 3 (AT-SCALE): Redis, durable queue, load/stress testing, SLOs, feature flags, OTel, pentest — intentionally deferred until traffic. (RBAC pulled forward — done, see commit 3665c7d.)

## Pending requests (open when the chat switched)
- Pre-merge process was given in chat — offered to save as `backend/LAUNCH_CHECKLIST.md`.
- Railway-account **migration runbook** given in chat (move accounts + repoint Vercel/Safaricom/Twilio; the 3 silent-breakage points: Safaricom CallBackURL, Twilio webhook, backend `CORS_ORIGINS`). Awaiting 2 answers: keep DB data or start fresh? move the Vercel project or just its API-URL env var? — then save as `backend/MIGRATION_RUNBOOK.md`.

## Notes for whoever continues
- The RBAC / password-policy / marketing / frontend-refactor work that was
  previously uncommitted is now **committed** (3665c7d, 7c4cff0, 6dd8458) and
  green. Completed a missing `SupplyChainSection` in the AI page along the way.
- Test env: venv at `backend/.venv` (gitignored). Run: `cd backend && .venv/Scripts/python.exe -m pytest -q` with `LOG_FORMAT=plain`.
- Migrations 015/016/017/018 are idempotent, dialect-aware, and run at container start.
