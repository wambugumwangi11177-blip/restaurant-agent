# Directive 019 — Event Catalog & Notification Routing

> The single source of truth for **what events exist**, **what fires them**, **who
> gets notified**, and **which of them are live vs. still on the roadmap**.
> Companion to the code in `backend/events/bus.py` (the enum + bus),
> `backend/ai/orchestrator/push_notifier.py` (in-app + Web Push fan-out), and
> `backend/ai/orchestrator/executive.py` (owner WhatsApp + agent reasoning).

## 1. The event-bus model

Every notable thing that happens in the restaurant is (or can become) an **event
on an internal bus**. A single emitted event can simultaneously:

1. **Notify the right humans** — role-scoped in-app feed + Web Push
   (`push_notifier.py`), and/or the owner's WhatsApp (`executive.py`).
2. **Wake an AI agent** — the orchestrator reasons across agents/memory and acts
   (`executive.py`'s handlers; e.g. a late supplier penalises the reliability
   score, a no-show can trigger winback).
3. **Feed the audit log & memory** — `write_audit_log` / `ai.memory.store`.

This is the architecture the "exhaustive event map" (below) is meant to grow
into. It is deliberately **incremental**: we wire an event the moment a real
trigger and a real recipient both exist — not before.

## 2. The one rule that governs this whole workstream

> **Alert on the exception, not the routine. Never emit a dead event.**

Two hard consequences, learned the hard way across directives 015–018 and the
2026-07-17 notification audit:

- **No dead enums.** An `EventType` value that nothing emits and nothing
  subscribes to is dead code that rots. The `EventType` enum only ever contains
  events that are *actually emitted*. The full aspirational map lives in this
  directive (§5) as a **roadmap**, not as 400 unused enum members. When a
  trigger and a recipient both become real, the event graduates from §5
  (PLANNED) into the enum and §4 (LIVE).
- **Guard against alert fatigue.** Most events are *exceptions* (stockout,
  variance, failed payment, lockout) and go to a tight recipient list. A handful
  of high-frequency *operational* events (a ready ticket, a new booking) are
  allowed **only** when the recipient would otherwise have to poll a screen —
  and even then they are push-only, role-scoped, exclude the actor, and
  **exclude the Owner** (whose feed is reserved for the exception class). See the
  `_EVENT_TARGET_ROLES` comments in `push_notifier.py`.

## 3. How to add a new event (the SOP)

For each new event, in order:

1. **`backend/events/bus.py`** — add one `EventType` member (`domain.action`,
   snake_case) with a comment stating *why it fires and why it's routed the way
   it is*.
2. **Emit at the trigger site** — the router/service where the condition
   actually occurs. Use `emit_async(...)` (background thread) unless the handler
   must run inside the request. Fire **once, on the real state transition**
   (guard on the old status), not on every write. Include an `actor_user_id` in
   the payload if the actor should be excluded from the fan-out.
3. **Subscribe a push handler** in `push_notifier.py`: add the row to
   `_EVENT_TARGET_ROLES`, `subscribe(...)` in `register_push_handlers()`, and
   write the `_on_<event>` handler (mirror the existing ones — resolve the
   restaurant, build title/body, call `_fan_out(...)` with the domain and any
   `exclude_user_id`).
4. **(Optional) subscribe an owner/agent handler** in `executive.py` — only if
   the owner personally needs the WhatsApp *or* an agent should reason/act on it.
   Many operational events are push-only and skip this step (that's the norm,
   not the exception).
5. **Test** in `tests/test_push_notifier.py`: targeted roles get it, untargeted
   roles (and, for operational events, the Owner) do not, the actor is excluded,
   and the resolved link matches the recipient's tier.

`_fan_out` already resolves each recipient's link to a page *their* tier can
actually open (`_TIER_URLS` / `_TIER_HOME`) — keep that table in sync with
`frontend/src/lib/permissions.ts` when adding a domain.

## 4. LIVE events (currently emitted & routed)

Roles below are the **push** recipients (`_EVENT_TARGET_ROLES`). "Owner WA"
marks events that also reach the owner's WhatsApp and/or an agent handler in
`executive.py`.

