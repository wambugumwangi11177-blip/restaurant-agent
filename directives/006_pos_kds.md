# Directive: POS & KDS Implementation

**Goal**: Point of Sale (POS) for waiters, Kitchen Display System (KDS) for chefs.

> **Revised 2026-08-06** — routes corrected to what shipped, prep-time capture
> added, and the offline claim corrected. See "Corrections" at the end.

## Inputs
-   Frontend, Backend

## Architecture

### POS (Frontend)
-   Route: **`/dashboard/pos`** (tenant protected). *The spec said `/pos`.*
-   Components: `CategoryTabs`, `MenuGrid`, `OrderCart`.
-   Cart state is in-memory only, synced on checkout. See "Corrections" on offline.

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

## Corrections

**Offline ordering was never implemented, and this directive implied it was.**
The original "State: Local storage for cart (offline support)" and the
"Offline Orders: Queue requests if internet fails" edge case describe intent that
does not exist in the code. `frontend/public/sw.js` caches the app shell and
**explicitly skips `/api` requests**; the POS page has no IndexedDB, no
localStorage write queue and no `navigator.onLine` handling. A dropped
connection means no orders can be taken.

A real fix needs three things together: an IndexedDB write queue, an idempotency
key on order creation so replay can't double-charge or double-deduct stock, and a
sync indicator in the UI. Deferred as its own piece of work. **Until it exists,
do not describe the POS as offline-capable** — the honest fallback is paper,
entered afterwards, which is what `docs/faq.md` already tells customers.

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
