# Directive: POS & KDS Implementation

**Goal**: Point of Sale (POS) for waiters, Kitchen Display System (KDS) for chefs.

> **Revised 2026-08-06** — routes corrected to what shipped, prep-time capture
> added, and offline POS actually built (see "Offline POS" below; superseded
> the original "Corrections" section, which is preserved further down for
> the reasoning trail — read it, it explains a real auth bug the offline work
> uncovered and fixed).

## Inputs
-   Frontend, Backend

## Architecture

### POS (Frontend)
-   Route: **`/dashboard/pos`** (tenant protected). *The spec said `/pos`.*
-   Components: `CategoryTabs`, `MenuGrid`, `OrderCart`.
-   Cart state is in-memory only, synced on checkout.
-   **Offline-capable** since 2026-08-06 — see "Offline POS" below.

### KDS (Frontend)
-   Route: **`/dashboard/kitchen`** (tenant protected). *The spec said `/kds`.*
-   Fetches `GET /orders/active` (PENDING, PREP, READY).
-   Polling. No websockets — the polling interval is well within what a kitchen
    needs and it avoids a persistent-connection dependency on a single worker.
-   Bump advances status via `PATCH /orders/{id}/status`.

### Backend
-   `POST /orders/` — create. **Prices are recalculated server-side from the
    menu.** The client sends `menu_item_id` and `quantity` only; a tampered
    client cannot set its own total. Keep it that way.
-   `POST /orders/public` — customer self-service ordering, unauthenticated,
    rate-limited 20/min, consent-gated when a phone number is supplied.
-   `GET /orders/` / `GET /orders/active` — history / kitchen queue.
-   `PATCH /orders/{id}/status` — advance status.
-   `PATCH /orders/{id}/payment` — mark paid; emits `ORDER_PAID` exactly once on
    the unpaid→paid transition, so a re-marked order never re-sends a receipt.

## Prep-time capture (added 2026-08-06)

`PATCH /orders/{id}/status` now writes `PrepTime` rows. This is the capture path
for `ai/kds_intelligence.py` — per-station p95/median/std-dev, bottleneck
severity, queue depth, delay-risk scoring, roughly twelve analytics in total.

**Why it was added:** nothing in the running application had ever written a
`PrepTime` row. The only writer in the entire codebase was
`populate_production.py`, the demo seeder. So on every real restaurant the
kitchen module read an empty table and returned `_empty_response()` — silently,
forever. See the capture-layer principle in directive 001.

Rules the implementation follows (`_record_prep_timing` in `routers/orders.py`):

-   **One timer per `OrderItem`**, opened on entry to PREP, closed on READY or
    SERVED with `actual_minutes`.
-   **`station` comes from `MenuItem.prep_station`.** Left at its "main" default,
    the per-station breakdown would be one bucket and bottleneck detection —
    which compares stations against each other — could never fire.
-   **Both halves are idempotent.** A double-tapped bump must not create a second
    row or re-stamp a measurement. Specifically, READY *then* SERVED must keep
    the measurement taken at READY; otherwise every prep time silently becomes
    "time until the plate was carried out", inflated by the whole service window.
-   **A backwards bump does not reopen a closed timer.** The first completion is
    kept rather than being extended by however long the ticket sat before someone
    corrected the status.
-   **PENDING → READY (skipping PREP) still measures**, starting from the order's
    `created_at`. Plenty of kitchens never press PREP; without this fallback a
    busy restaurant would see an empty kitchen dashboard while running hundreds
    of orders a day.
-   **A cancelled ticket leaves its timer open.** `kds_intelligence` only reads
    rows with `actual_minutes` set, so an abandoned ticket never counts as a fast
    prep, and no cleanup job is needed.

## Offline POS (built 2026-08-06)

Three pieces, and they only work as a set — shipping any one alone leaves a gap
that defeats the other two.

### 1. The write queue — `frontend/src/lib/offlineQueue.ts`

IndexedDB (`leviii-offline` DB), two object stores:
-   `pending-orders` — orders placed while offline, each keyed by a
    client-generated UUID (`crypto.randomUUID()`), FIFO by `createdAt`.
-   `menu-cache` — the last successfully fetched menu. **This is not optional
    polish.** Without it, a device that reloads (or is opened fresh) with no
    connection has an empty menu and nothing to sell, no matter how good the
    order queue is. Cached on every successful `GET /menu/`; used as the
    fallback the instant that fetch fails.

### 2. Idempotent replay — `client_order_id`

The queue can't always tell whether a sync actually reached the server: the
request may have succeeded and only the *response* was lost to a flaky
connection, which is indistinguishable client-side from the request never
arriving. `OrderCreate.client_order_id` (migration 026,
`uq_orders_restaurant_client_order_id`) makes retrying that safe:
`routers/orders.py` looks up an existing order by `(restaurant_id,
client_order_id)` before doing anything else, and returns it unchanged on a
repeat — no duplicate ticket, no second stock deduction (`stock_ledger` is
never reached a second time), no second `PrepTime` row. NULL for every normal
online order; multiple NULLs are fine under the constraint on both SQLite and
Postgres.

