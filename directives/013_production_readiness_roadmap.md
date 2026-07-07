# Production Readiness Roadmap

## Purpose
`012_agentic_roadmap.md` tracks the AI/orchestration engineering work. This directive is
the wider gate: everything across all phases that must be true before real restaurants
run on this system, with an explicit verification method for each item — not just "built"
but "checked." Update this file's checkboxes as work lands; don't let it drift into
aspirational copy the way the original sprint plan did.

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
- **Duplicate `/ai` router routes.** `analytics.py` and `ai.py` both mount `/ai/dashboard`,
  `/ai/menu-engineering`, `/ai/revenue-forecast`, `/ai/reservation-insights`; `analytics.py`
  wins (registered first in `main.py`), so `ai.py`'s versions of those 4 are dead code with
  *different* implementations. Consolidating to one router per endpoint needs per-endpoint
  frontend-shape verification (the menu/orders/reservations pages depend on the currently
  served shapes), so it's its own careful task — flagged, not ripped out mid-hardening.

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
