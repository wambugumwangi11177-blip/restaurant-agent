# Eleven daily experience — implementation matrix

Local implementation on `codex/eleven-demo-readiness`, 25 October 2026. This supersedes the earlier stock-only remaining-work list. The original working tree was preserved. Custody is already in the branch ancestry; no blanket branch merge was made. PIN switching reuses the current authenticated quick-switch flow. Context7 was consulted for Next.js URL state and navigation, not operating policy.

`O` = owner/admin; `A` = accountant (existing `controller` identifier); `S` = stockkeeper; `C` = chef (`kitchen`); `W` = waiter; `M` = manager. API paths below have the `/api/v1` prefix; existing legacy aliases remain mounted. Staff use their own role shell, not the owner dashboard.

| Feature and route | Backend source / contract | Roles | Result and input requirements |
|---|---|---|---|
| One Home `/home`; legacy `/demo`, `/vibanda` | `owner/home`, overview, shared report engines | O | Compact recorded sales/cash/result, three ranked concerns, team tasks and coming up. Full health/area analysis remains in disclosure panels. Different periods labelled. |
| Daily work `/daily`, `/staff/{role}` | `daily/tasks`, `daily/team`, `daily/close/{day}` | O/A/M; own tasks S/C/W | Actual identity, branch, pending/disputed handovers, assigned counts, review status and freshness. Role landing pages have direct main-task links; old modules remain available. |
| Food cost `/areas/money?tool=food-cost` | `owner/area/money`, `cost_dials`, `compute_pnl` | O | One ingredient-cost/sales definition, last 30 calendar days. Missing recipe costs suppress the ratio. |
| Wages `?tool=wages`; prime cost `?tool=prime-cost` | Same P&L engine and dates as food cost | O | Separate views. Shift-based wage estimate identified; missing wage input stays unknown. Prime cost requires matching food/wage/sales basis. |
| P&L, break-even, bills, forecast and delivery economics | Existing Money and Sales area blocks, `owner/money/*` | O | Individual tool bodies and assumptions; legacy combined overview retained. Bills use paid expense records; break-even is a reference-cost estimate. |
| Stock review `/planning?tool=stock-review` | `owner/planning/stock-review` | O | Attention/tasks/all tabs, search and five-item pages; URL persists tab/search/page/item. Valuation, count calendar and supplier details are deliberate drill-downs. |
| Item detail and location count/waste; staff `/staff/stockkeeper/records`, `/staff/controller/records` | `daily/stock/{id}`, `/evidence` | O/A/S/M write; C read | Audited store/kitchen/in-transit/unallocated balances. Structured reason, visible unit, actor/capture time, optional private photo. Retry-safe; stale count rejected after global **or location** movement. |
| Raw stock `/inventory`, staff old stock module | Existing inventory APIs | Existing permissions | Preserved administration and full lists. Internal transfers excluded from purchasing/consumption analytics. Recorded waste excluded from unexplained usage. |
| Delivery receiving `/entries`, `/purchasing` | `owner/operations/deliveries/{id}/receive`, shared `ai/reorder.py` | O/A/S/M | One atomic whole-stock movement + store event + optional-expiry receipt batch. Purchase ID provides retry identity. Historical delivered orders without evidence are not assigned a location on retry. |
| Store → kitchen `/kitchen-stock`, staff receiving | `stock/transfers`, `/request`, `/{id}/fulfill`, `/{id}/confirm`, shared custody service | O/A/S/M send/receive; C receive | Sender cannot confirm own handover through HTTP or WhatsApp's shared service. Dispatch goes in transit; actual arrival enters kitchen. Short receipt remains disputed/in transit. Optional arrival photo. |
| Recipes `/staff/kitchen/recipes`, owner planning | `menu/{id}/ingredients`, shared `ai/order_stock.py` | C recipe maintenance; O/M existing admin | Yield-aware consumption once per order-line ingredient; immutable retry key. Negative kitchen balances flag missing records without blocking sale or borrowing silently. Reversal uses original deduction quantity. |
| Sales/menu `/areas/sales`, `/menu` | Shared sales/trend/menu engines | O; W existing POS; C recipe/menu read | Trends and dish decisions first; pricing, combos, demand simulation and delivery economics remain distinct. Unknown costs cannot produce an invented margin. |
| Forecast → portions → ingredients → buying | `owner/planning/forecast`, prep/market-list and purchase-draft APIs | O/M as already allowed | Step labels, searchable five-dish preview, full editable proposals retained; hidden pages still included in the plan. Drafting does not approve or notify a supplier. |
| Manual sales `/staff/waiter/pos` | Existing authenticated order APIs | W/O/M | Manual entry independent of a POS connector; daily landing links directly to it. Original order/kitchen/booking routes retained. |
| Assigned blind cash count | `daily/close/{day}/assign`, `daily/cash-count`, shared cash reconciliation | O/A/M assign; assigned person submit | Exact branch/person/drawer window, expected value hidden from response. Overlapping restaurant-drawer assignments rejected; windows are not falsely treated as per-waiter sales allocations. |
| Close review | `daily/close/{day}/review`, `DailyShiftClose` | O/A/M review; O exception close | Open → ready for review → closed or closed with exceptions; version-checked, persistent snapshot/history. Required item counts, negative location balances/in-transit stock, independent handovers, cash gaps and incomplete M-Pesa coverage block a clean close. |
| Closed-day corrections | Existing corrections plus shared ORM invalidation | Existing write permissions | Original journal remains; relevant changed evidence reopens reviewed days. Date changes invalidate original and corrected day. No silent signed-off rewrite. |
| Accounting `/entries`, `/reports` | Expense/receipt APIs; `owner/report/{period}`; accountant export | O/A/M according to endpoint | Summary first; detailed ledger/receipts/export on request. PDF reports use the same report payload, integer cents preserved in accounting/export. |
| Ask `/os` | `owner/ask`, existing deterministic engines | O | Greeting returns greeting; short ambiguous operational question asks for context. Source figures/actions retained for supported questions. |
| Alerts `/alerts` | Existing tenant-scoped alerts | O in owner shell | Unread/history, URL search/pages; reading does not falsely claim business resolution. Staff notification access remains role-scoped. |
| Settings/team `/settings`, `/team` | Owner settings/history, staff management, daily team/tasks | O; assigned staff own task view | Settings grouped by purpose; responsibilities and daily-work link first, full team administration retained. `controller` displayed as Accountant. |
| Legacy links and filters | `useToolSelection`, `useListQuery` | All authorized routes | One `?tool=` selector; old raw/encoded stacked fragments recovered. Search and pagination preserve other query state, reload and Back. Invalid tool is explicit. |
| Shared-device personal identity | Existing `auth/quick-switch` and PIN modals | Existing branch-linked staff | Current personal PIN implementation reused. PIN/photo are identity/evidence aids, not proof a quantity is correct. |

