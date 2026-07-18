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
- **2026-07-17 update**: the *Twilio* nudge above is still open (needs
  "who's on duty"), but the **in-app** half of this same gap didn't actually
  need that signal and was closed: `ai/notify.py`'s `notify_users` already
  fans out by `staff_role`, not by a specific person, which is exactly what
  role-based events need. `request_transfer`/`fulfill_transfer`
  (`ai/stock_custody.py`) now emit `STOCK_TRANSFER_REQUESTED` /
  `STOCK_TRANSFER_FULFILLED` (new in `events/bus.py`), handled in
  `ai/orchestrator/push_notifier.py` — see that directive's notes in
  017/018 below for the full chain this unblocked (Kitchen had no page to
  request from at all until the same pass added one).
- **A separate, pre-existing bug found and fixed in the same pass**:
  every `push_notifier.py` deep link was still hardcoded to
  `/dashboard/<route>`. Since directive 015's 2026-07-17 nav rework made
  `/dashboard/*` Owner-only (any `staff_role` account gets redirected off it
  on load), every notification sent to a non-Owner tier — stock critical,
  stock depleted, transfer discrepancy, variance flagged, count discrepancy,
  purchase order late, reservation no-show — deep-linked to a page that
  immediately bounced the recipient back to their own tier home. Fixed by
  resolving the link per-recipient's `staff_role` against a `_TIER_URLS` map
  (mirrors `frontend/src/lib/permissions.ts` + each tier's `layout.tsx` nav)
  instead of one link for everyone. Keep `_TIER_URLS` in sync with the
  frontend route tree the same way `permissions.ts`'s own docstring already
  warns about for its matrix.
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

## 2026-07-17 incident: this branch and production share one database

While setting up test logins for the notification work above, discovered
`backend/.env`'s `DATABASE_URL` is the **same Neon database the live
Railway/master backend uses** — there is no separate branch/dev DB. Running
this branch's pending migrations (034-036) against it broke live production:
migration 035 (`convert_inventory_cost_to_cents`) renamed
`inventory_items.cost_per_unit` to `cost_per_unit_cents`, but `master`'s
deployed `models.py` still reads `cost_per_unit` as a raw column — confirmed
`GET /inventory/` 500ing on the live Railway API within minutes of the
migration. Rolled back to `034_add_auth_tokens_and_email_verified`
immediately (`alembic downgrade`) and re-verified the live endpoint returned
200 again. **This is exactly the anti-pattern [[restaurant-agent-deploy-facts]]
already warned about** ("never let a preview/branch/local env share the prod
DATABASE_URL") — it just hadn't bitten a feature branch's *local dev* usage
before, only preview deploys.

**Resolution for local dev/testing going forward**: `execution/seed_local_dev_db.py`
builds a throwaway SQLite file (`backend/dev_local.db`) via
`database.init_db()` (schema from current `models.py` directly, no migration
ambiguity) and seeds one login per staff tier. Run it, then start the backend
with `DATABASE_URL=sqlite:///dev_local.db` — `backend/.env`'s real
`DATABASE_URL` is never touched. **Do not run `alembic upgrade`/`downgrade`
against the real `DATABASE_URL` again without explicit, named user
confirmation** — this incident is why.

**Still true and unresolved**: this branch's `models.py` (the
`cost_per_unit_cents` property) has not been merged to `master`/deployed, so
the *real* database is intentionally left stamped at `034`, one migration
behind this branch's code. Whoever merges this branch to `master` must run
migrations 035/036 as part of that deploy, not before it.

## 2026-07-17: notification-coverage audit ("automate everything")

Audited every `EventType` against `events/bus.py`'s registry, every actual
`emit`/`emit_async` call site, and `push_notifier.py`'s subscriber list, to
find events that fire but notify nobody, and real actions with no event at
all. Verified each gap by reading the code, not guessing — several
plausible-looking gaps turned out to be intentional and were left alone:

- `RESERVATION_CREATED`/`RESERVATION_CANCELLED` are never emitted — correctly:
  `routers/reservations.py` has no public/unauthenticated creation endpoint,
  so every reservation is staff-created. Notifying staff about their own
  action would be noise, not signal.
- `ORDER_CREATED`/`ORDER_COMPLETED`/`ORDER_CANCELLED` are never emitted —
  left alone: Kitchen already watches a real-time KDS board for new orders;
  a push notification on top would duplicate a screen already being looked
  at, the exact alert-fatigue pattern this workstream has avoided elsewhere.
- `RECOMMENDATION_GENERATED` is never emitted — correct: pricing
  recommendations are generated on-demand when a human opens `GET
  /ai/pricing` (`sync_pending_recommendations`), not by a background job, so
  there's no "silent recommendation nobody knows about" moment to notify.
- `STOCK_LOW` is dead code, superseded by the two-tier `STOCK_CRITICAL`/
  `STOCK_DEPLETED` design (documented in `ai/whatsapp/brain.py`'s
  `run_stock_check` docstring from the 2026-07-07/08 audit) — not a gap.

Real gaps closed (all additive, no new DB columns/migrations):

- **`ORDER_PAID` via the M-Pesa webhook only** — new push handler
  (`_on_order_paid`), gated on `mpesa_reference` being present in the
  payload so the POS "mark as paid" emit (`routers/orders.py`, a staff
  member's own synchronous action) is correctly excluded. Closes a real gap:
  M-Pesa settles asynchronously (customer approves on their own phone,
  sometimes minutes later) and Waiter/Supervisor had no signal it landed —
  confirmed by reading `POSWorkspace.tsx`, which has no payment-status
  polling at all.
- **`PURCHASE_ORDER_DELIVERED`** (short delivery) — had a WhatsApp handler
  (Owner-only) but no push handler, so Manager/Controller/Stockkeeper never
  learned of a shortfall through any channel.
- **`RECOMMENDATION_APPROVED`** — `approve_pricing_rec()` updates the live
  menu price immediately; the existing WhatsApp handler only records
  memory/audit bookkeeping, notifies nobody. Added a push handler targeting
  the POS-facing tiers (Waiter/Supervisor/Manager/Owner) so nobody quotes a
  stale price.
- **New `ACCOUNT_LOCKED`** (`events/bus.py`) — emitted once, exactly at the
  failed-login-attempt threshold transition (`routers/auth.py`'s login
  endpoint), Owner-only. A brute-force signal that previously existed only
  as silent `locked_until` state in the DB.
- **New `STAFF_ROLE_CHANGED`** — emitted from `routers/staff.py`'s
  `assign_role`, Owner-only, excludes the actor (`exclude_user_id` param
  added to `push_notifier._fan_out`) so the Manager who made the change
  doesn't get told about their own action. Real-time companion to the
  `AgentAuditLog` entry that already existed — audit trail answers "what
  happened," this answers "did anyone notice right now."
- **Two matrix-vs-reality frontend gaps found in the same pass** (same class
  as the Supervisor-purchasing gap found 2026-07-17 earlier the same day):
  `permissions.ts` granted Supervisor `menu: "r"` but no
  `/staff/supervisor/menu` page existed. Added it (reuses `MenuReadView`,
  same as Kitchen/Waiter) + nav entry.
- Added `orders`, `menu`, `staff` domains to `push_notifier.py`'s
  `_TIER_URLS` map (previously only `inventory`/`purchasing`/
  `reservations`/`ai-ops` existed) to support the deep links above.

**Deliberately not added** (considered, rejected with a reason, not silently
skipped): `MFA disable` notification — self-only action requiring proof of
the current TOTP code first, so it's neither a stolen-session vector nor
something the account owner doesn't already know about. Adding it would be
notification volume without a real signal, the opposite of this
workstream's own stated philosophy.

## 2026-07-17: second pass, same audit continued

Three more gaps closed, same verify-before-building discipline as above:

- **New `STAFF_DEACTIVATED`** — `routers/staff.py`'s `update_staff` already
  revoked a deactivated login's session (directive 016's original build) and
  wrote an audit-log entry, but nobody was told it happened in real time.
  Owner-only, excludes the actor (reuses `_fan_out`'s `exclude_user_id`).
  Directive 016's own risk table names "ex-staff retaining access" as the
  exact risk this closes the loop on — the person revoking access now gets
  it confirmed back, not just logged.
- **`STAFF_ROLE_CHANGED` reused (not a new event) for brand-new logins** —
  `create_staff`'s `create_login` path grants a role to a new account
  through the same `_require_grant_allowed` boundary as `assign_role`; from
  a "who has access" standpoint a new grant is the same signal as a changed
  one. Emits with `before_role=None`, which the handler already renders as
  "unassigned -> <role>" — reused the existing event/handler rather than
  adding a near-duplicate.
- **New `MENU_ITEM_UNAVAILABLE`** — `routers/menu.py`'s `update_menu_item`
  captures `is_available` before applying the update and fires only on the
  True->False transition (an item going back available is lower urgency and
  deliberately not notified — one-directional by design, see the event's
  docstring in `events/bus.py`). Targets every POS-facing tier
  (Waiter/Supervisor/Manager/Owner): a manager 86ing an item mid-shift
  previously had no way to tell whoever's on the floor to stop selling it
  except walking over and saying so.

**Verified working end-to-end against the isolated local dev stack** (not
just unit tests): triggered a real account lockout and a real role
reassignment through the running API and confirmed the right notification
landed in the right account's feed with the actor correctly excluded.

**Considered and explicitly left out of this pass**: notifying on
`StaffMember` reactivation (asymmetric with deactivation — reactivating is a
deliberate, already-visible action to whoever does it, lower urgency than
"did the revocation I just did actually happen"); a "menu item back in
stock" notification (same reasoning). Both are cheap to add later if this
judgment call turns out wrong in practice — flagged, not silently dropped.
