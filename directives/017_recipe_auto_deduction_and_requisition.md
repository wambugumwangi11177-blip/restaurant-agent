# Directive: Recipe-Driven Auto-Deduction, Kitchen Requisition & Physical Counts

**Goal**: Close the last manual link in the stock chain — selling a dish
should deduct its ingredients without anyone typing a number — while adding
the one check (a physical count) that keeps theft/shrinkage detection real
once that deduction is automatic, and give the kitchen a way to pull stock
from the store instead of only the store pushing it.

**Status**: Implemented (2026-07-15), same branch as directives 015/016
(`feat/staff-rbac-stock-custody-twilio`). 12 new tests pass
(`tests/test_recipe_auto_deduction_and_requisition.py`), full suite green,
frontend `tsc --noEmit` clean.

## What prompted this

Planning session with the owner surfaced two gaps in what directive 016
built:

1. `MenuIngredient` (the recipe model — links a `MenuItem` to the
   `InventoryItem`s it uses, with `quantity_per_serving`) already existed
   and was already read by the knowledge graph and the stock-critical
   cascade — but **nothing let an owner actually populate it**. No API, no
   UI. Verified by grep before assuming: zero references to `MenuIngredient`
   in any router or any frontend file.
2. Marking an order SERVED never touched inventory at all — verified by
   reading `routers/orders.py`'s `update_order_status`: it only sets
   `completed_at`. The variance report directive 016 built (theoretical
   recipe usage vs. recorded `StockMovement` OUT) was comparing two numbers
   that, once this gap closed, would risk becoming the same number computed
   twice — see "The circularity risk" below.

## Design decisions made with the owner, and why

- **Deduct at order creation, not at SERVED.** The owner's call: the
  customer is committed to buying it the moment it's rung up. Requires a
  reversal path for cancellation, which order-completion-time deduction
  wouldn't have needed — accepted as the tradeoff.
- **Reversal only applies if cancelled before SERVED.** If the order was
  already served, the ingredients were physically used regardless of what
  happens to the bill afterward — reversing here would put fictional stock
  back. Verified this is a clean rule to implement: orders in this codebase
  can't be edited after creation, only their status transitions
  (`routers/orders.py` has no line-item add/remove endpoint), so "reversal"
  only ever means "credit back the whole order," never a partial edit.
- **Recipe editor uses "Lavy" as the reference set** (the existing demo
  restaurant referenced elsewhere in this app) for example content, per the
  owner's direction — but there was no existing ingredient-level Lavy data
  to import; example quantities were authored, not pulled from something
  real. If real recipe data exists, it should replace the illustrative
  examples.
- **Kitchen requisition rebuilt as a pull**, not just directive 016's push.
  The owner's own described workflow (kitchen asks → storekeeper checks
  their own records and fulfills → supervisor sees the log) is a real,
  named restaurant practice ("requisition and issue system" — external
  research, not invented here). The existing `StockTransfer` push flow
  (store declares, kitchen confirms) is the *wrong direction* for "kitchen
  realizes mid-shift they're short" — that has to start with the kitchen.
- **Physical count, not a rebuilt variance report.** See below.

## The circularity risk, and how it's resolved

Once `StockMovement` OUT entries are written automatically from the recipe
math (this directive), directive 016's variance report — theoretical usage
(recipe × sales) vs. actual usage (recorded `StockMovement` OUT) — risks
comparing the same number to itself: the "actual" entries now *are* the
recipe math, so they agree by construction. A gap stops being a signal.

**Resolution**: `StockCount` (new) is a physical count — someone actually
looking at the shelf — compared against `InventoryItem.quantity` at count
time. This is the one number in the whole system that doesn't derive from
the recipe, which is what makes a mismatch here meaningful. Directive 016's
variance report is **not removed or rearchitected** in this pass — it still
runs, and still catches gaps in movements that never went through recipe
auto-deduction at all (manual adjustments, waste, the store→kitchen leg).
The physical count is a second, independent check layered alongside it, not
a replacement. Revisiting whether the two should be unified into one report
is flagged as a follow-up, not decided here.

## Architecture

