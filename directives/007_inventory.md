# Directive: Inventory Management

**Goal**: Order-driven stock tracking with AI predictive ordering.

> **Status (2026-08-06):** deduction is now implemented, in `backend/stock_ledger.py`.
> Between the original spec and that date there was **no deduction at all** —
> `InventoryItem.quantity` moved only through the manual `/receive` and
> `/adjust` endpoints. Every downstream number (food cost %, depletion
> prediction, reorder intelligence, "4 hours of chicken left") therefore rested
> on counts a human remembered to type. The implementation diverges from what
> this directive originally specified in two places; both divergences and their
> reasoning are recorded below rather than edited away.

## Inputs
-   Frontend, Backend, Database

## Architecture

### Backend
-   `InventoryItem` — stock levels. `cost_per_unit` is a **Float in whole KES**.
-   `StockMovement` — the append-only ledger of every IN/OUT/ADJUST.
-   `MenuIngredient` — the recipe link (dish → ingredient, `quantity_per_serving`).
-   `stock_ledger.consume_for_order()` / `.restore_for_order()` — deduction and
    its reversal, called from `routers/orders.py`.
-   `GET|PUT|DELETE /menu/{id}/recipe` — recipe CRUD (`routers/menu.py`).
-   `GET /ai/inventory` — depletion prediction and reorder suggestions.

> **⚠ Unit boundary.** `InventoryItem.cost_per_unit` is whole KES.
> `MenuItem.cost_price` is **cents**. `PurchaseOrder.cost_per_unit` is also
> cents — same field name, different unit. Deriving a dish cost therefore needs
> `× 100`. Getting this wrong produces margins wrong by exactly 100×, which is
> the class of error `ai/data_quality.py` exists to catch after the fact.

### Frontend
-   Route: `/dashboard/inventory`. Table view, "AI Insights" depletion widget.
-   **Not yet built:** a recipe editor. The API exists; the UI does not, so
    recipes must currently be created via the API. This is the highest-value
    remaining inventory UI work.

## Divergences from the original spec — read before changing

**1. Deduction happens at ORDER CREATION, not on the KDS bump (Prep → Ready).**

The original spec said `POST /inventory/deduct` would be "called when order is
bumped". It is instead applied when the order is created, inside the same
transaction.

Reasoning: the question an owner asks inventory is *"what can I still sell
tonight?"* A dish committed to a live ticket is already spoken for. Deducting at
bump time would mean that during a rush — exactly when the shortage alert
matters most — twenty in-flight orders' worth of stock still reads as available.
It would also make deduction depend on kitchen staff pressing a button, so any
restaurant that doesn't diligently bump would silently never deduct.

**2. There is no `POST /inventory/deduct` endpoint.**

Deduction is not independently callable. It is a function invoked by order
creation. An endpoint would be a way for stock to drift from sales — the whole
point is that the two cannot disagree. Manual corrections go through
`/inventory/{id}/adjust`, which is what that endpoint is for.

## Design decisions

-   **A sale is NEVER blocked by stock.** Quantities may go negative. Refusing
    to sell food because the software's count disagrees with the shelf is a far
    worse failure than a negative number on a dashboard, and it teaches staff to
    work around the system on their busiest night. A negative quantity is
    information: the opening count was wrong. (This matches the original
    directive's "allow it, flag heavily".)

-   **Dishes without a recipe are skipped silently.** Partial recipe books are
    the expected case — a restaurant maps its expensive, theft-prone and
    fast-moving ingredients and never maps a bottled soda. Partial mapping must
    produce partial (correct) deduction, not an error.

-   **Idempotence lives in `StockMovement.reason`**, tagged `sale:order:<id>` and
    `void:order:<id>`. A retried request, double-tapped cancel or webhook replay
    cannot double-deduct. Chosen over a new column so no migration was needed.

-   **Cancellation writes compensating IN rows; it does not delete the OUT rows.**
    "Taken, then given back" is the auditable history, and it lets analysis
    distinguish a void from a sale that never happened.

-   **`cost_price` is derived from the recipe** (`sync_cost_price`, default on).
    This is the real prize: when a supplier raises chicken 15%, every affected
    dish's margin updates without anyone re-entering anything, and pricing flags
    the dishes that just fell through the margin floor. An empty recipe leaves
    the previous `cost_price` alone rather than zeroing it — a 0 cost reads as
    100% margin and would poison every pricing and profit number for that dish.

-   **Recipe ingredients are tenant-scoped on write.** Without that check, an
    admin could point their recipe at another restaurant's inventory row and
    drain that tenant's stock with their own sales — a cross-tenant write
    through a legitimately-owned object.

## Alerting

Stock alerts are **not** raised by the ledger. They come from
`ai/whatsapp/brain.run_stock_check`, on a 2-hourly cron between 08:00–22:00 EAT,
with a per-item cooldown (`InventoryItem.last_alerted_at`, migration 010) so a
persistently low item doesn't send up to 7 identical messages a day. Keep
deduction free of side effects; alerting is a separate concern with its own
schedule and dedup rules.

## Still open

-   **Recipe editor UI** — the API has no frontend.
-   **Shrinkage detection** — now *possible* but not built. Theoretical usage
    (recipes × orders) exists; what's missing is a physical stock-count endpoint
    to compare it against. Variance between the two is how you find food walking
    out the back. This is the natural next piece.
-   **Waste/spoilage** — `expiry_days` exists on the model and nothing uses it.

## Verification

`backend/tests/test_recipes_and_deduction.py` (15 tests) covers the round trip,
cost derivation and its unit boundary, aggregation of a shared ingredient across
one ticket, the negative-stock path, cancellation, idempotence, tenant scoping
and the public customer-order path.
