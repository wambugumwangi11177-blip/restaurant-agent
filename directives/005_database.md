# Directive: Database Schema & Migration

**Goal**: Define and deploy the initial database schema for the Restaurant Agent.

**Inputs**:
-   Database: Neon (PostgreSQL)

**Tools**:
-   `execution/setup_db.py`

**Schema Design**:
-   **Tenants**: `id`, `name`, `plan`, `created_at`
-   **Users**: `id`, `email`, `hashed_password`, `role` (SuperAdmin, Admin, Staff), `tenant_id`
-   **Restaurants**: `id`, `tenant_id`, `name`, `address`
-   **Menu**: `id`, `restaurant_id`, `name`, `price`, `category`
-   **Orders**: `id`, `restaurant_id`, `status` (Pending, Prep, Ready, Served), `total`
-   **Inventory**: `id`, `restaurant_id`, `item_name`, `quantity`, `unit`, `low_stock_threshold`

**Steps**:
1.  Install `sqlalchemy`, `alembic`, `psycopg2-binary`.
2.  Initialize Alembic: `alembic init alembic`.
3.  Configure `alembic.ini` with `DATABASE_URL` (from env).
4.  Define SQLAlchemy models in `backend/models.py`.
5.  Generate migration: `alembic revision --autogenerate -m "Initial schema"`.
6.  Apply migration: `alembic upgrade head`.

**Edge Cases**:
-   Migration conflicts: Ensure local revisions are impactful.
-   Connection errors: verify `DATABASE_URL` format.