1. **Recipe editor** — `routers/menu.py` gains
   `GET/POST /menu/{item_id}/ingredients`,
   `PUT/DELETE /menu/{item_id}/ingredients/{ingredient_id}`. Same
   `_CAN_WRITE` (Owner/Manager) gate as the rest of `menu.py`; reads open to
   any authenticated user, matching the existing menu-read posture.
2. **Auto-deduction** — `ai/order_stock.py` (new):
   `deduct_ingredients_for_order` / `reverse_ingredients_for_order`, pure
   functions over a `Session`, called from both `routers/orders.py` order-
   creation paths (staff `create_order` and the public `create_public_order`
   — the public one has no `current_user`, so movements are attributed to
   no one rather than guessed) and from `update_order_status`'s cancel
   branch. Best-effort: a deduction failure is logged and rolled back but
   never blocks the order itself — the sale already happened.
   Negative stock is allowed, per directive 007's existing policy — this
   directive doesn't relitigate that, just relies on it.
3. **Kitchen requisition (pull)** — `StockTransfer` gains a `REQUESTED`
   status and nullable `requested_by_user_id`/`requested_at`; `quantity` and
   `initiated_by_user_id` become nullable to support a request with no
   quantity yet. New `ai/stock_custody.py` functions `request_transfer` /
   `fulfill_transfer`, mirroring `confirm_transfer`'s shared-between-HTTP-
   and-Twilio pattern. `confirm_transfer` itself is **unchanged** — a
   fulfilled pull transfer reaches `PENDING`, the same state a push transfer
   starts at, so the receiver-side confirm logic doesn't need to know which
   way the transfer originated.
4. **Physical counts** — new `StockCount` table + `ai/stock_custody.py`'s
   `submit_count`: records the count, reconciles `InventoryItem.quantity` to
   match it (an ADJUST/OUT movement, same mechanism as the existing manual
   `/adjust` endpoint), and emits `STOCK_COUNT_DISCREPANCY` only when the
   gap exceeds `VARIANCE_THRESHOLD` (reused, not a second number to keep in
   sync) — matches the "alert on the exception" philosophy from directive
   016.
5. **Twilio** — `ai/whatsapp/brain.py: handle_staff_command` gains `NEED`,
   `SEND`, `COUNT` alongside the existing `CONFIRM`. `NEED`/`COUNT` resolve
   an inventory item **by name** (case-insensitive exact match, falling back
   to a single unambiguous partial match) since a kitchen worker knows an
   ingredient's name, not its database id — unlike `SEND`/`CONFIRM`, which
   reference a transfer id the person already has from a prior message.

## Verify before calling it done

- Order creation deducts the right quantity (recipe × quantity sold), not
  the recipe's `quantity_per_serving` alone.
- An order with no recipe defined for its menu item doesn't crash — it's
  silently skipped (flagged in the frontend's recipe editor as "no recipe
  set," not silently invisible everywhere).
- Cancelling before SERVED credits back exactly what was deducted; cancelling
  after SERVED does not.
- A pull-initiated transfer, once fulfilled, behaves identically through
  confirm as a push-initiated one — including the mismatch/dispute path.
- A physical count's gap only triggers an alert when it exceeds threshold,
  and always reconciles `InventoryItem.quantity` regardless of whether it
  triggers one.

## Explicitly out of scope for this directive (real follow-ups, not silently dropped)

- **Order modifiers** ("no cheese" only deducting what was actually used) —
  there is no concept of an order-item customization anywhere in this
  schema (`OrderItem` is just `menu_item_id` + `quantity`). Needs its own
  data model and POS UI before deduction logic could honor it.
- **Routing a pull request's outbound Twilio nudge to a specific person** —
  same gap directive 016 already flagged: nothing in this codebase knows
  "who's on kitchen/store duty right now" to notify proactively. The
  inbound half (`NEED`/`SEND`/`CONFIRM`/`COUNT`) works today regardless of
  how someone learns a request exists.
- **Par-level / reorder-point automated purchasing** — the next planned
  phase (demand-adjusted par levels, draft PO generation, supplier Twilio
  contact), not started here.
- **Unifying the recipe-based variance report and the physical-count
  discrepancy check into one signal** — flagged above, deliberately left as
  two separate checks for now rather than guessing at the right merge.

## When you're done

If the reversal rule, the recipe-editor UX, or the requisition vocabulary
changes during further use, update this file in the same change — living
spec, not an archived design doc.
