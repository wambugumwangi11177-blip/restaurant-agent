# Directive: Stock Chain-of-Custody, Risk Management & Staff Twilio Comms

**Goal**: Make every stock movement (supplier → store → kitchen → production/
waste) attributable to a person, detect theft/shrinkage and account-level risk
automatically, and let staff receive and confirm actions over Twilio
(WhatsApp/SMS) the same way the owner already does — without inventing a
second, unauthenticated messaging path.

**Status**: Implemented (2026-07-15), branch `feat/staff-rbac-stock-custody-twilio`.
11 new backend tests pass (`tests/test_stock_custody_and_staff_roles.py`), full
362+11-test suite green, frontend `tsc --noEmit` clean. See "As-built notes"
at the end of this file for what shipped vs. what's still open.

Update this file as decisions get made, per CLAUDE.md's
self-annealing rule.

**Depends on**: [[staff-roles-permissions]] skill / `directives/015_*.md` for
the 7-tier role model — separation of duties (who can *see* a variance report
vs who can *cause* one) is a risk control, not just a UX nicety, and this
directive assumes 015's RBAC is landing in the same change.

## What's already there (verified in this codebase, 2026-07-15) — reuse, don't rebuild

- `StockMovement` (`models.py`) has `movement_type`, `quantity`, freeform
  `reason`, `created_at` — **no field records who performed the movement.**
  This is the root gap. Every mitigation below builds on fixing this first.
- `Supplier` + `PurchaseOrder` already model supplier→store, including
  `quantity_ordered` vs `quantity_received` and a `status` state machine
  (`PENDING→SENT→DELIVERED/LATE/PARTIAL`). Supplier-side short-delivery is
  already representable. Don't rebuild it.
- `MenuIngredient` links `MenuItem`→`InventoryItem` with
  `quantity_per_serving` — this is what makes "theoretical usage" computable
  (servings sold × recipe quantity), the other half of a variance check.
- `InventoryItem.last_alerted_at` + `STOCK_ALERT_COOLDOWN_HOURS` (12h) in
  `ai/whatsapp/brain.py` is the existing per-subject cooldown pattern. A real
  double-send bug was fixed here 2026-07-08 (an emitter AND a handler both
  sent WhatsApp for the same event) — read `run_stock_check`'s docstring
  before wiring any new alert type through the event bus, so it isn't
  reintroduced.
- `events/bus.py` (`EventType` registry, `subscribe`/`emit`/`emit_async`) and
  `ai/orchestrator/executive.py` (`register_all_handlers`, one handler per
  event type, calls `ai.whatsapp.send_whatsapp_message`) is the existing,
  working pattern for "something happened → decide → notify." New risk events
  plug into this, they don't get a parallel notification path.
- `ai/whatsapp/twilio_client.py` validates every inbound webhook against
  Twilio's request signature (`validate_twilio_request`,
  `routers/webhooks.py: whatsapp_webhook`). This is the **only** authenticated
  inbound channel that exists. Any new staff-facing inbound command (transfer
  confirmation, etc.) must be resolved inside this same signature-checked
  endpoint — do not add a second webhook route that skips validation.
- `routers/webhooks.py: _resolve_restaurant_by_phone` /
  `_resolve_restaurant_for_customer` show the existing pattern for "whose
  message is this" resolution (by `Restaurant.owner_phone`, then by recent
  `Order.customer_phone`). **Neither resolves a staff member** — there is no
  phone column on `StaffMember` today and no third resolution branch. This is
  the gap to close for two-way staff messaging.
- `AgentAuditLog` (`models.py`) is the existing immutable audit trail
  (`action_type`, `agent_name`, `entity_type/id`, `before/after_state`,
  `reasoning`, `approved_by`). Reuse for every custody/role-change event —
  don't build a second audit table.
- MFA (TOTP) and `token_version`-based logout-all already exist in `auth.py`.
  Account-compromise risk has a real mitigation already; the gap is
  **account lifecycle**, not authentication strength — see below.

## Risks considered, and what each mitigation actually is