| Event | Fires when | Emitter | Push recipients | Owner WA / agent |
|---|---|---|---|---|
| `stock.critical` | Item ~hours from zero | `ai/whatsapp/brain.py` | Owner, Mgr, Controller, Stockkeeper | ✅ |
| `stock.depleted` | Item hit zero | `ai/whatsapp/brain.py` | Owner, Mgr, Controller, Stockkeeper | ✅ |
| `stock_transfer.discrepancy` | Store→kitchen confirm ≠ declared | `ai/stock_custody.py` | Owner, Mgr, Controller | ✅ |
| `stock.variance_flagged` | Daily variance job > threshold | `main.py` | Owner, Mgr, Controller | ✅ |
| `stock_count.discrepancy` | Physical count ≠ system | `ai/stock_custody.py` | Owner, Mgr, Controller | ✅ |
| `stock_transfer.requested` | Kitchen pulls an ingredient | `ai/stock_custody.py` | Owner, Mgr, Supervisor, Stockkeeper | — |
| `stock_transfer.fulfilled` | Store commits qty to a pull | `ai/stock_custody.py` | Owner, Mgr, Supervisor, Kitchen | — |
| `purchase_order.created` | PO auto-drafted (par crossed) | `ai/reorder.py` | Owner, Mgr, Supervisor, Controller | ✅ |
| `purchase_order.approved` | PO approved & sent to supplier | `ai/reorder.py` | Mgr, Controller, Stockkeeper | — |
| `purchase_order.delivered` | Short/partial delivery received | `ai/reorder.py` | Owner, Mgr, Controller, Stockkeeper | ✅ |
| `purchase_order.late` | Delivery overdue | `main.py` | Owner, Mgr, Controller | ✅ |
| `inventory.adjustment_flagged` | Manual downward stock adjustment (waste/loss) | `routers/inventory.py` | Owner, Mgr, Controller (excl. actor) | — |
| `supplier.reliability_dropped` | Reliability crosses watch threshold (≤70) | `ai/orchestrator/executive.py` | Owner, Mgr, Controller | — |
| `order.created` | Online order placed (public path, no staff) | `routers/orders.py` | Mgr, Supervisor, Kitchen | — |
| `order.paid` | M-Pesa settled (webhook) | `routers/webhooks.py`, `routers/orders.py` | Owner, Mgr, Supervisor, Waiter | ✅ (receipt) |
| `order.ready` | Kitchen marks ticket READY | `routers/orders.py` | Mgr, Supervisor, Waiter | — |
| `order.cancelled` | Live ticket pulled | `routers/orders.py` | Mgr, Supervisor, Kitchen | — |
| `mpesa.payment_failed` | STK push failed/cancelled | `routers/webhooks.py` | Owner, Mgr, Supervisor, Waiter | ✅ |
| `reservation.created` | New booking taken | `routers/reservations.py` | Mgr, Supervisor, Waiter | — |
| `reservation.cancelled` | Booking cancelled/deleted | `routers/reservations.py` | Mgr, Supervisor, Waiter | — |
| `reservation.no_show` | Booking marked no-show | `routers/reservations.py` | Owner, Mgr, Supervisor, Waiter | ✅ (winback) |
| `menu_item.unavailable` | Item 86'd mid-shift | `routers/menu.py` | Owner, Mgr, Supervisor, Waiter | — |
| `recommendation.generated` | AI pricing rec batch generated (awaiting review) | `ai/pricing/recommendations.py` | Owner, Mgr | — |
| `recommendation.approved` | Pricing rec approved (live price change) | `ai/pricing/recommendations.py` | Owner, Mgr, Supervisor, Waiter | ✅ |
| `price.changed` | Menu price edited **by hand** | `routers/menu.py` | Owner, Mgr, Supervisor, Waiter (excl. actor) | — |
| `account.locked` | Login crossed failed-attempt threshold | `routers/auth.py` | Owner | — |
| `staff.role_changed` | Staff role changed | `routers/staff.py` | Owner (excl. actor) | — |
| `staff.deactivated` | Staff login revoked | `routers/staff.py` | Owner (excl. actor) | — |
| `staff.reactivated` | Revoked staff login restored | `routers/staff.py` | Owner (excl. actor) | — |
| `agent.failed` | AI agent run failed | `routers/ai.py` | Owner | ✅ (≥3/hr) |

