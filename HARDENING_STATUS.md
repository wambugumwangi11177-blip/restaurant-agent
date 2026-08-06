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

## Capture-layer gap — closed 2026-08-06

An audit of *what the running application actually writes* found that several of
the most built-out analytics modules were reading tables no production code path
ever populated. The only writer was `populate_production.py`, the demo seeder —
so on a real restaurant those modules always took their empty branch. The
analytics weren't broken; they were starved. Suite went 362 → **412 green**.

| Table | Was written by | Now written by | Unblocks |
|---|---|---|---|
| `PrepTime` | seeder only | KDS status transitions (`routers/orders.py`) | `ai/kds_intelligence.py` — station p95s, bottleneck severity, queue depth, delay risk (~12 analytics) |
| `MenuIngredient` | **nothing — no API existed** | `PUT /menu/{id}/recipe` | theoretical usage, `ai/graph` cascade traversal, derived `cost_price` |
| `InventoryItem.quantity` on sale | manual `/receive` + `/adjust` only | `stock_ledger.consume_for_order` | food-cost %, depletion prediction, reorder intelligence |
| `StaffMember` / `LaborShift` | **nothing, not even the seeder** | `routers/staff.py` + clock-in/out | `ai/labor/intelligence.py`; `ai/roi/savings.py` stops falling back to its `DEFAULT_HOURLY_RATE_CENTS` constant |

Second-order win: with recipes in place `MenuItem.cost_price` becomes **derived**
(Σ quantity × ingredient cost) instead of hand-typed, so a supplier price change
updates every affected dish's margin without anyone re-entering anything.

Also closed the same day:
- **Billing is enforceable.** Was `provider="manual"` with a plan string an admin
  set on themselves and nothing reading it. Now a real state machine (trial →
  paid period → grace → past_due → canceled), effective status computed on read
  rather than by a job, and `require_active_subscription` gating `/ai/*` with 402.
  Payment *processor* stays pluggable — `extend_period()` is the single seam.
  **POS, KDS, orders, menu, payments and the dashboard are deliberately never
  gated:** non-payment costs the analysis, never the ability to trade.
- **Branding unified** to Leviii AI (app previously said "Chakula" in layout,
  login, order page, `manifest.json`, `sw.js` while every doc said Leviii AI).

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