| Risk | Mitigation | New or reused |
|---|---|---|
| Theft/shrinkage in the supplier→store leg | `PurchaseOrder.quantity_received < quantity_ordered` beyond tolerance | Reused (already modeled) |
| Theft/shrinkage in store→kitchen leg | New `StockTransfer` model: sender declares quantity, **receiver independently confirms actual quantity** — a mismatch is the signal, not a self-reported number | New |
| "Who moved this?" — no accountability today | `StockMovement.performed_by_user_id` (nullable, backfill-safe) | New |
| Recipe-implied usage vs recorded usage drifting apart (the classic "sold 50, only 40 worth of ingredients went out" theft pattern) | Variance report: theoretical (via `MenuIngredient` × sales) vs actual (`StockMovement` OUT), industry-standard 2–3% tolerance before flagging (external research, cited in the `stock-loss-prevention` skill) | New |
| Same person causing AND catching a discrepancy | Controller role is read-only on inventory (015's matrix) — enforced in the router, not just UI | Reused (015) |
| Alert fatigue → real alerts get ignored | Daily/shift-level variance summary, not per-movement; transfer-discrepancy alerts fire once per transfer (inherently non-repeating, no cooldown needed) | New job + reused cooldown philosophy |
| Ex-staff retaining dashboard/API access after being taken off the roster | **New gap found while implementing this**: `StaffMember.is_active` existed but nothing downstream acted on it — the linked `User` kept working. Added `User.is_active` (default True); deactivating a `StaffMember` with a linked user now also flips `User.is_active=False` and bumps `token_version` (immediate session revocation, reusing the existing logout-all mechanism) | New |
| Spoofed/forged Twilio messages | Signature validation already exists — reused as-is, no new unvalidated endpoint | Reused |
| Role escalation via self-assignment | Role assignment endpoint requires Owner/Manager (`require_staff_role`), and every change writes to `AgentAuditLog` | New endpoint, reused audit table |
| Notification spend/storm abuse | Same `send_whatsapp_message` choke point (opt-out honoured, single send path) | Reused |

**Explicitly deferred (real risks, not built this pass — don't claim they're covered)**:
- Spoilage/expiry-driven loss (`InventoryItem.expiry_days` exists but nothing
  alerts on approaching expiry). Separate directive if prioritized.
- Supplier-side fraud evidence (photos of delivered goods, etc.) — no upload
  pipeline exists in this codebase to build on.
- Multi-location `staff_role` (a manager at one site, supervisor at another)
  — flagged as open in directive 015, not decided here either.

## Architecture

1. **`StockMovement.performed_by_user_id`** — nullable FK to `users`,
   populated by every write path in `routers/inventory.py` going forward
   (`receive_stock`, `adjust_stock`). Nullable because historical rows have
   no actor and can't be backfilled honestly.
2. **`StockTransfer`** (new table) — the store→kitchen leg, modeled as a
   two-party record, not a single `StockMovement` row:
   - `initiated_by_user_id`, `initiated_at`, `quantity` (what the sender says
     they're sending)
   - `confirmed_by_user_id`, `confirmed_at`, `confirmed_quantity` (what the
     receiver actually counts) — nullable until confirmed
   - `status`: `PENDING → CONFIRMED` (matches) or `DISPUTED` (mismatch)
   - On confirm, if `confirmed_quantity != quantity`, emit
     `STOCK_TRANSFER_DISCREPANCY` (immediate, no cooldown — a single
     confirm action can't repeat) instead of silently trusting either party.
   - On confirm with a match, this also writes the underlying
     `StockMovement` OUT/IN pair so existing depletion-prediction code (which
     reads `StockMovement`) keeps working unmodified.
3. **Variance report** (`ai/stock_custody.py`) — theoretical (from
   `MenuIngredient.quantity_per_serving` × `OrderItem` quantities sold) vs
   actual (`StockMovement` OUT sum), per `InventoryItem`, over a rolling
   window (default: previous 24h). Flags any item where
   `abs(actual - theoretical) / theoretical > 0.03` (3%, the conservative end
   of the 2–3% industry range — false positives cost a manager two minutes
   reading a report; false negatives cost real shrinkage). Gated to
   Controller/Owner/Manager per the 015 matrix.
4. **Scheduled job** — `run_variance_check`, once daily (21:00 EAT / 18:00
   UTC, after most of the day's covers), computes the report per restaurant
   and emits `STOCK_VARIANCE_FLAGGED` only for restaurants with at least one
   item over threshold. This is what makes the "daily summary, not
   per-movement" alerting philosophy hold without needing a new cooldown
   column.
5. **Twilio, both directions**:
   - Outbound: `STOCK_TRANSFER_DISCREPANCY` and `STOCK_VARIANCE_FLAGGED`
     handlers in `executive.py`, same shape as `on_stock_critical` — compose
     a message, call `send_whatsapp_message`, write to `AgentAuditLog`.
     Discrepancy alerts go to the Owner/Manager/Controller (whoever has an
     `owner_phone`-equivalent — see Edge Cases, this is currently
     restaurant-level, not per-staff-member).
   - Inbound: `StaffMember.phone` (new nullable column) lets
     `routers/webhooks.py: whatsapp_webhook` resolve a third case — not the
     owner, not a customer, but a staff member — and route simple commands
     (`CONFIRM <transfer_id> <qty>`) to a new
     `brain.handle_staff_command`-style handler. **This is the actual
     "messages going through" automation the user asked for**: a stockkeeper
     can text a quantity back instead of opening the dashboard.
6. **Account lifecycle**: `User.is_active` (new, default `True`), checked in
   `auth.get_current_user` alongside the existing `token_version` check.
   Deactivating a `StaffMember` with a linked `user_id` sets `User.is_active
   = False` and bumps `token_version` in the same transaction — access is
   revoked immediately, not just hidden from a future login attempt.

## Steps

1. Migration 025 (bundled with 015's `staff_role` migration — same release):
   `stock_movements.performed_by_user_id`, `staff_members.phone`,
   `users.is_active`, new `stock_transfers` table.
2. `routers/inventory.py`: stamp `performed_by_user_id` on every movement.
3. New `routers/stock_custody.py`: `POST /stock/transfers` (initiate),
   `POST /stock/transfers/{id}/confirm`, `GET /stock/transfers`,
   `GET /stock/variance-report`.
4. `ai/stock_custody.py`: variance computation, unit-testable in isolation
   from the HTTP layer.
5. `events/bus.py`: add `STOCK_TRANSFER_DISCREPANCY`, `STOCK_VARIANCE_FLAGGED`.
6. `executive.py`: two new handlers, registered in `register_all_handlers`.
7. `main.py`: `run_variance_check` scheduled job, same registration pattern
   as `_run_stock_check_job`.
8. `webhooks.py`: staff phone resolution branch + `handle_staff_command`.
9. `auth.py`: `is_active` check in `get_current_user`; staff deactivation
   endpoint bumps `token_version`.
10. Frontend: transfer initiate (Stockkeeper) / confirm (Kitchen) UI,
    variance report view (Controller/Owner/Manager) — see 015 for nav gating.

## Verify before calling it done

- Unit test variance math: zero variance, under-threshold, over-threshold,
  and the div-by-zero case (theoretical usage of 0 — an item nobody's recipe
  uses but that still moved stock; don't crash, just skip it).
- Confirm a `StockTransfer` mismatch actually emits
  `STOCK_TRANSFER_DISCREPANCY` exactly once (not zero, not twice — same
  double-send class of bug as the 2026-07-08 stock-check fix).
- Confirm deactivating a `StaffMember` with a linked login actually 401s
  their very next request, not just hides the nav link.
- Confirm the staff-command webhook branch only fires for a signature-valid
  request — no new bypass of `validate_twilio_request`.

## When you're done

If the variance threshold, alert cadence, or staff-command vocabulary changes
from what's specified here during implementation, update this file in the
same change — this is a living spec, not a design doc to archive.

## As-built notes (2026-07-15)

Everything in "Steps" above shipped as specified, with these refinements
made during implementation (each is a real decision, not a rubber-stamp):

- **Confirm logic lives once, in `ai/stock_custody.py::confirm_transfer`**,
  not duplicated between the HTTP route and the WhatsApp handler. Originally
  drafted inline in `routers/stock_custody.py`, then extracted when it became
  clear the inbound `CONFIRM` command needed byte-identical mismatch/audit/
  event behavior — exactly the double-send risk this directive already
  called out, so the fix was to have one implementation, two callers.
- **Variance threshold is 3% flat**, not "2-3%" — picked the conservative end
  explicitly (see `ai/stock_custody.py`'s `VARIANCE_THRESHOLD` docstring) so
  false positives (a manager reading an unnecessary report) are cheaper than
  false negatives (real shrinkage going unflagged).
- **`StockTransfer` has no "who should receive this" field.** `to_location`
  is a place ("kitchen"), not a person, so the outbound Twilio nudge to a
  specific receiving staff member isn't wired yet — a receiver only learns
  about a pending transfer via the dashboard's pending-transfers list. The
  inbound half (`CONFIRM <id> <qty>` via WhatsApp/SMS) IS fully wired and
  works today for anyone who already knows a transfer id exists. Closing this
  loop needs a real "who's on duty right now" signal this codebase doesn't
  have yet — flagged as follow-up, not silently dropped.
- **Backend RBAC matrix applied to inventory, menu, ai.py, and analytics.py's
  6 GET routes** — orders.py and reservations.py were deliberately left on
  their pre-existing "any authenticated user" gate rather than tightened to
  match directive 015's per-role matrix exactly, since verb-level
  differentiation (POST vs PATCH) wasn't already structurally separated
  there the way inventory.py's routes were, and tightening them blind
  risked a real regression for Waiter/Supervisor's day-to-day POS flow. This
  is real matrix debt, not an oversight — worth its own follow-up pass with
  its own test coverage rather than folding into this already-large change.
- **`users.is_active` added** (not originally in models.py) — found the real
  gap this directive predicted: `StaffMember.is_active` existed but nothing
  downstream acted on it. Now checked in `auth.get_current_user` and flipped
  automatically by `routers/staff.py`'s deactivation path, which also bumps
  `token_version` in the same transaction for immediate revocation.
- **Frontend**: transfer initiate/confirm + a variance panel were added to
  the existing `/dashboard/inventory` page rather than a new route — Stock
  nav already covers Controller/Stockkeeper/Kitchen per 015's matrix, so a
  separate page would have just meant a second nav entry pointing at the
  same audience. Both panels are best-effort (`null` response = hidden
  panel, not an error state) so a role without `/stock/*` access sees a
  normal inventory page instead of a broken one.