> **2026-07-18 event-map pass** wired, in two batches:
> **Batch 1** (operational, push-only, actor- & Owner-excluded — the first live
> events deliberately kept off the owner's feed, per §2): `order.ready`,
> `order.cancelled`, `reservation.created`, `reservation.cancelled`,
> `purchase_order.approved`.
> **Batch 2** (Tier-A events needing no new tables): `inventory.adjustment_flagged`
> (shrinkage signal → custody oversight), `supplier.reliability_dropped`
> (procurement oversight), `order.created` (online-order gap → kitchen).
> **Batch 3** (Tier-A audit follow-up — wiring two enums that were defined but
> never emitted): `price.changed` (manual menu price edit, the hand-driven twin
> of `recommendation.approved`) and `recommendation.generated` (nudge the
> approver that an AI pricing batch is waiting).
> **Batch 4** (final Tier-A sweep across billing/suppliers/enterprise/staff/
> auth): one clean gap — `staff.reactivated`, the symmetric partner of
> `staff.deactivated`. Everything else in those routers is either a self-action
> with no distinct recipient (billing plan change, supplier CRUD, email-verify)
> or a security event whose recipient is a policy question (impersonation,
> password-reset, MFA-disable) — see §5.13.

## 5. The full event map (roadmap) — PLANNED vs LIVE

The catalog the owner supplied, kept complete and honest. **LIVE** = wired
(see §4). **PLANNED** = valuable but blocked on a prerequisite the app doesn't
have yet; the "needs" column is the gate. Grouping follows the owner's map.

A recurring theme: whole domains are **PLANNED-blocked on hardware/integrations
this software doesn't have** — IoT temperature probes, delivery GPS, cameras,
cash-drawer hardware, equipment/POS-printer telemetry, POS payment-processor
webhooks. Those are honest "not yet," not oversights.

### 1. Suppliers / Purchasing
- **LIVE:** PO created, PO approved/sent, PO delivered (short), supplier late.
- **PLANNED:** PO rejected/modified/cancelled *(need a reject/cancel endpoint —
  today a draft PO is only ever approved or ignored)*; supplier
  acknowledged/declined/requested-changes/confirmed-date *(need a supplier
  reply channel — directive 018 deliberately made the send one-way)*; delivery
  truck approaching / arrived / unloaded / signed *(need driver GPS/ePOD)*;
  goods rejected / quantity·weight mismatch / wrong·damaged·expired·missing·extra
  items / temperature violation *(the receive endpoint captures a single
  quantity today; per-line QC + cold-chain probes are the prerequisite)*;
  **supplier rating dropped / consistently late** → LIVE via
  `supplier.reliability_dropped` (reliability_score crosses the watch
  threshold); price increased / better supplier found / contract expiring /
  inactive / blacklist remain PLANNED *(need supplier scorecard trend + contract
  records)*.

### 2. Inventory
- **LIVE:** stock low→`stock.critical`, depleted, variance flagged, count
  discrepancy, transfer requested/fulfilled/discrepancy; **adjusted / manual
  override / unauthorized adjustment / waste recorded / theft suspected** all
  covered by `inventory.adjustment_flagged` (fires on manual downward adjust).
- **PLANNED:** overstock / safety-stock breached / emergency stock *(need par +
  safety-stock thresholds surfaced as events; par exists for reorder only)*;
  reorder awaiting approval *(covered indirectly by `purchase_order.created`)*;
  expiry today/tomorrow/3-days/expired, batch recalled, FIFO/FEFO violation
  *(need per-batch expiry dates on inventory — not modelled)*; item
  added/removed/transferred *(StockMovement records these)*; a value/magnitude
  threshold on `inventory.adjustment_flagged` to separate routine waste from a
  suspicious write-off; cycle-count due / full-audit due / accuracy below
  threshold *(need an audit scheduler)*.

### 3. Kitchen
- **LIVE:** new order → KDS (poll), order ready, order cancelled.
- **PLANNED:** rush/VIP/catering/hold/resume order *(need order tags/flags)*;
  cooking started/completed, delayed prep, SLA breach *(need per-ticket timers —
  the KDS tracks status, not elapsed-vs-SLA)*; burnt food / wrong recipe /
  missing·substitute ingredient *(no signal source)*; station overload /
  bottleneck / idle / chef unavailable *(need station-level routing & staffing
  state)*; fridge·freezer·hot-holding temp, HACCP fail, cleaning/sanitization/
  pest-control *(IoT probes + a checklist module — not present)*.

### 4. Customer Orders
- **LIVE:** placed (create), paid, cancelled, ready.
- **PLANNED:** payment pending / confirmed / kitchen accepted·rejected / out for
  delivery / delivered / collected / no-show *(the `OrderStatus` enum is
  PENDING→PREP→READY→SERVED→CANCELLED; the finer delivery/pickup lifecycle isn't
  modelled)*; complaint / refund requested·approved·denied *(support tickets
  exist for staff; a customer complaint/refund flow does not)*; duplicate /
  suspicious / fraud *(need a fraud-scoring signal)*.

### 5. Reservations
- **LIVE:** booked, cancelled, no-show.
- **PLANNED:** modified *(easy add on the status/edit path)*; checked-in / late /
  walk-in seated / table ready / waiting-list / reminder *(need check-in state +
  a reminder scheduler; `ReservationStatus` has no CHECKED_IN)*.

### 6. Tables
- **PLANNED (all):** occupied / free / reserved / cleaning required·completed /
  slow turnover / customer waiting / merged / split *(Table + TableStatus exist,
  but nothing drives live table state — needs a floor/seating workflow)*.

### 7. Delivery (drivers / tracking)
- **PLANNED (all):** every driver-assignment, acceptance, arrival, delay, route,
  GPS-anomaly, wrong-address, failed-delivery event *(needs a driver app +
  GPS/dispatch integration — not part of this system)*.

### 8. Staff
- **LIVE-adjacent:** role changed, deactivated, account locked (security side).
- **PLANNED:** clock in/out, late arrival, early departure, missed shift,
  overtime, break started·exceeded *(need a time-clock/attendance module;
  `shift.started`/`shift.ended` enums were reserved but there's no attendance
  source)*; high-performer / low-productivity / mistakes / compliment /
  complaint / training due / certification expired *(need a performance & HR
  records module)*.

### 9. Finance
- **LIVE-adjacent:** `order.paid`, `mpesa.payment_failed`.
- **PLANNED:** sales target / below-target / hourly-low / record day / revenue
  anomaly *(analytics computes these on demand; turning a threshold-cross into a
  pushed event needs a scheduled evaluator)*; expense added / over budget /
  unexpected / cost spike *(need an expense ledger)*; cash drawer imbalance /
  deposit due / shortage / surplus *(need cash-management + drawer hardware)*;
  failed payment (non-M-Pesa) / large transaction / chargeback *(need a card
  processor webhook)*.

### 10. AI Intelligence
- **LIVE:** `recommendation.generated` ("AI recommendation available"),
  `recommendation.approved`, `agent.failed`.
- **PLANNED:** confidence low / recommendation ignored·accepted / model drift /
  retraining needed *(the `recommendation.*` family is the clean extension
  point; forecast-generated belongs with the §16 BI evaluator)*.

### 11–12. Equipment / Maintenance
- **PLANNED (all):** oven/grill/fridge/freezer/POS-printer/KDS/network/generator/
  UPS status, plus maintenance-due/overdue/completed, repair, technician,
  warranty *(all require equipment telemetry or an asset/maintenance module —
  not present)*.

### 13. Security
- **LIVE:** failed logins → `account.locked`; privilege changes →
  `staff.role_changed`; access revoked/restored → `staff.deactivated` /
  `staff.reactivated`; suspicious inventory movement → `inventory.adjustment_flagged`.
- **REAL trigger, recipient is a policy decision (deliberately not auto-wired):**
  **impersonation started/ended** (`staff.py` audit-logs it; the actor is the
  Owner, so who else is told — a co-owner? the impersonated staff? — is a
  choice); **password reset confirmed** and **MFA disabled** (`auth.py`; the
  actor is the account holder — notifying them is a confirmation-email pattern,
  not an in-app push; owner-oversight routing is undecided). These are the
  honest "one decision away from Tier-A" items.
- **PLANNED (blocked):** raw failed-login-attempt stream *(noise — the lockout
  is the actionable signal)*; new-device login *(no device fingerprinting)*;
  employee deleted data *(no soft-delete audit stream)*; camera offline / door
  forced *(physical-security hardware)*.

### 14. Marketing
- **PLANNED:** promotion started·ended / coupon redeemed·abuse / loyalty
  milestone / birthday reward / review requested·received *(need a
  promotions/loyalty module; note the enum comment in `bus.py` — autonomous
  outbound marketing was intentionally removed pending consent/opt-out/spend
  decisions)*.

### 15. Customer Experience
- **PLANNED:** VIP/frequent/birthday customer arrived / waiting too long /
  complaint unresolved / 5-star·1-star review / negative sentiment *(need a CRM
  + reviews + arrival detection)*.

### 16. Business Intelligence
- **PLANNED:** food·labor cost over target / margin below target / best·worst
  seller changed / menu-engineering update / peak·slow period / demand·weather·
  event forecast *(analytics has the data; each is a scheduled threshold/delta
  evaluator away — the most valuable non-hardware roadmap cluster)*.

### 17. Compliance
- **PLANNED:** license expiring / health inspection due·failed / tax·payroll due
  / document missing *(need a compliance-calendar module)*.

### 18. Multi-Branch
- **PLANNED:** branch offline / out·under-performing / stock-transfer requested /
  cross-branch shortage / staff-transfer *(the tenancy model supports multiple
  restaurants; cross-branch orchestration isn't built)*.

### 19. System
- **PLANNED:** backup completed·failed / API offline·latency / storage full /
  update·deploy succeeded·failed / service restarted / agent unavailable
  *(infra/observability signals — belong in ops monitoring, partially covered by
  `agent.failed`)*.

### 20. Owner Dashboard (digests)
- **PLANNED:** daily·weekly·monthly report ready / KPI exceeded·below / forecast
  changed / cash-flow warning / profit opportunity / risk / expansion rec
  *(`briefing.morning` enum is reserved; these are digest/roll-up events on top
  of §16)*.

### 21. Autonomous agent triggers
Already partially live inside `executive.py` (late supplier → reliability
penalty; no-show → winback; stock-critical → cross-agent reasoning). The rest of
the owner's "event → agent" list becomes real automatically as the underlying
events in §5 graduate to LIVE and gain an `executive.py` handler — the wiring
pattern is identical (§3, step 4).

## 6. Recommended next events (highest value, no new hardware)

The tractable wins where a real trigger and recipient already exist. ✅ = shipped
in the 2026-07-18 pass; the rest remain, roughly in priority order.

1. ✅ **`inventory.adjustment_flagged`** — shipped (§4). Fires on a manual
   downward adjustment; serves §2/§13 "unauthorized adjustment / theft suspected".
2. **BI threshold events (§16)** — a daily scheduled evaluator over existing
   analytics (food-cost over target, margin below target, best-seller changed).
   Recipients: Owner (+ Mgr). The single most valuable **non-hardware** cluster;
   reuses `main.py`'s existing scheduled-job pattern. **Next up.**
3. **`reservation.modified`** — needs a field-edit endpoint on reservations
   (today only status changes exist), then a trivial emit. Closes the §5.5 gap.
   Recipients: Mgr, Supervisor, Waiter.
4. **PO reject/cancel (`purchase_order.rejected` / `.cancelled`)** — needs the
   reject/cancel endpoints §5.1 flags as missing; then emits that mirror
   `purchase_order.approved`. Recipients: approver + receiving tiers.

Beyond these sit the **Tier-B modules** (expenses ledger, loyalty/coupons,
compliance calendar, staff time-clock) and the **Tier-C hardware gateway** (a
signed ingest webhook so external sensors/POS/GPS can *push* the §7/§11/§12
events this software can't originate). Each is a deliberate build, not a
one-line emit — see §2 on why they aren't pre-stubbed as dead enums.
