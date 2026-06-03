# Directive: Inventory Management

**Goal**: Real-time tracking of stock with AI predictive ordering.

**Inputs**:
-   Frontend, Backend, Database

**Architecture**:
1.  **Backend**:
    -   `InventoryItem` model (already defined).
    -   `POST /inventory/deduct`: Called when order is bumped (Prep -> Ready).
    -   `GET /inventory/alerts`: Items below threshold.
    -   AI Service: `POST /ai/predict-stock` -> Returns suggested reorder quantity based on past 30 days history.
2.  **Frontend**:
    -   Route: `/inventory`.
    -   Table view of current stock.
    -   "AI Insights" widget showing predicted depletion.

**Steps**:
1.  **Backend**:
    -   Implement `routers/inventory.py`.
    -   Connect `Order` status change to inventory deduction (via background task or direct call).
2.  **Frontend**:
    -   Build `InventoryTable` with sort/filter.
    -   Add "Reorder" action.

**Edge Cases**:
-   Negative Stock: Allow it (theoretical debt) but flag heavily.
-   Bundle Items: e.g. "Burger Meal" deducts "Bun", "Patty", "Fries". Need `Recipe` model linked to `MenuItem`.
