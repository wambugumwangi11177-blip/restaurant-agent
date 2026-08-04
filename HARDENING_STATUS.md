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

## Notification reliability pass (2026-08-04)
Prompted by "make sure the notifications work" ahead of going out to sell.

**The gap:** the notification chain failed *silently by design*. `twilio_client.send()`
returns `{"status": "not_configured"}` and writes a log line when config is missing, and
every caller treats a send as best-effort — nothing raises. `/health` and `/health/db`
both stayed green through a total notification outage. Nothing validated Twilio at boot.

**Worst case found:** `TWILIO_WHATSAPP_FROM` *defaults* to Twilio's shared public
sandbox number. A deploy that forgets to set it gets `sent` back from Twilio for every
message while reaching only handsets that texted the sandbox join code — and those
opt-ins expire after 72h. No error anywhere. Now detected and warned about explicitly.

- **`backend/notifications_health.py`** — one shared definition of "notifications are
  broken": transport config (read from the same module `send()` uses, so it can never
  certify a broken deploy as healthy), sandbox-sender detection, scheduler-job
  registration, per-restaurant owner-phone routing, and the recent send-failure rate.
  Opt-out suppressions are explicitly *not* counted as failures.
- **`GET /health/notifications`** — 503 when nothing can be delivered, 200 + detail when
  degraded. Point UptimeRobot here alongside `/health`. Leaks no credentials.
- **`startup_checks`** now warns loudly on notification config — deliberately SOFT even
  in production: a POS that refuses to boot because WhatsApp is misconfigured is worse
  for a restaurant than a late briefing.
- **`execution/verify_notifications.py`** — preflight before a demo or an onboarding.
  Read-only by default (safe against prod); `--send +2547…` puts one real message
  through to prove delivery, not just configuration; `--url` checks a deployed instance.
- Tests: `test_notifications_health.py` (15). Suite **377 passed** (was 362), Bandit
  clean at `-ll`, frontend `tsc --noEmit` clean, `next build` green (18 routes).

## Go-to-market (2026-08-04)
- **`directives/015_cold_outreach.md`** — door-to-door and cold-call SOP: the two good
  walk-in windows (10:00–11:30, 15:00–17:00 EAT) and the two hours that guarantee a no,
  qualification signals, gatekeeper and decision-maker scripts, doorstep objections,
  follow-up cadence, and the funnel targets to steer on. Builds on the existing
  `docs/sales/talk-track-internal.md` rather than duplicating it.
- **`execution/outreach_pipeline.py`** — deterministic lead pipeline (add / log / stage /
  today / show / stats). Funnel conversion is computed on the deepest stage each lead
  ever reached, so a lost deal stays in the demo denominator instead of quietly
  inflating the close rate. Data lands in `outreach/`, self-gitignored — it holds real
  prospects' phone numbers and must never be committed.

## Not done — needs YOU (ops access) or deliberately deferred
**These four genuinely require your accounts/credentials — no code can do them:**
- [ ] Enable Railway Postgres **backups** + run one **restore drill** (steps in `backend/DISASTER_RECOVERY.md`)
- [ ] Set/verify prod env on Railway: **`MPESA_CALLBACK_TOKEN`** (prod won't boot without it when M-Pesa is configured), **`CORS_ORIGINS`**
- [ ] Set **`TWILIO_SMS_FROM`** and a **real `TWILIO_WHATSAPP_FROM`** (not the sandbox
      default) on Railway, then run `py execution/verify_notifications.py --url <prod>`
      and once `--send <your own number>` to confirm a message actually arrives on a
      handset. Until this is done, notifications are the single most likely thing to be
      quietly broken in front of a paying restaurant.
- [ ] Sentry alert rules · UptimeRobot on `/health` **and `/health/notifications`** · OWASP ZAP baseline
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
