# Changelog

Notable changes to the Leviii AI platform and its documentation. Newest first. Derived from
git history on `feat/phase1-production-hardening`.

## 2026-08-06 — Second review pass: PIN attribution and retry-policy consistency

A re-review of the branch after the fixes below found five further defects, one
of which was only reachable *because* the path-prefix fix made the PIN feature
run at all.

### Fixed
- **PIN attribution was silently dropping on every order** (D16). `pin_verify`
  returns `{user_id, ...}` while `/pin/roster` returns `{id, ...}`, and
  `PinSwitcher` passed the response body straight to `onSwitch` — so
  `PinOperator.id` was `undefined` and every order posted
  `attributed_user_id: null`. The header still read "Serving as: Amina" because
  `display_name` is common to both shapes, so the feature looked like it worked.
  Now normalized on read. This was invisible until the path prefix was fixed:
  before that the request 404'd and never returned a body at all.
- **A transient 5xx on first submit discarded the order** instead of queueing
  it, contradicting the replay path's policy fixed in the entry below. Worse,
  the error toast pushed the waiter to resubmit by hand, which minted a *fresh*
  idempotency key — reintroducing the duplicate-charge bug on exactly the
  "committed but response lost" case the key exists for. The retry policy now
  lives in one exported predicate (`isTerminalClientError`) that both the
  first-attempt and replay paths call, so they cannot drift apart again.
- **Dropped queue entries were silent.** `flushQueue` discards a 4xx entry
  permanently, but only exposed an `onFlushed` (success) callback, so the POS
  never learned and the queue badge went stale. Added `onDropped`; the POS now
  shows a persistent "please re-enter it" error, since a discarded order exists
  nowhere but in the waiter's memory.
- **`Retry-After` HTTP-date parsed as `NaN`** in the axios 429 interceptor.
  RFC 7231 §7.1.3 permits both delta-seconds and an HTTP-date; `Number(<date>)`
  is `NaN`, and `setTimeout(fn, NaN)` runs immediately — retrying instantly
  against a server that just asked us to wait. Not reachable through slowapi
  today, but a landmine the moment a CDN or gateway sits in front.
- **PIN modal had no Escape-to-close**, despite declaring `role="dialog"`. The
  sibling `ConfirmSend` modal added the handler under D20; this one now matches.

- **The PIN-verified operator did not survive a page reload**, so a
  service-worker update or mobile Safari evicting a backgrounded tab silently
  reverted attribution to null mid-shift — with no signal, since the backend
  accepts null attribution by design. Now persisted in `sessionStorage`
  (`frontend/src/lib/posOperator.ts`): survives a reload, does not outlive the
  tab, so a tablet left on the counter overnight isn't still ringing up orders
  as whoever closed. Cleared on logout so the next login can't inherit the
  previous session's operator. Rehydrated in an effect rather than a lazy
  `useState` initializer, which would read browser storage during render and
  produce a hydration mismatch.

## 2026-08-05 — Review follow-up: POS offline queue and PIN switching hardened

Seven defects found by a multi-agent review of `feat/pos-offline-pin-hardening`,
all in code this branch introduced. Each is covered by a regression test that
was verified to fail against the pre-fix code.

### Fixed
- **PIN quick-switch was entirely non-functional** (D16). `PinSwitcher` called
  `/auth/pin/roster` and `/auth/pin/verify`, but `api.ts`'s baseURL is the bare
  host and the auth router mounts only at `/api/v1/auth` (included outside the
  dual-mount loop in `main.py`). Both 404'd; the `.catch` swallowed it into
  "No staff have set up a PIN yet," so the feature looked merely unconfigured.
  Backend tests were green throughout — they used the correct path. Now
  prefixed, and a failed roster fetch reports a load error instead of
  masquerading as an empty roster. Covered by `PinSwitcher.test.tsx`.
- **The first order POST carried no idempotency key** (D15), which defeated the
  guarantee the key exists for. When the server committed an order but the
  response was lost in transit — cellular handoff, TLS reset, LB timeout, the
  exact failure the offline queue was built for — the replay was stamped with a
  *fresh* UUID, so the backend saw a new order and the customer was charged
  twice. The key is now minted before the first attempt and preserved on
  enqueue.
