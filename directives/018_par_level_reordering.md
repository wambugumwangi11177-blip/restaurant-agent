# Directive: Par-Level Reordering

**Goal**: Nobody checks a shelf to decide what to order. Stock crosses its
reorder point, a draft purchase order is prepared automatically (adjusted
for known demand signals like holidays), a human approves it, and only then
does a message go to the supplier — closing Phase 2 of the automation
roadmap sketched with the owner (Phase 1 was directive 017's recipe/kitchen
work).

**Status**: Implemented (2026-07-16), same branch
(`feat/staff-rbac-stock-custody-twilio`). 15 new tests pass
(`tests/test_par_level_reordering.py`), full suite green, frontend
`tsc --noEmit` clean.

## What was already there, reused rather than rebuilt

- `Supplier` and `PurchaseOrder` models already existed, fully fleshed out
  (`quantity_ordered`, `quantity_received`, `cost_per_unit`, `total_cost`,
  `status` as a free string documented `PENDING → SENT → DELIVERED (or LATE
  / PARTIAL)`) — but verified by grep before assuming: **zero routers
  referenced either model**. No way for an owner to create a supplier, place
  an order, or record a delivery existed anywhere in the app. `PENDING`
  already meaning "created, not yet sent" is exactly the draft state this
  directive needed — no new status value required.
- `ai/simulation/signals.py: demand_signals(date) -> dict` (built for the
  Digital Twin) already computes a multiplicative demand factor from Kenyan
  public holidays and school-term breaks (weather/sports are wired but
  no-op until their API keys are set). Reused as-is for par-level adjustment
  — this directive adds no new demand-signal logic, it consumes the
  existing one.
- `InventoryItem.low_stock_threshold` (existing column, already the trigger
  for the 2-hourly stock-alert job) doubles as the Reorder Point — not
  duplicated. `par_level` (new) is the only genuinely new number: the target
  to restock up to.
- `PurchaseOrder.cost_per_unit`/`total_cost` are documented in **cents**;
  `InventoryItem.cost_per_unit` is stored in **whole KES** (confirmed by
  reading `routers/inventory.py`'s receive endpoint and the frontend's
  direct, undivided `KES {cost_per_unit}` display). A real, pre-existing
  unit mismatch in this codebase — `ai/reorder.py::draft_purchase_order`
  converts explicitly, once, with a comment, rather than let it become a
  silently-wrong `total_cost`.

## A bug found and fixed while extending this same alerting pattern