## Record contract

Legacy staff modules are retained behind “More tools” or the landing page's full-workspace disclosure. The existing domain matrix remains separate from the new explicit stock send/receive/location-record capabilities:

| Retained module and route pattern | Existing API family | Eleven staff access |
|---|---|---|
| Orders `/staff/{role}/orders` | `/orders` | W write; A/C read |
| Kitchen orders `/staff/kitchen/orders`, `/staff/waiter/kitchen` | `/orders`, kitchen status services | C work queue; W read |
| Menu `/staff/{role}/menu` | `/menu` | W/C read; C recipe ingredients write through the explicit recipe route |
| Reservations `/staff/waiter/reservations` | `/reservations` | W write |
| Sales `/staff/controller/sales` | `/sales`, reporting | A read |
| Purchasing `/staff/{role}/purchasing` | `/purchasing` | S purchase workflow; A existing read plus dedicated delivery receiving |
| ROI, AI and AI operations `/staff/controller/{roi,ai,ai-ops}` | Existing `/ai/*` readers | A read; retained optional analysis |
| Support `/staff/{role}/support` | Existing support services | W/S/A/C existing support view |

These retained modules do not replace the new daily landing or grant general financial/menu administration. Owner raw administration remains available from its canonical owner entry paths.

Migration `059_eleven_daily` adds `stock_zone_events`, `stock_receipt_batches` and `daily_shift_closes`. No historical location is guessed: unallocated is the residual between the original whole-item book quantity and explicitly recorded zones. New receipt/deduction/waste paths update the existing whole-item source and zone evidence together. A transfer does not change total on hand. A short receipt leaves the unresolved quantity in transit. Negative store/kitchen or residual quantities are visible recording exceptions, not automatic theft findings.

Writes require authenticated actors and current branch checks. Zone evidence retains the original request and retry key. Existing entry journals, offline queues and audited reversals remain intact. New zone evidence requires an online submission; it is not advertised as an offline queue. The UI retains its request key, capture timestamp and uploaded photo reference on retry. Day-review versions and unique drawer windows prevent duplicate sign-off/assignment effects.

## Remaining limits

- Receipt batches retain received quantities and optional dates; they are **not** remaining-lot balances or FIFO consumption. An old receipt date says to check whether that lot remains, never that all its original quantity is still on hand. Historical expiry is unknown.
- A clean close is evidence completeness, not proof the physical count is accurate. It requires each tracked item to have a whole-item count or both store/kitchen counts. The current drawer is restaurant-wide; multiple physical drawers need a future drawer identifier and allocations.
- M-Pesa day close remains conservative when statement coverage does not span the day. Unexplained statement receipts block a clean close even without a recorded M-Pesa sale. Client export formats and coverage semantics need actual samples.
- Discrepancies can be reviewed and closed with an owner-authorised exception; this does not erase a disputed transfer or resolve its quantity. Corrections preserve original evidence.
- Live POS/provider compatibility, push/SMTP delivery and consent-reviewed win-back sending remain dependent on client samples/configuration and separate authorization. No deployment, production writes, supplier approval or external message was made.
- Existing raw administration screens remain available for detailed work and retain some older presentation. The lint baseline is not clean; new findings are prevented by the ratchet.
- New per-item detail currently shows the latest 50 location events, 30 global movements and 30 receipt batches. Dedicated searching/paging through older item-detail records remains an implementation gap; these bounded previews are not labelled as a complete historical export.

Verification and reproducible scenario evidence are recorded in `ELEVEN_DAILY_ACCEPTANCE.md` and `PROGRESS.md`.