- **The offline queue silently dropped orders two ways** (D15). It treated any
  HTTP response as non-retryable, so a 502 from a backend restart permanently
  deleted a queued order; 5xx and 429 are now retained and retried, and only
  true 4xx are dropped. And it wrote back a pre-`await` snapshot of the queue,
  so an order enqueued mid-flush (a waiter submitting during a replay, or a
  second POS tab sharing localStorage) was clobbered; entries are now removed
  by id against freshly-read storage.
- **Concurrent idempotent replays returned 500 instead of the existing order**
  (D15). `create_order`'s key lookup is a check-then-act; two simultaneous
  replays both missed it and the loser hit
  `uq_orders_restaurant_idempotency_key` uncaught. Compounding the offline
  queue's drop-on-5xx above, that 500 then destroyed the order. Now caught,
  rolled back, and resolved to the winning row.
- **PIN lockout was effectively permanent.** After the 15-minute window expired
  the failed-attempt counter was never reset, so a single wrong digit re-tripped
  the lockout — a staff member who fumbled their PIN once per window was locked
  out for the rest of the shift unless they entered it correctly first try. The
  counter now resets when the window lapses.

### Security
- **Deactivation now revokes every credential, not just login** (D18).
  `/auth/pin/verify` and `create_order`'s attribution lookup filtered on
  id + tenant only, while `/pin/roster` one function above correctly filtered
  `is_active` — so a departed employee's PIN still verified and they could still
  be stamped as the operator on new orders. Both queries now enforce
  `is_active`, and `deactivate_user` clears `pin_hash`/`pin_failed_attempts`/
  `pin_locked_until` so re-activation is a deliberate opt-in. This is the same
  accountability trail migration 029 was written to protect.
- **`/pin/set` and `/pin/verify` are now actually rate-limited.** `pin_set`'s
  docstring claimed "rate-limited like any other credential-setting action" but
  carried no limiter — and since it resets the failed-attempt counter, it was a
  way to clear the `/pin/verify` lockout at will. Added `10/hour` on set and
  `30/minute` on verify (generous: a shared tablet legitimately verifies many
  times per shift). `pin_set` also overwrote an existing display name on every
  call despite promising "if not already set"; now guarded.

## 2026-08-03 — Audit follow-up: CI gate unblocked, stock attribution

### Security
- **Stock movements now record who performed them** (`StockMovement.user_id`,
  migration 029). `POST /inventory/{id}/receive` and `/adjust` are open to any
  authenticated user — correct, since logging a delivery or writing off waste is
  normal floor work — but the movement record captured only item/type/quantity/
  reason. A negative adjustment with a free-text reason was therefore completely
  anonymous: the textbook shrinkage vector, sitting directly beneath the
  profit-leak and portion-drift detection this product sells. Fixed by
  attribution rather than restriction, so kitchen workflow is unchanged.
  Covered by `backend/tests/test_stock_attribution.py`.

### Fixed
- **Blocking `npm audit` CI gate is green again** (closes tech-debt D27). The 3
  high-severity advisories were in `postcss`/`sharp` **bundled inside** Next.js,
  not in direct dependencies — npm's suggested remedy was a downgrade to
  `next@9.3.3`. Resolved properly instead: Next patch bump 16.2.10 → 16.2.12 plus
  `overrides` pinning `postcss ^8.5.25` / `sharp ^0.35.0` inside Next's tree.
  Verified with a full build, typecheck, and test run — the advisories are
  actually resolved, not suppressed by loosening the threshold.

### Changed
- **Tech-debt D1 re-scoped P1 → P2** after a route-by-route RBAC audit. Its
  original remedy ("STAFF = POS/KDS only") would have broken the POS: orders,
  reservations, and inventory receive/adjust are legitimate floor work. The
  admin surfaces (`ai`, `analytics`, `billing`, `enterprise`, `export`, and
  menu/inventory CUD) are already gated. The residual gap is that floor routes
  rely on implicit "any authenticated user" rather than an explicit
  `require_role` declaration — a readability and fail-closed concern, not an
  open privilege hole.

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