`frontend/src/lib/offlineSync.ts` flushes the queue **sequentially**, oldest
first, on the `online` event, a 30s poll (the `online` event alone is not
reliable across browsers/mobile networks), and once at layout mount. A
**network failure** (`!err.response` — axios's signal that no response came
back at all) stops the flush and waits for the next trigger. A **real
rejection** (`err.response` present — e.g. a menu item deleted while offline)
is left in the queue with the error recorded, not silently dropped — retrying
forever won't fix a bad reference, and discarding a placed order is a worse
failure than one staying visibly stuck for a human to look at.

### 3. The auth bug this uncovered — read before touching `AuthContext.tsx`

Building this surfaced a **pre-existing** bug that would have defeated the
whole feature: `AuthContext.fetchUser()` treated *any* failure of the
boot-time `/auth/me` check — including a plain network failure — as an
invalid session, clearing the token and bouncing to `/login`. Every reload
while offline hit exactly this path, on a device that by definition can't
reach `/login`'s own API either. The queue and the cached menu were never the
weak link; a page reload was logging the user out before either could matter.

Fixed by distinguishing the two cases: a real `401`/`403` (`err.response`
present — the server actually rejected the token) still clears the session,
but a network failure now falls back to a `cached_user` snapshot in
`localStorage` (written on every successful `/auth/me`) instead. This does not
weaken auth — a genuinely revoked token is still rejected the moment any
request actually reaches the server, via `api.ts`'s existing 401 interceptor —
it only stops *connectivity loss* from being treated as *session revoked*.

**If you touch `AuthContext.tsx` again:** any change that clears the token or
user on a bare `catch` will silently reintroduce this. The fix is the
`err?.response` check, not the presence of an error.

### Verified end-to-end (not just typechecked)

Driven in a real browser against a real backend, **against a production build**
— `next dev`'s own asset serving doesn't survive a real offline reload and gave
a false failure the first time this was tested; only `next build && next start`
represents what ships. Sequence: place one order online → confirm the service
worker has actually activated (`navigator.serviceWorker.ready`) → go offline
(`context.setOffline(true)`) → place two more orders, confirm both show "Saved
on this device" and the pending count → **reload the page while still
offline** → confirm the POS renders fully (session intact, real cached menu,
"2 waiting" banner) instead of a login screen or a blank tab → come back online
→ confirm the queue auto-flushes with no interaction → confirm via the backend
API that all three orders exist exactly once, correct items and totals, no
duplicates.

### Known remaining edges

-   **The queue is per-device, not shared across POS terminals.** Two tablets
    both offline can't see each other's queued orders. Not fixable without a
    sync layer between devices, which is a materially bigger feature.
-   **A queued order used stale prices/availability if the cached menu is old**
    — the sync sends whatever price was on the client at cart time, same as
    any online order (the server always recomputes from current prices, so
    this only affects what the waiter *saw*, never what gets charged).
-   **A real rejection during sync currently has no dedicated UI to inspect
    and resolve it** beyond `OfflineSyncIndicator`'s failed-count banner — no
    per-order detail view or manual discard/edit yet.

## Corrections (historical — the offline claim above superseded this)

**Offline ordering was never implemented, and this directive implied it was**
— true as of the audit on 2026-08-06, fixed later the same day (see "Offline
POS" above). Kept for the reasoning trail: the original "State: Local storage
for cart (offline support)" and "Offline Orders: Queue requests if internet
fails" described intent that didn't exist in the code.
`frontend/public/sw.js` cached the app shell and **explicitly skipped `/api`
requests**; the POS page had no IndexedDB, no write queue, no
`navigator.onLine` handling. A dropped connection meant no orders could be
taken, and the honest fallback at the time was paper, entered afterwards
(what `docs/faq.md` told customers).

**Station-filtered KDS view is still not built.** Prep timing is now captured
per station, but the kitchen page shows one undifferentiated queue. The data now
exists to build the filtered view; it's a UI change.

**Race conditions on bump are handled by being idempotent, not by locking.** Two
chefs bumping the same order converge on the same state and produce one
measurement. That's sufficient here — the operation is a status set, not a
read-modify-write.

## Verification

`backend/tests/test_prep_timing.py` (9 tests) covers open/close, station
propagation, one-timer-per-item, both idempotence paths, the backwards bump, the
PREP-skip fallback, the cancelled-ticket case, and an end-to-end assertion that
`get_kds_intelligence` reports real per-station numbers.

`backend/tests/test_order_idempotency.py` (7 tests) covers `client_order_id`
replay returning the same order, no double stock deduction, no duplicate
`PrepTime` row, distinct ids creating distinct orders, ordinary online orders
(no id at all) being unaffected, per-restaurant scoping, and the public
customer-order endpoint's own replay path. Offline POS's browser-driven
end-to-end verification is described in "Offline POS" above — that scenario
doesn't fit a pytest run (it needs a real service worker, a real IndexedDB, and
`context.setOffline()`), so it isn't in the automated suite; re-run it by hand
per that section if this area changes again.
