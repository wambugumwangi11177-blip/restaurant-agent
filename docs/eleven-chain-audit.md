# Eleven chain audit (`feat/jack-storekeeper` @ c4d235d+)

Status key: **Connected** = production path on a screen or scheduler; **Partial** = called but missing data/UI; **Dead** = no runtime caller.

| Engine / surface | Files | Called? | Data needed | Screen | Gap (before this batch) |
|---|---|---|---|---|---|
| **Pricing intelligence** | `ai/pricing/analysis.py`, `recommendations.py` | Partial — `ai_ask`, WhatsApp, `decisions/adapters`, tests only | MenuItem prices, velocities, ingredient costs | Ask / hidden specialists | No owner **Dishes** or **Money** surface |
| **Menu engineering** | `ai/menu_engineer.py` | Partial — `ai_ask`, adapters, marketing | Orders, MenuItem.`cost_price` (often stale) | — | Margins used hand-typed cost, not recipes |
| **Profit / P&L** | `ai/profit/intelligence.py` | Partial — `ai_ask`, `home_specialists`, ROI | Orders, MenuItem costs, bills | `/eleven/money` (feed cards only) | P&L not on Money page; cost from `cost_price` not recipes |
| **Supply chain** | `ai/supply_chain/intelligence.py` | Partial — `reorder.draft_purchase_order` notes reliability | Supplier history, deliveries | — | No supplier insight page |
| **Inventory predictor** | `ai/inventory_predictor.py` | Partial — workflows, Ask, plugins | StockMovement history | — | Predictions not driving par/reorder on items |
| **Reorder / PO** | `ai/reorder.py`, `main._run_reorder_check_job` | Partial — daily job drafts PENDING POs | `par_level`, `default_supplier_id`, `low_stock_threshold` | Owner approvals `restock` | No routing from questionnaire; no storekeeper WhatsApp flow |
| **Stock custody / plates** | `ai/stock_custody.py`, `main._run_variance_check_job` | Partial — scheduler emits events; WhatsApp | OrderItem lines, recipes, StockMovement OUT | — | No dish lines from POS yet; no owner UI |
| **Order stock deduction** | `ai/order_stock.py` | **Connected** — `integration/quicksell.py` when sale `lines` present | Orders with OrderItem + MenuIngredient | Plates / custody | Totals-only POS sales still have no lines |
| **Store recipes** | `routers/store_recipes.py`, `/store/recipes` | **Connected** | MenuIngredient rows | Store recipes | No computed dish cost |
| **Deliveries / invoice photos** | `routers/store_intake.py`, store_vision | **Connected** | DeliveryReceipt photos | `/store/deliveries`, `/store/invoice-prices` | Owner deliveries duplicates accountant path |
| **Handovers** | `routers/store_control.py` | **Connected** | KitchenHandover + photo | Approvals, store issue | No owner timeline view |
| **Staff setup / questions** | `staff_setup.py`, `config/storekeeper-questions.json` | **Connected** | StaffSetupAnswer | `/store/questions` | No ordering rule → tables; questionnaire not gate before store |
| **Team / schedule** | `routers/team.py` | **Connected** | StaffWeeklyShift | `/eleven/team`, `/store/team` | — |
| **Overview / home** | `routers/overview.py`, OwnerFeed | **Connected** | Mixed | `/eleven`, `/store` | Jack home still shows delivery explainer after setup |

## Connections added in this batch

1. **Questionnaire gate** — floor managers must finish questions (including ordering rule) before store APIs; answers persist to `Restaurant.restock_routing_mode` and item par/supplier fields.
2. **`services/dish_cost.py`** — recipe × ingredient cost drives margins; profit and menu engineering read effective cost.
3. **`services/reorder_points.py`** — reorder point = daily usage × lead days + safety; syncs `low_stock_threshold` / `par_level`.
4. **`routers/store_restock.py`** — restock queue, WhatsApp draft, mark ordered; approval notifies requester (`ordered_by_user_id`).
5. **`routers/eleven_dishes.py`** + **`/eleven/dishes`** — cost, price, margin, plate status.
6. **`routers/eleven_money.py`** — P&L snippet from profit intelligence on Money page.
7. **`routers/eleven_plates.py`** — plate expected vs sold (or “Waiting on POS dish lines”).
8. **`routers/store_prep.py`** — prep suggestions on handover/issue flow.
9. **POS hook** — `integration/quicksell.py` calls `deduct_ingredients_for_order` when line items exist on ingest.
10. **Demo seed** — recipes, par levels, sample orders with dish lines for test stack.

## Still blocked on real data

- **POS dish lines** — QuickSell webhook today inserts order totals only; plate variance and full custody need line mapping (UI shows waiting state).
- **Till revenue on Money** — live P&L needs paid orders; seed provides demo orders on test only.
- **WhatsApp send** — order draft link is always shown; outbound WhatsApp/SMS still depends on configured supplier phone + Twilio.