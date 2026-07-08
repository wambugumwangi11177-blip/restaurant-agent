# Production Readiness Roadmap

## Purpose
`012_agentic_roadmap.md` tracks the AI/orchestration engineering work. This directive is
the wider gate: everything across all phases that must be true before real restaurants
run on this system, with an explicit verification method for each item — not just "built"
but "checked." Update this file's checkboxes as work lands; don't let it drift into
aspirational copy the way the original sprint plan did.

## Auth/perimeter security hardening pass (2026-07-07, second pass)
Prompted by an explicit "check the security, protect it from hacking in all the ways
possible" request. Scope: authentication abuse, response hardening, and a systematic
audit of the classic web attack surface (SQLi, XSS, verbose errors, dependency CVEs).
Every fix below is verified — either with a new passing test or a direct grep/build check,
not just "should be fine."

**Login had zero brute-force protection (was: no failed-attempt tracking, and slowapi was
configured in `main.py` but never actually applied to any route — a circular-import
problem, since routers importing from `main.py` would be circular).** Fixed with two
complementary layers: (1) extracted the shared `Limiter` into new `rate_limit.py` so both
`main.py` and router files can import it; applied `@limiter.limit("10/minute")` to
`/api/v1/auth/login`, `@limiter.limit("5/hour")` to `/api/v1/auth/register`, and
`@limiter.limit("20/minute")` to the unauthenticated `/orders/public` (real M-Pesa STK-push
cost/abuse vector). (2) Added per-account lockout — `User.failed_login_attempts` /
`User.locked_until` columns (migration `007_add_login_lockout_fields.py`, idempotent via
the established inspector-check pattern), 5 failed attempts locks the account for 15
minutes. Lockout is checked *before* password verification, so a locked account never
leaks a password-verification timing signal. Rate limiting defends per-IP (defeated by
proxy rotation); lockout defends per-account (survives IP rotation) — deliberately layered,
neither alone is sufficient. Tests: `test_auth_security.py` (4 tests — account actually
locks at the threshold, correct login resets the counter, both rate limits actually return
429 rather than just having the decorator present).
  - Test-isolation hazard found while writing these tests: slowapi's `Limiter` is a
    process-wide in-memory singleton keyed by IP, same class of hazard as the existing
    `database.py`/`executive.py`/`events/bus.py` singletons documented in `conftest.py`.
    Without resetting it, an earlier test's counters bleed into a later, unrelated test.
    Fixed: `limiter.reset()` added to the `db_env` fixture, documented as hazard #4.

