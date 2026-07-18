---
name: stock-loss-prevention
description: Design or implement the supplier-to-store-to-kitchen stock chain-of-custody, variance/shrinkage detection, and automated theft-risk alerts for the restaurant-agent app. Use this whenever asked about stock movement tracking, who moved/received/used inventory, theft or shrinkage prevention, stock variance reports, or extending the existing Twilio/WhatsApp alert pipeline to cover risk events (not just low-stock). Also use it before adding any new inventory-adjustment endpoint, to check whether it's recording who performed the action.
---

# Stock Chain-of-Custody & Loss Prevention

## Check for a directive first

No directive exists yet for this workstream. Before writing code, check
whether `directives/016_*.md` (or higher) already covers this — if not,
draft `directives/016_stock_loss_prevention.md` following the pattern in
`directives/007_inventory.md` and `directives/015_staff_roles_permissions.md`
(Goal / Inputs / Architecture / Steps / Edge Cases), get it reviewed, then
implement. This repo's CLAUDE.md is explicit: directives are the SOP layer
and shouldn't be skipped even when the fix feels obvious.

## Ground yourself in what already exists — this is more built than it looks

- `backend/models.py: StockMovement` (search `class StockMovement`) tracks
  `movement_type` (`IN/OUT/ADJUST`), `quantity`, freeform `reason` ("sale",
  "waste", "purchase", "adjustment"), `created_at`. **It has no field
  recording who performed the movement.** This is the actual gap: you
  cannot answer "who moved this stock" today. Any loss-prevention work
  starts here — add `performed_by_user_id` (or `staff_member_id`) before
  building variance reports on top of it, or the reports will have no
  accountability trail, which defeats the point.
- `Supplier` and `PurchaseOrder` (`models.py`, search `class Supplier`)
  **already model supplier→store**: `PurchaseOrder.quantity_ordered` vs
  `quantity_received`, `status` (`PENDING→SENT→DELIVERED/LATE/PARTIAL`).
  Supplier-side variance (ordered vs. received) is already representable —
  don't rebuild it, extend it (e.g. flag `quantity_received < quantity_ordered`
  beyond a tolerance as a variance event).
- **Store→kitchen transfer has no model yet.** `StockMovement.reason` is
  freeform text, not a structured transfer with a source/destination and an
  accountable party. This is the real net-new piece, not the supplier side.
- `InventoryItem.last_alerted_at` + the cooldown logic in
  `backend/ai/whatsapp/brain.py` (`run_stock_check`,
  `STOCK_ALERT_COOLDOWN_HOURS`, migration 010) is the **existing, working**
  per-subject alert-cooldown pattern — 12h cooldown, stamped per item, so a
  persistently low item doesn't re-alert every 2h cycle. Reuse this
  mechanism for variance/theft alerts; do not build a second cooldown
  system. `directives/012_agentic_roadmap.md` documents a real bug that was
  fixed here (a handler double-sending WhatsApp alerts because both the
  emitter and the handler tried to notify) — read that section before
  wiring a new alert type into the event bus, so you don't reintroduce it.
- `backend/ai/whatsapp/twilio_client.py` is the real, signature-verified
  Twilio integration already in production use for owner alerts
  (`Restaurant.owner_phone` / `owner_channel`). Extending it to theft/
  variance alerts means adding a new event type through the **existing**
  event bus (`backend/events/bus.py`) with its own handler — it does not
  mean adding a second Twilio client or a parallel notification path.

## The actual loss-prevention pattern (verified externally, not guessed)

Industry-standard practice, not this repo's invention — cite this if asked
why the numbers are what they are:

- Compare **theoretical usage** (what the POS/recipe data says should have
  been consumed — this repo already has `MenuIngredient` linking
  `MenuItem`→`InventoryItem`, see `directives/007_inventory.md`'s "Bundle
  Items" edge case) against **actual usage** (recorded `StockMovement` OUT
  entries). A gap above roughly **2–3%** is the standard trigger for
  investigation — below that, it's noise (spoilage, portion variance), not
  a signal.
- Alert on the **variance report**, not on every individual movement — a
  daily/shift-level summary to the owner/manager/controller, not a message
  per adjustment. This matches the existing cooldown philosophy above.
- Separation of duties, not just alerting: the Controller role (see the
  `staff-roles-permissions` skill / directive 015) can read variance
  reports but not adjust stock — the person catching a discrepancy
  shouldn't be the person who could have caused it. Don't build variance
  detection without also making sure that role boundary actually holds in
  the routers, or the control is theater.

## Implementation sequence

1. Draft/update the directive (see above) if it doesn't already reflect
   this plan.
2. Migration: `performed_by_user_id` on `StockMovement` (nullable initially
   for backward compat with existing rows, required going forward at the
   API layer).
3. New structured transfer concept for store→kitchen (a `reason="transfer"`
   movement pair, or a dedicated model if the freeform `reason` proves too
   loose to query reliably — check how `reason` is actually queried
   elsewhere before deciding).
4. Variance computation: theoretical (via `MenuIngredient` + sales) vs.
   actual (via `StockMovement` OUT), surfaced as a report, gated to
   Controller/Owner/Manager per the permission matrix.
5. New event type (e.g. `STOCK_VARIANCE_FLAGGED`) through `events/bus.py`,
   one handler, reusing the `last_alerted_at`-style per-subject cooldown —
   do not let both an emitter and a handler send the WhatsApp/SMS
   themselves (see the double-send bug reference above).
6. Verify: unit test the variance math against known-good and known-bad
   scenarios (zero variance, under-threshold, over-threshold), and confirm
   the cooldown actually prevents re-alerting within the window before
   calling this done.

## When you're done

Write down in the directive what the actual chosen variance threshold and
alert cadence ended up being, and why, if it differs from the 2–3%
industry-standard starting point above — that's exactly the kind of
learned constraint CLAUDE.md wants captured, not left in a commit message.
