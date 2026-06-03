# Directive: POS & KDS Implementation

**Goal**: Build the Point of Sale (POS) for waiters and Kitchen Display System (KDS) for chefs.

**Inputs**:
-   Frontend, Backend

**Architecture**:
1.  **POS (Frontend)**:
    -   Route: `/pos` (Tenant protected).
    -   Components: `CategoryTabs`, `MenuGrid`, `OrderCart`.
    -   State: Local storage for cart (offline support), sync on checkout.
2.  **KDS (Frontend)**:
    -   Route: `/kds` (Tenant protected).
    -   Components: `OrderCard`, `Timer`.
    -   Auto-refresh: Polling (every 5s) or Websockets (Pusher/Socket.io).
3.  **Backend**:
    -   `POST /orders`: Create new order.
    -   `GET /orders`: List orders (filter by status).
    -   `PATCH /orders/{id}`: Update status (Prep -> Ready).

**Steps**:
1.  **Backend**:
    -   Implement `Order` CRUD in `routers/orders.py`.
    -   Add status update logic.
2.  **Frontend (POS)**:
    -   Create responsive grid layout.
    -   Implement cart logic (add, remove, total).
    -   Connect "Place Order" button to API.
3.  **Frontend (KDS)**:
    -   Fetch orders with `status != SERVED`.
    -   Display in Kanban-style or Grid.
    -   Add "Bump" button to advance status.

**Edge Cases**:
-   Offline Orders: Queue requests if internet fails (use `react-query` or Service Worker).
-   Race Conditions: Two chefs bumping same order (handle gracefully).