**No security response headers anywhere (was: every response, including the JSON API
responses served to the frontend, was missing browser-enforced defenses).** New
`middleware/security_headers.py`: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`, a restrictive `Permissions-Policy`, and
HSTS (safe unconditionally — Railway terminates TLS in front of this app). No CSP set here
deliberately: this is a JSON API, CSP is the frontend's (Vercel/Next.js) responsibility for
the pages it actually renders.

**SQLi / XSS / verbose-error audit (systematic grep, not spot-check).** SQL injection:
grepped for `execute(`, `text(`, and raw string-formatted SQL across `backend/`— the only
raw `execute()` calls found are static strings (`SELECT 1` health check, static DDL in
migration `001`); everything else goes through the SQLAlchemy ORM/query-builder. No
finding. XSS: grepped frontend for `dangerouslySetInnerHTML`/`eval(` — one use in
`layout.tsx`, but it's a hardcoded static service-worker-registration script with no user
input flowing into it. No finding. Verbose errors: grepped for `HTTPException(status_code=500`
and `detail=str(e)` patterns — none found; the one `exc_info=True` in `routers/ai.py` is a
server-side log call, not returned to the client. No finding.

**Frontend dependency CVEs (`npm audit`: 14 findings — 1 low, 7 moderate, 6 high).** Ran
`npm audit fix` (non-breaking): resolved 10 of 14, down to 4 remaining (3 moderate, 1 high
— Next.js DoS/cache-poisoning/SSRF advisories, and a `uuid` bounds-check issue pulled in via
`next-auth`). Verified `npm run build` still succeeds after the fix. The remaining 4 only
resolve via `npm audit fix --force`, which bumps Next.js to `16.2.10` (major version, outside
the current dependency range) and downgrades `next-auth` to `3.29.10` (breaking change to
the actual login flow). Deliberately deferred rather than bundled into this pass — none of
the 4 are critical/RCE, and stacking a breaking auth-library downgrade on top of changes to
the login endpoint's own security logic is exactly the kind of compounded risk that deserves
its own dedicated test window, not a same-pass bundle.

### Deliberately NOT done (real, currently-outstanding — flagged, not fixed)
- **Neon production DB password rotation.** The current password has been pasted into chat
  multiple times this session while debugging migrations — anyone with access to that
  conversation history has it. User explicitly asked to skip rotating it in this pass.
  **This is a live exposure, not a theoretical one — rotate via the Neon dashboard + update
  the Railway `DATABASE_URL` env var as soon as convenient.**
- **JWT stored in frontend `localStorage`.** Vulnerable to exfiltration via any XSS that
  does land (defense-in-depth gap, not an active hole given the XSS audit above found
  nothing exploitable today). Migrating to an httpOnly cookie is a real frontend+backend
  change (CSRF handling needed once you're off a Bearer header), not done in this pass.
- **`npm audit --force` (Next.js 16.2.10 + next-auth 3.29.10).** See above — real fix,
  deliberately deferred pending a dedicated test window for the login flow.

## Security + engineering hardening pass (2026-07-07)
A dedicated security review and engineering-quality review of the session's changes ran,
and every actioned finding was fixed with a regression test proving it. Suite grew 40 → 44.

**Payment integrity (was: unauthenticated M-Pesa callback marks orders paid with no amount
check).** `POST /webhooks/mpesa` now (a) verifies the callback amount against the order
total — rejects any success-coded callback reporting less than the whole-shilling floor of
`order.total`, so a forged/underpaid callback can't settle a large order; (b) settles
atomically — `is_paid` + `payment_method` + `mpesa_receipt` in one transaction in the
webhook, so the 200 ACK to Safaricom can never lie about settlement (previously `is_paid`
was set by the event handler in a separate session/commit that, if it errored, was swallowed
while the ACK still said success — order stuck unpaid, no retry); (c) fires the WhatsApp
receipt via `emit_async` so a slow Twilio call never blocks the callback ACK and a
notification failure can't roll back a settled payment. `on_order_paid_mpesa` is now
notification+audit only (no `is_paid` mutation). Test: `test_underpaid_callback_does_not_settle_order`.

**Dashboard "recent actions" (was: `m.direction` AttributeError swallowed by bare except →
panel silently always empty, on a route that was also shadowed).** Discovered a deeper issue:
`GET /ai/dashboard` is served by `analytics.py` (→ `ops_manager`), which never returned
`recent_ai_actions` at all, while the frontend requires it. Added the feature to the
*actually-served* `ops_manager.get_operations_dashboard` (real outbound messages only,
metering rows excluded). Test: `test_dashboard_recent_actions_includes_outbound_message`.

**Token metering (was: sentinel rows polluting `agent_messages`, and committing the caller's
request session).** New dedicated `token_usage` table (migration `005`); `_log_usage` writes
there via its own short-lived session, never touching the caller's transaction. Test:
`test_metering_writes_token_usage_not_agent_messages`.

**Groq tool-call arguments (was: `"arguments": "{}"` hardcoded, dropping the model's chosen
arguments on multi-turn Groq conversations).** Now preserved via `json.dumps(block.input)`.
Test: `test_canonical_messages_preserve_tool_call_arguments`.

**Owner phone routing (was: `OWNER_PHONE_{id}` env var + O(n) env scan — needs a redeploy to
onboard a restaurant, wrong shape for multi-tenant).** New `Restaurant.owner_phone` column
(migration `006`), settable via `PUT /api/v1/auth/restaurant`, resolved by direct column query
with env-var fallback for backward compatibility. WhatsApp webhook tests now exercise the
column path with env cleared.

**Logging consistency**: `payments/mpesa_client.py` and the orchestrator use `logger`, not
`print`; narrowed the swallowing `except` on the dashboard feed.

### Deliberately NOT done (with reasons — not oversights)
- **Config-object refactor (module-level env reads).** The `importlib.reload` dance in
  `conftest.py` exists because `database.py`/`auth.py`/`twilio_client.py`/`mpesa_client.py`
  read env at import time. The clean fix is a lazy config object, but that's an app-wide
  refactor whose main payoff is test elegance on code that's already working and fully
  tested — blast radius outweighs benefit. Deferred as a deliberate future task.

## Design principles pass — DRY + SSOT fixes (2026-07-07)
Prompted by an explicit design-principles review. Two concrete violations found and fixed,
both verified (not just asserted):

**DRY — the restaurant-lookup pattern had drifted into 8 near-duplicate implementations**
across `ai.py`, `inventory.py`, `orders.py`, `reservations.py`, `menu.py` (×2 inline),
`auth.py` (×2 inline), and `analytics.py` — with 3 *different* behaviors mixed in (some
auto-created a missing restaurant, one raised 404, one silently returned 0). Consolidated
into `routers/deps.py` with two functions, deliberately kept separate rather than merged
into one:
- `get_or_create_restaurant()` — the majority/safe pattern, used by all write-capable
  endpoints and GETs that reasonably expect a restaurant to exist.
- `get_restaurant_or_none()` — read-only, no side effects, used by `auth.py`'s `/me` and
  `analytics.py`'s dashboard helpers specifically because auto-creating data as a side
  effect of a GET request would violate command-query separation.
4 new unit tests in `tests/test_deps.py` covering both functions directly (create-when-missing,
return-existing-without-duplicating, no-side-effect-on-none, return-existing). Full suite
44 → 48, all passing.

**Single Source of Truth — the duplicate `/ai` router routes (flagged earlier this session,
now resolved).** `ai.py`'s shadowed, unreachable copies of `/ai/dashboard`,
`/ai/menu-engineering`, `/ai/revenue-forecast`, `/ai/reservation-insights` (dead code that
was still being read/edited as if live — see the earlier "recent actions" bug fix, which
initially targeted the wrong copy) are deleted. `ai.py` now only contains its genuinely
unique routes (`/ai/pricing` + approve/reject, `/ai/labor`, `/ai/inventory`), which never
overlapped with `analytics.py`. Verified via a live route-registration check: each
previously-duplicated path now has exactly one route object registered, not two.

**`except Exception` audit** (the design-principles review flagged this as worth checking):
scanned the highest-stakes paths (`webhooks.py`, `mpesa_client.py`, `twilio_client.py`,
`auth.py`). Both remaining broad excepts in `webhooks.py` log and re-raise as an HTTP error
(legitimate); `twilio_client.py`'s is a fire-and-forget outbound send whose failure status
is returned to and logged by the caller (legitimate, matches the same
notification-failure-must-not-break-the-core-transaction principle established in the
M-Pesa atomicity fix). No further masked-bug pattern found beyond the one already fixed
(the dashboard's `except Exception: pass`).

## Orphaned modules wired + broken event/scheduler orchestration fixed (2026-07-07)
User asked to check "the others" (profit intelligence, orchestration between modules,
memory) after the real-data verification pass above. Audited every `ai/*` module for
actual reachability and every subscribed event type for whether anything ever emits it —
both were more incomplete than the earlier pass suggested.

**Newly wired routes** (real, complete modules, verified against real production data,
zero route ever exposed them): `GET /ai/profit`, `GET /ai/supply-chain`.
`ai/pricing/analysis.py` and `ai/memory/store.py` turned out to already be wired
indirectly (analysis.py imported by the live `recommendations.py`; memory/store.py called
by executive.py's event handlers) — correcting an earlier overly-broad "orphaned" claim.

**Event/scheduler orchestration — 5 of 7 subscribed event types were never emitted by
anything, 2 of 3 documented scheduler jobs were never registered.** Subscribers and job
functions existed; nothing ever triggered them:
- `main.py`: registered `run_stock_check` + `run_slow_day_check` (previously only
  `morning_briefing`/`po_late_check` ran); de-duplicated `_send_all_morning_briefings`
  (was a near-copy of `brain.run_morning_briefing` instead of calling it).
- `brain.run_stock_check` now emits `STOCK_CRITICAL`/`STOCK_DEPLETED`.
- `reservations.py` emits `RESERVATION_NO_SHOW` on the actual status transition.
- `pricing/recommendations.py`'s `approve_recommendation()` now emits
  `RECOMMENDATION_APPROVED` with real approver identity.
- `routers/ai.py`'s `_safe_run()` emits `AGENT_FAILED` on any caught exception.

3 new tests (`tests/test_event_orchestration.py`) prove emit → handler actually fires,
not just that the emit call exists. Full suite 48 → 51, all passing. Verified live: all
11 `/ai/*` endpoints (9 original + 2 new) return 200 against the real Lavy dataset.

**Flagged, not auto-wired**: `ai/marketing/campaigns.py`'s `run_daily_campaigns()` has a
real side effect — it attempts to send actual WhatsApp winback messages to real customers.
Discovered this only *after* calling it to verify it works (nothing sent, Twilio isn't
configured — that was luck, not a check made beforehand). Deliberately not scheduled or
wired to its events (`CAMPAIGN_LAUNCHED`/`WINBACK_TRIGGERED` exist but have no subscriber)
until there's an explicit decision on cadence/opt-in for customer-facing messages.

## Deployment platform is Railway, not Render — critical findings (2026-07-07)
`render.yaml` was dead config all along; the user deploys on **Railway**
(`restaurant-agent-production-ffd3.up.railway.app`), which uses `backend/railway.json`
(`"builder": "DOCKERFILE"`) → `backend/Dockerfile`, not `render.yaml` or (crucially)
`Procfile`.

**Found via a live 502 + deploy-log check, not assumed:**
1. **Railway's Root Directory was pointing at the wrong folder.** The crash log referenced
   a `check_connection` coroutine in `database.py:140` — that function does not exist
   anywhere in the real `backend/database.py` (45 lines total), only in the *abandoned*
   `restaurant-agent/backend/database.py` (216 lines, async SQLAlchemy). This means
   **the entire session's work — M-Pesa, tenant-isolation security fix, consent gate, all
   6 migrations, all 44 tests, the orchestrator — was never actually deployed.** User needs
   to fix Railway's service Settings → Root Directory to `backend`.
2. **Hardcoded `ENV PORT=8000` in `Dockerfile` fought Railway's injected `PORT`** (Railway's
   dashboard showed 8080) — classic container port-mismatch 502 (app healthy internally,
   edge proxy routing to the wrong port). Fixed: removed the `ENV PORT=8000` line; `$PORT`
   is now read live from whatever Railway actually injects at container start.
3. **`Procfile`'s `release:` migration step was dead code for this deploy path.** Docker
   builds don't read `Procfile` at all (that's Nixpacks/Heroku-only) — so the
   migration-on-deploy fix from earlier in this roadmap never actually ran here. Fixed:
   moved the same `init_db()` + `alembic upgrade head` sequence directly into the
   Dockerfile's `CMD`, before `gunicorn` starts.

**Not yet verified**: whether fixing the Root Directory setting (a Railway dashboard change
only the user can make) resolves the 502 for real — that's the next thing to check once
the setting is changed and Railway redeploys.

## Real-data verification against the actual 107,700-order dataset (2026-07-07)
User asked to verify the agentic software actually works against their real historical
data (restaurant "Lavy", tenant_id=3, 107,700 orders spanning Apr 2024 - Jun 2026 — by far
the largest of the 5 restaurants in production). Created one new STAFF-role test user
(`claude-test@lavy.co.ke`) under Lavy's existing tenant rather than touching any of the
6 real Lavy accounts. Found and fixed 5 real bugs, none of which the SQLite-based local
test suite could ever have caught (small test datasets never trigger N+1 pain; SQLite
silently accepts SQLite-only SQL functions that don't exist on Postgres):

1. **`func.strftime()` — SQLite-only syntax, crashed `/ai/dashboard` outright (500) on
   real Postgres** (`ai/menu_engineer.py`). Fixed with SQLAlchemy's cross-dialect `extract()`.
2. **Severe N+1 in `get_revenue_forecast`** — no eager loading, no date bound (despite an
   unused `thirty_days_ago` variable proving that was the original intent) — a 90+ second
   hang with zero response. Fixed: 30-day bound (sufficient for the function's own WoW/MoM
   math) + `joinedload`.
3. **Same N+1 pattern in `get_kds_intelligence`** (`pt.order_item.menu_item` chain) —
   completed but took 35s+ even after eliminating the N+1, since it was still unbounded by
   date. Fixed: `joinedload` + 30-day bound.
4. **Same N+1 in `get_upsell_pairs`, plus an O(n²) per-order pairing loop, plus no date
   bound** — made `/ai/menu-engineering` (which also calls this) time out past 30s. Fixed
   the same way.
5. **`routers/ai.py`'s `/ai/inventory` imported a function name that doesn't exist**
   (`get_inventory_intelligence` vs the real `get_inventory_predictions`) — a hard 500 that
   `_safe_run()`'s error handling couldn't catch (it wraps the function *call*, not the
   *import statement*). Nothing had ever exercised this route with a real authenticated
   request before to catch it.

**Verified twice** — once against an isolated Neon branch (to get full tracebacks safely),
once against live production after deploying the fix: all 9 `/ai/*` endpoints now return
200 (previously: 2 hard 500s, 2 timeouts past 30-90s). `/ai/dashboard` end-to-end:
4.95s on production (down from a complete, unbounded hang). The LLM orchestrator (Groq)
verified working end-to-end against the same real data via direct function calls — genuine
tool-calling round-trips producing correct natural-language answers about real sales/stock/
pricing state. Full local suite still 48/48 passing throughout.

## Production database wired (2026-07-07)
The real backend is now connected to its production Neon Postgres (project "restaurant
agent", branch "production", pg17) — the database already held **108,436 orders, 5
restaurants, 11 users** (real data spanning Apr 2024 → Jun 2026), plus inert leftover
tables from the abandoned tree (`bookings`, `user_vault`, `dpa_audit_logs`, etc.) that the
app's models never reference.

**How it was done safely** (the migration was proven before production was touched):
1. Read-only inspection first — confirmed schema of the overlapping tables matched
   `models.py` exactly at baseline; the only blocker was `alembic_version` stamped at the
   abandoned tree's revision (`002_add_agent_session_and_user_state_tables`), which isn't in
   our migration chain.
2. Created an isolated copy-on-write Neon **branch** from production, verified it was an
   exact copy (same 108,436 orders), cleared the foreign stamp, ran `alembic upgrade head`,
   and verified **zero data loss** + all 6 new schema elements present.
3. Only then applied the identical migration to production, with the same before/after
   integrity check: 108,436 orders / 5 restaurants / 11 users all preserved, schema at head
   (`006`), then deleted the throwaway branch.
4. Verified the **app itself** reads real production data through its ORM (new columns
   included) loading config purely from `backend/.env`. Full test suite still 44/44
   (tests use throwaway SQLite — production isolation confirmed).

`backend/.env` `DATABASE_URL` now points at the direct Neon endpoint (gitignored, not
committed). Migrations are additive/idempotent, so future redeploys (which run
`init_db()` + `alembic upgrade head`) are safe no-ops against this now-migrated database.

### Remaining for an actual public launch (needs the user / external accounts)
- **Set env vars in the Render dashboard** (since `backend/.env` is gitignored and not
  deployed): `DATABASE_URL`, `SECRET_KEY`, `GROQ_API_KEY`, `GROQ_MODEL`, and Twilio/M-Pesa
  vars when ready. The build command already runs migrations, so `DATABASE_URL` must be
  present at build time.
- **M-Pesa production credentials** — the client's real Safaricom/Daraja account
  (`MPESA_ENV=production` + live shortcode/passkey). Sandbox is fine until then.
- **Frontend**: point `NEXT_PUBLIC_API_URL` at the deployed backend, and set the backend's
  `CORS_ORIGINS` to the real frontend domain.
- **Owner phones**: the 5 existing restaurants have `owner_phone = NULL`; set via
  `PUT /api/v1/auth/restaurant` for WhatsApp owner features to route.

## Working method going forward (how we do things)
1. Before marking anything done: state what would prove it's done, then prove it —
   a real test against real code paths, not "it should work." This session's pattern
   (build → mock/simulate the boundary → run real scenarios → confirm before/after state)
   is the standard, not a one-off.
2. Before calling anything "Phase N progress": confirm it touches the actually-deployed
   code (`backend/`, tracked in git, run via `render.yaml`/`Procfile`) — not a parallel or
   abandoned tree. The M-Pesa mistake earlier in this roadmap (assuming `execution/`
   scripts were real progress when they targeted a different, unused schema) is the
   cautionary example; check `git log -- <path>` and cross-reference `models.py` before
   trusting a script's claims about itself.
3. Every module gets the AI-or-deterministic label check before being described to
   anyone (carried over from 012's standing rule).
4. One phase's exit criteria gate the next phase's start where there's a real
   dependency (e.g., don't build customer-facing LLM booking before the consent
   decision is made) — but independent gaps (e.g., writing tests) can proceed in
   parallel with anything.

---

## Phase 0 — Foundation
- [x] Twilio inbound signature validation — real, fail-closed, verified (bad/missing
      signature → 403, valid → 200).
- [x] Structured logging, circuit breakers exist in the abandoned tree only — **not
      ported to real `backend/`**. Open item below.
- [x] **Decision made (2026-07-07): accept plain `logging`/`print()` for v1, defer
      structured JSON logging + circuit breakers to a later phase.** Reasoning: the
      abandoned tree's versions are real, working code, but porting them now means
      taking on untested integration surface (they were built and verified against a
      different, incompatible schema — same class of mismatch as the M-Pesa scripts
      earlier in this roadmap) for a v1 launch that doesn't yet have the traffic volume
      where structured log aggregation or circuit-breaker trip thresholds would matter.
      Revisit once there's real production traffic and a concrete signal (e.g. an
      external-call failure that plain logging made hard to diagnose) rather than
      speculatively. This is an explicit decision, not an oversight — flagging it this way
      so it doesn't get silently re-opened as "still ambiguous" later.
- [x] **Minimal consent gate — built and verified (2026-07-07).** Deliberately the
      middle-ground option, not the abandoned tree's unbuilt DPA vault/ZKP/tokenization
      theater and not "skip it entirely": `models.CustomerConsent` (append-only,
      restaurant_id + customer_phone + purpose + timestamp — matches the existing
      `AgentAuditLog` pattern), migration `004_add_customer_consents.py` (idempotent,
      upgrade/downgrade both verified). Wired into the one place customer PII is
      actually collected today, `POST /orders/public`: an order with a phone number
      requires `consent: true` (400 if missing) and records a consent row; an anonymous
      order with no contact info needs no consent (nothing to consent to). 3 new tests
      in `tests/test_consent_gate.py`; 3 existing checkout tests updated to include
      consent so they keep passing. This also resolves 012's "blocked on
      product/legal decision" note for any *future* customer-facing flow (e.g.
      reservation booking) — the mechanism now exists; a future flow just needs to call
      it the same way.
      **Regression caught and fixed the same session**: the consent gate is a breaking
      API change to `POST /orders/public`, and `frontend/src/app/order/page.tsx` (the
      real customer-facing order page) already calls that endpoint with
      `customer_phone` set — it would have started failing with 400s in production had
      this not been checked. Fixed by adding a real consent checkbox to the checkout UI
      (not a hardcoded `true`, which would defeat the purpose) and sending
      `consent: consentGiven` in the request. Verified: `npm run build` compiles cleanly
      (TypeScript passes, all 19 routes generate); confirmed the staff-facing POS page
      (`dashboard/pos/page.tsx`) uses the separate authenticated `/orders/` endpoint and
      is correctly unaffected; confirmed no other public-facing frontend flow exists
      that would need the same fix.
- [x] **Secrets rotated (2026-07-07).** User rotated `GROQ_API_KEY` on the Groq side; a
      fresh `SECRET_KEY` was generated (`secrets.token_hex(32)`, never reusing the leaked
      value). Both written to a newly created `backend/.env` (the real deployed app had
      **no `.env` at all** until now — confirmed gitignored, confirmed not tracked by git
      before writing anything sensitive to it). New key verified with a real live Groq
      API call (see Phase 2 below) alongside a model swap to `openai/gpt-oss-120b` (the
      model the user's own working curl example used), confirmed to support tool-calling
      via the same orchestrator round-trip.

## Phase 1 — Deterministic Core
- [x] M-Pesa: STK push initiation, real callback handling, idempotency, event-bus
      handoff — verified end-to-end (5 scenarios: success, duplicate, failure, unknown
      correlation ID, malformed phone).
- [x] `payment_method` bug fixed in `create_public_order` (was silently ignoring
      customer's chosen method).
- [x] Reservation availability logic — real conflict/capacity checker, verified against
      6 scenarios. **Known gap**: no DB-level concurrency guard yet (needs the same class
      of fix as the pricing-recommendation partial unique index) — must close before
      concurrent booking traffic, not before v1 if traffic is low/staff-mediated initially.
- [x] Renamed "AI Intelligence"-labeled deterministic modules for accuracy
      (`routers/ai.py`, `routers/analytics.py` docstrings + OpenAPI tag, `ai/__init__.py`)
      — docstrings/comments/tags only, URL paths (`/ai/...`) deliberately left unchanged
      (real API contract, out of scope for a cosmetic rename). Verified: full test suite
      (33 tests) still passes after the change.
- [x] **Migration-on-deploy gap — fixed and verified (2026-07-07).** Root cause was
      deeper than "alembic isn't invoked": `models.py` defines the same tables migration
      001 creates (`pricing_recommendations`, `agent_messages`), so on a truly fresh
      database, running `alembic upgrade head` alone would fail (001's FK targets
      `restaurants`/`menu_items` don't exist yet — those only get created by
      `init_db()`/`create_all`, which historically only ran at app startup, after build).
      Fix: (1) `render.yaml` buildCommand and `backend/Procfile`'s new `release` step now
      run `python -c "from database import init_db; init_db()"` **before**
      `alembic upgrade head`; (2) all three migrations (001/002/003) were rewritten to be
      idempotent via SQLAlchemy inspector checks (table/column/index existence) instead
      of raw `IF NOT EXISTS` SQL — needed because `ADD COLUMN IF NOT EXISTS` is
      Postgres-only syntax and this project's local dev/tests run on SQLite; a raw
      `INTEGER PRIMARY KEY` also wouldn't autoincrement correctly on Postgres the way
      `op.create_table`'s `Integer`/`primary_key=True` does. Verified against 2 real
      scenarios: (a) brand-new empty database, full sequence run twice in a row
      (idempotency check) — no errors either time; (b) a realistic existing production
      database at the pre-migration schema shape, with a live `orders` row already in
      it, stamped at migration 001 (simulating "only 001 was ever manually applied, long
      ago") — the fixed sequence correctly added only the genuinely missing
      002/003 columns, and the existing row's data was fully preserved, not lost.
- [x] **Test suite + CI — built and verified (2026-07-07).** `backend/tests/` now
      covers: Twilio webhook (missing/bad/valid signature, keyword fast-path never
      touching the LLM), M-Pesa webhook (success, duplicate idempotency, failure,
      unknown correlation ID), order checkout (STK push triggered + checkout ID stored,
      malformed phone skipped safely, cash-order payment_method regression), M-Pesa
      client (phone normalization, not-configured degrade, Daraja payload shape), and
      reservation availability (all 6 conflict/capacity scenarios), and LLM provider
      selection/Groq response normalization (added after the Anthropic→Groq provider
      correction — see 012). 33 tests, all real (hit actual code paths, mock only the
      external HTTP boundary), 0 skipped.
      **Two hazards found and fixed while building this** (documented in
      `tests/conftest.py`'s docstring so they don't get silently reintroduced):
      (1) `database.py`, `ai/orchestrator/executive.py`, `ai/whatsapp/twilio_client.py`,
      and `payments/mpesa_client.py` all read env-derived config at *module import time*
      — since pytest runs all tests in one process, a later test's env var changes
      silently had no effect on an already-imported module until each was explicitly
      `importlib.reload()`-ed after the env var was set; (2) `events/bus.py`'s handler
      registry is a process-wide singleton — calling `register_all_handlers()` more than
      once per process would have silently accumulated duplicate subscriptions (duplicate
      WhatsApp sends/audit writes) with no error raised, fixed via `clear_handlers()` in
      the shared fixture. Both bugs would have produced tests that *looked* like they
      passed while silently testing stale state — caught only by noticing a specific
      assertion failure (403 where 200 was expected) and tracing it to its root cause
      rather than assuming the test itself was wrong.
      CI: `.github/workflows/backend-tests.yml` runs `pip install -r requirements.txt`
      then `pytest -v` on every push/PR. Caveat: the workflow itself hasn't been observed
      running on GitHub Actions (no push access in this session) — only the identical
      commands, run locally against the same `requirements.txt`, are verified.

## Phase 2 — The Orchestrator
- [x] Tool-calling router, prompt caching, per-tenant token metering, hybrid
      keyword-fast-path — built and verified (see 012 for full detail).
- [ ] Real live-API round-trip test (needs an actual Anthropic key, spends real tokens —
      your call on timing).
- [ ] Cheap/fast model for intent classification before escalating to Sonnet/Opus — not
      yet implemented.
- [ ] **Blocked on product/legal decision**: customer-facing reservation booking needs a
      consent/PII approach decided (see Phase 0's gap above — same underlying decision).

## Phase 3 — Memory & Localization
- [ ] Not started. Correctly sequenced after Phase 2 ships real traffic — don't build
      semantic memory or localization speculatively.

## Phase 4 — Operational Bridge / Enterprise Scale
- [x] **Multi-tenant isolation audit — done, and it found a real, serious vulnerability
      (2026-07-07).** Full pass across every router's queries (`.query(models.X).filter(...)`)
      found **8 endpoints across 3 files with zero tenant scoping** — a genuine
      cross-tenant IDOR (Insecure Direct Object Reference): any authenticated user from
      *any* restaurant/tenant could read, update, or delete another restaurant's data
      just by guessing/enumerating small sequential integer IDs:
      - `routers/orders.py`: `update_order_status`, `update_order_payment` — the payment
        one meant any tenant could mark *another restaurant's* order as paid, bypassing
        M-Pesa entirely.
      - `routers/reservations.py`: `update_reservation_status`, `delete_reservation`.
      - `routers/inventory.py`: `update_inventory_item`, `receive_stock`, `adjust_stock`,
        `delete_inventory_item`.
      `routers/menu.py` was already correctly protected (fetches by ID, then checks
      `db_item.restaurant.tenant_id != current_user.tenant_id`) — a useful reference for
      what "done right" looks like, which made the gap in the other three files obvious
      by contrast.
      **Fix**: added `restaurant_id == restaurant.id` directly into each query (filtering
      at the DB level, not a post-fetch check) using each file's existing
      `_get_restaurant(db, current_user)` helper.
      **Verified two ways**: (1) 4 new regression tests in
      `tests/test_tenant_isolation.py` — two real tenants/restaurants, real JWTs via
      `auth.create_access_token`, cross-tenant attempts on order status, order payment,
      reservation deletion, and inventory adjustment, all correctly rejected with 404 and
      confirmed to leave the target data untouched; (2) a mutation test — deliberately
      reintroduced the exact vulnerability in `orders.py`, confirmed the new test
      actually fails (proving it would have caught this bug), then restored the fix.
      37 tests total, all passing.

---

## Go-Live Gate (must all be true before first real restaurant goes live)
Treat this as the actual production checklist — not aspirational, checked one at a time:

- [x] Migrations run automatically as part of deploy — fixed and verified against both
      a fresh and an existing populated database (see Phase 1 above).
- [x] `backend/tests/` exists (40 tests as of 2026-07-07: webhook auth, M-Pesa webhook
      success/duplicate/failure, order checkout, reservation availability, M-Pesa
      client, LLM provider selection, tenant isolation, consent gate). CI workflow
      written (`.github/workflows/backend-tests.yml`) — not yet
      observed running on actual GitHub Actions infrastructure (see Phase 1 above).
- [ ] Consent/PII decision made and implemented for any flow that touches customer data
      beyond what's needed to fulfill an order (this gates Phase 2's reservation booking
      specifically, but also applies to anything customer-facing going forward).
- [ ] Secrets rotated (`GROQ_API_KEY`, `SECRET_KEY` from the quarantined file) and a real
      secrets-management process in place (Render env vars are fine — just confirm
      nothing is hardcoded anywhere else; this session found one instance already).
- [ ] Structured logging decision made (port from abandoned tree or accept plain logging
      for v1) — don't leave this ambiguous into production.
- [ ] `ANTHROPIC_API_KEY` / `headroom-ai` enabled deliberately, not accidentally — the
      requirements.txt gate ("uncomment when client has paid") should be a conscious
      business decision at go-live time, not something toggled by habit.
- [ ] M-Pesa credentials are production Daraja credentials, not sandbox — confirm
      `MPESA_ENV=production` and the shortcode/passkey match the live paybill, tested
      with a real small-value transaction before trusting it with customer money.
- [x] **Rollback plan — verified (2026-07-07).** Full round-trip tested: upgrade to head
      with live seeded data → downgrade 003→002→001→base, one step at a time → re-upgrade
      to head. Data survived throughout; final schema matched the original exactly.
      **Real bug found and fixed in the process**: `op.drop_column` on SQLite fails when
      the column has (or recently had) an index on it — a well-known SQLite limitation,
      not a Postgres issue, but this project's local dev/tests run on SQLite so it had to
      be fixed regardless. Fix: both 002's and 003's `downgrade()` now use Alembic's
      `batch_alter_table` (recreates the table safely on SQLite; transparently falls back
      to plain `ALTER TABLE` on Postgres/production — no behavior change there).

## Reservation booking guards + `utcnow()` deprecation pass (2026-07-08)

**IDOR class this project's tenant tests structurally miss.** `test_tenant_isolation.py`
proves you cannot update/delete another tenant's rows by guessing sequential ids. It does
not — and by construction cannot — catch a **foreign key accepted in a create body and
never ownership-validated**. `POST /reservations` took `table_id` straight from the request
and wrote it, so any authenticated user could book any restaurant's table by guessing an
integer. Same endpoint also never checked availability at all (`find_available_tables()`
existed, correct, since Phase 2, and no write path had ever called it) — so two ordinary
sequential requests double-booked a table, no concurrency required. Fixed; 9 tests added;
suite 85 passed. **Action item**: audit every other router for the same shape — an FK id in
a POST/PATCH body that is trusted without a `restaurant_id`/`tenant_id` scope check. Grep
starting points: `menu_item_id`, `table_id`, `supplier_id`, `inventory_item_id` in
`schemas.py` create models.

Ownership failures return **404, not 403**. A 403 confirms the row exists, turning the
endpoint into an enumeration oracle for other tenants' floor plans and menus.

**`datetime.utcnow()` (155 deprecation warnings) — why the obvious fix was the wrong one.**
The mechanical replacement, `datetime.now(timezone.utc)`, returns a timezone-*aware*
datetime. `utcnow()` returns a *naive* one. Every `DateTime` column in `models.py` is naive
(none declare `timezone=True`), so every value read back from the DB is naive, and Python
raises `TypeError: can't subtract offset-naive and offset-aware datetimes` where the two
meet. This codebase does exactly that in a dozen places (`analysis_clock.py`'s
`utcnow() - latest`, and every `cutoff = utcnow() - timedelta(...)` across pricing,
marketing, evaluation, executive). A find/replace would have shipped a **runtime crash in
production while the test suite stayed green**, since tests mostly build their own naive
fixtures. Instead: new `backend/time_utils.py` with `utcnow()` preserving naive-UTC
semantics byte-for-byte, all 64 call sites migrated, orphaned `datetime` imports removed.
Warnings 155 → 9 (all third-party: passlib/argon2, FastAPI `on_event`).

- [ ] **Migrate to timezone-aware datetimes properly.** `DateTime(timezone=True)` columns,
      one Alembic migration per table, and an audit of every naive comparison.
      `time_utils.utcnow()` is the single place that flips; `aware_utcnow()` is what it
      flips to. A real change — deliberately not smuggled into a deprecation cleanup.
- [ ] **Run migration 009 against a real Postgres before deploy.** Never executed against
      one: no local Postgres here, and the only reachable instance is production Neon.
      Confirm the role may `CREATE EXTENSION btree_gist`, and query for pre-existing
      overlapping CONFIRMED reservations first — nothing ever prevented them, so
      `ADD CONSTRAINT` may fail on live data. Reconciliation query is in the migration's
      docstring.
