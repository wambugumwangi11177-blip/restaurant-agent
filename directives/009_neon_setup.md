# Directive: Neon Database Setup

**Goal**: Configure the backend to connect to a Neon PostgreSQL database.

**Inputs**:
-   Neon Connection String (from user).

**Steps**:
1.  **Get Connection String**:
    -   User logs into Neon console.
    -   Creates a project.
    -   Copies the "Pooled connection string" (e.g., `postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require`).
2.  **Update Environment**:
    -   Paste string into `backend/.env` as `DATABASE_URL`.
3.  **Run Migrations**:
    -   Run `python -m alembic upgrade head` to apply schema to the new DB.

**Verification**:
-   Check if tables (`users`, `tenants`, etc.) exist in Neon dashboard.