`on_purchase_order_late` (existing handler, `ai/orchestrator/executive.py`)
read `OWNER_PHONE_{id}`/`OWNER_PHONE` env vars only — never
`Restaurant.owner_phone`, the DB column every other handler in this file
already prefers. This is the exact bug class `on_stock_critical`'s own
comment describes fixing elsewhere in the same file ("Was env-var only, so a
restaurant onboarded via the owner_phone column got no critical-stock alerts
at all"). A restaurant using the normal onboarding path (the DB column) got
**zero supplier-late alerts**, silently. Fixed to use the shared
`_owner_phone()` helper, consistent with every handler this directive adds
alongside it.

## Architecture

1. **`InventoryItem.par_level`, `InventoryItem.default_supplier_id`**
   (migration 027) — both nullable. An item missing either is simply never
   auto-drafted, matching this whole workstream's "don't guess" posture
   (same reasoning as directive 015's unassigned-`staff_role` handling).
2. **`ai/reorder.py`** — pure functions over a `Session`, same posture as
   `ai/stock_custody.py`:
   - `find_reorder_candidates`: items at/below their reorder point, with
     both new fields set, no purchase order already open
     (`PENDING`/`SENT`) for that item — skips duplicate drafts.
     `order_quantity = (par_level - on_hand) × demand_factor`.
   - `draft_purchase_order`: writes the `PENDING` row, emits
     `PURCHASE_ORDER_CREATED`.
   - `approve_and_send`: `PENDING → SENT`, texts the supplier
     (`fallback_sms=True` — a supplier isn't guaranteed to be on WhatsApp),
     writes the audit log entry. **This is the approval gate** — nothing
     reaches a supplier without a human calling this.
   - `receive_purchase_order`: `SENT → DELIVERED` or `PARTIAL`, writes the
     received quantity as a `StockMovement` IN (closing the loop back into
     inventory), emits `PURCHASE_ORDER_DELIVERED` **only on a real
     shortfall** — matches the "alert on the exception" philosophy from
     directives 016/017, not a ping on every successful delivery.
3. **`routers/suppliers.py`** (new) — CRUD, Owner/Manager
   (`require_staff_role(MANAGER)`).
4. **`routers/purchase_orders.py`** (new) — list (Manager/Controller/
   Stockkeeper), approve (Manager/Supervisor), receive (Manager/
   Stockkeeper). Thin — all the real logic lives in `ai/reorder.py`, same
   split as `routers/stock_custody.py` / `ai/stock_custody.py`.
5. **`routers/inventory.py`**: new `PUT /{item_id}/reorder-settings` sets
   `par_level`/`default_supplier_id`; rejects an unknown
   `default_supplier_id` rather than silently accepting a dangling
   reference.
6. **Scheduled job** (`main.py: _run_reorder_check_job`, 06:00 EAT daily) —
   a draft should be waiting before/during opening, not discovered
   mid-shift. Deliberately not on the 2-hourly stock-check cadence; one pass
   a day matches "prepare a draft," not "watch continuously."
7. **`executive.py`**: two new handlers,
   `on_purchase_order_created` (draft-ready notification) and
   `on_purchase_order_delivered` (shortfall-only notification), registered
   alongside the (now-fixed) `on_purchase_order_late`.
8. **Frontend**: new `/dashboard/purchasing` page rather than growing the
   already-733-line inventory page further — approve/receive queue, a
   reorder-settings panel per item, supplier management, and order history.
   Nav entry gated to Manager/Controller/Supervisor/Stockkeeper (directive
   015's `access` array pattern), matching the backend's per-action split.

## Verify before calling it done

- An item below its reorder point with both new fields set produces exactly
  one candidate; missing either field produces none.
- A second draft is never created while one is already `PENDING`/`SENT` for
  the same item.
- A known Kenyan public holiday date produces a higher adjusted quantity
  than a neutral date, using the real (not mocked) `demand_signals`.
- `cost_per_unit` on the drafted PO is in cents, converted from
  `InventoryItem.cost_per_unit`'s whole-KES storage.
- Approve only succeeds from `PENDING`; receive only succeeds from `SENT` —
  both reject a second call.
- A full-quantity receive marks `DELIVERED` and credits `InventoryItem.quantity`
  by exactly what was received; a short receive marks `PARTIAL` and emits
  `PURCHASE_ORDER_DELIVERED` with the correct shortfall, once.

## Explicitly out of scope for this directive (real follow-ups)

- **Supplier-side digital confirmation** — deliberately not built. The
  planning conversation this directive comes from explicitly pushed back on
  assuming a small Kenyan supplier has any app to confirm through; the
  approve step sends a one-way informational text, matching how every other
  supplier-facing touch in this codebase already works.
- **Fully autonomous approval** (no human in the loop at all) — every path
  here requires an explicit approve call. An "auto-approve under KES X"
  trust setting was discussed as a real possibility but deliberately not
  built without being asked for explicitly — it's real money being
  committed.
- **QR/barcode-based receiving** — discussed in the same planning
  conversation as a way to make the receive step itself lower-friction;
  `receive_purchase_order` takes a typed quantity today, not a scan.
- **Waste/expiry detection, supplier price comparison** — still the
  Phase 3 items named when this roadmap was first sketched; untouched here.

## When you're done

If the reorder cadence, approval roles, or the demand-adjustment formula
change from what's specified here during further use, update this file in
the same change.
