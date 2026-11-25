# Engine triggers (LEVIII)

Branch: `feat/jack-storekeeper`. This table records **what starts each engine**, what it writes, which UI surfaces it, and whether it runs automatically on real entry points (no manual scripts/cron-only).

| Engine | Trigger (event / entry point) | Writes / emits | Screen | Auto? |
|---|---|---|---|---|
| Recipe deduction (`ai/order_stock.py`) | QuickSell webhook maps sale → `Order` + dish lines | `InventoryItem.quantity`, `StockMovement` OUT | Store stock, Owner stock | **Yes** — `integration/quicksell.py` on each mapped sale |
| POS order events | Same sale commit | `order.created`, `order.paid` NOTIFY | Push / notifications | **Yes** — `services/engine_triggers.after_pos_sale` after webhook commit |
| Par / reorder draft (`ai/reorder.py`) | Stock touch: sale deduct, delivery IN, handover OUT, day close | `PurchaseOrder` PENDING, `purchase_order.created` | Owner Approvals / Alerts restock cards | **Yes** on events + **06:00 EAT** cron backstop (`main.py`) |
| Reorder points (`services/reorder_points.py`) | Before draft on any `after_inventory_touch` | `low_stock_threshold`, `par_level` on items | Store stock meta (internal) | **Yes** — synced on each inventory touch |
| Low / critical stock | Item qty ≤ threshold after touch | `stock.low` / `stock.critical` | Alerts (via notifier) | **Yes** — `engine_triggers._emit_low_stock_events` |
| Stock custody / variance (`ai/stock_custody.py`) | Handover, day close, POS+movement window; daily job | `stock.variance_flagged` when flagged | Owner home specialists / custody (no dedicated Eleven page) | **Partial** — auto on handover/close/sales; **21:00 EAT** cron for catch-up |
| Dish cost rollup (`services/dish_cost.py`) | Accountant confirms delivery invoice prices | `MenuItem.cost_price` (cents) from recipe × unit cost | Owner Dishes / profit math | **Yes** — `after_prices_confirmed` |
| Stock received signal | Jack keys delivery receive | `stock.received` | Owner deliveries feed | **Yes** — `after_delivery_received` |
| Restock approval notify | Owner approves PO on `/store/approvals` | `purchase_order.approved` | Jack restock, notifications | **Yes** — `after_restock_decision` |
| Inventory predictor (`ai/inventory_predictor.py`) | On demand (Ask OS, specialists) | Read-only JSON | `/eleven/ask` | **On read** — needs movement history |
| Menu engineering (`ai/menu_engineer.py`) | On demand (Ask OS) | Read-only | `/eleven/ask` | **On read** — needs paid orders + `cost_price` |
| Revenue forecast (`ai/revenue_forecaster.py`) | On demand + learning cron 05:00 EAT | Forecast rows | `/eleven/ask` | **On read** + scheduled learning |
| Profit / food P&L (`ai/profit/intelligence.py`) | On demand; Money P&L endpoint (falls back to paid orders last 30d when rollup empty) | Read-only rollups | `/eleven/money` (bills wired); Ask | **On read** — UI cache-busts on navigation so new QuickSell sales show on next visit |
| Prep list (`services/prep_suggest.py`) | On demand GET `/store/prep` | Read-only from handover history | Store prep | **On read** — cache-bust on page load after handovers |
| Supplier price change | Invoice price confirm on lines | `InventoryItem.cost_per_unit` | Store invoice-prices, accountant flow | **Yes** (manual keying is the real entry point) |
| Approval reminders (`services/approval_workflow.py`) | Pending approvals feed load | Reminder rows, notifications | Owner Home / Approvals / Alerts | **Yes** — `process_due_reminders` on feed GET |
| Store vision (`store_vision.py`) | Photo on delivery / handover / stock | Vision check rows | Store screens | **Yes** — background task after photo POST |
| Eleven rules cards (`services/eleven_rules.py`) | Owner outcomes / home load | Rule cards JSON | Owner home | **On read** |
| Fraud scan (`ai/fraud/detection.py`) | Cron every 2h | Events when patterns found | No Eleven page | **Cron only** |
| Cash reconciliation | Needs drawer count submission | Read-only report | **Blocked** — no drawer count UI on Eleven |
| WhatsApp stock / briefings | Cron when Twilio configured | Outbound messages | N/A | **Cron** — **blocked** without WhatsApp creds |
| Ask OS (`routers/ai_ask.py`) | Owner POST `/api/v1/ai/chat` | Chat card | `/eleven/ask` | **On demand** — routes to engines above |

## Entry-point map (audit flow)

1. **QuickSell** `POST /webhooks/quicksell/data` → mirror, order, deduct, events, reorder draft, variance if applicable.
2. **Jack** questionnaire / suppliers / delivery+photos / stock count / handover+PIN / low stock (via movement) / day close → inventory touch + variance on handover & close.
3. **Accountant** `POST …/deliveries/{id}/prices` → unit costs + dish `cost_price` sync.
4. **Owner** `POST /api/v1/store/approvals` `kind=restock` → `purchase_order.approved`.

## Tests

- `backend/tests/test_engine_triggers.py` — POS events, auto PO draft, dish cost sync.
- `backend/tests/test_quicksell_webhook.py` — webhook auth, dish lines, deduction.
- `backend/tests/test_quicksell_empty_binding.py` — `X-Leviii-Pos-Binding: quicksell-empty` routes to empty stack; Money P&L reflects sale on next GET.
- `frontend/e2e/ui-broken-sweep.spec.ts` — Playwright sweep (owner / Jack / accountant × empty + data); `npm run test:ui-sweep` against Railway test.
- Scheduler jobs in `main.py` remain as production backstops.

## Still blocked on data

| Blocker | Engines affected |
|---|---|
| No drawer count capture | Cash reconciliation |
| No supplier phone | PO SMS after approve/send |
| No WhatsApp/Twilio | Scheduled briefings, supplier SMS fallback only where phone exists |
| Fraud / strategist / learning | Need mature order history; screens not wired |