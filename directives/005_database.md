# Directive: Database Schema & Migration

**Goal**: Define and deploy the initial database schema for the Restaurant Agent.

**Inputs**:
-   Database: Neon (PostgreSQL)

**Tools**:
-   `execution/setup_db.py` — SQLAlchemy/Alembic setup
-   `execution/deploy_schema.py` — **Step A**: Idempotent DDL deploy + seed (use this)
-   `execution/verify_tools.py` — **Step B**: End-to-end tool verification against Neon
-   `execution/chaos_harness.py` — **Step C**: Adversarial audit (Liar / Race / PII)

**Schema Design** (Step A additions — on top of existing SQLAlchemy-managed tables):
-   **restaurant_tables**: `table_id`, `table_number` (UNIQUE), `capacity`, `zone`, `current_status` CHECK, `last_updated`
-   **menu_items** (pre-existing, different columns): `id`, `restaurant_id`, `name`, `price` (cents), `category`, `is_available`
-   **bookings**: `booking_id` (UUID), `user_id_hash` (NO PII), `table_id` FK, `booking_time`, `party_size`, `status` CHECK, `idempotency_key` UNIQUE, `created_at`

**Steps**:
1.  Install `sqlalchemy`, `alembic`, `psycopg2-binary`.
2.  Initialize Alembic: `alembic init alembic`.
3.  Configure `alembic.ini` with `DATABASE_URL` (from env).
4.  Define SQLAlchemy models in `backend/models.py`.
5.  Generate migration: `alembic revision --autogenerate -m "Initial schema"`.
6.  Apply migration: `alembic upgrade head`.
7.  **Step A**: Run `python execution/deploy_schema.py` to deploy reservation schema + seed.
8.  **Step B**: Run `python execution/verify_tools.py` to verify all tools pass end-to-end.
9.  **Step C**: Run `python execution/chaos_harness.py` to prove the system is non-delusional.

**Edge Cases**:
-   Migration conflicts: Ensure local revisions are impactful.
-   Connection errors: verify `DATABASE_URL` format.
-   **asyncpg SSL**: asyncpg does NOT accept `?sslmode=require` as a URL query param.
    Pass SSL via `connect_args={"ssl": "require"}` to `create_async_engine()` instead.
-   **CREATE TABLE IF NOT EXISTS is a no-op**: If a table already exists (e.g. `menu_items`
    from a prior Alembic migration), the DDL is silently skipped. Always verify actual column
    names against `information_schema.columns` — don't assume the DDL column names landed.
    The `menu_items` table uses `id`/`name`/`price`, not `item_id`/`item_name`/`price_cents`.
-   **Python version mismatch**: On this machine, `pip` installs to Python 3.13 but `python`
    resolves to Python 3.11. Always use the full path:
    `C:\Users\toxic\AppData\Local\Programs\Python\Python313\python.exe`
-   **Dual src/ package conflict (Step C)**: The repo has TWO `src/` directories:
    `restaurant-agent/src/` (top-level services, shield.py) and
    `restaurant-agent/backend/src/` (circuit_breaker, secrets, etc.).
    `llm.py` imports from `backend/src`. Adding BOTH to sys.path causes the wrong one to
    win for `from src.core.circuit_breaker import ...`. Resolution: implement logic inline
    so cross-package imports aren't needed (no relative path hacks).
-   **PII masking — inline regex (Step C)**: Rather than importing `shield.py` from an
    ambiguous location, `orchestrator.py` masks PII inline with a self-contained regex
    at the top of `run()`. Zero-dependency and always works. Masks: Kenyan phones
    (`+254...`), generic E.164 (`+\d{10,15}`), email (`x@y.z`). Runs BEFORE the message
    enters the thought log or the LLM context window.
-   **Race condition testing (Step C)**: Do NOT use `asyncio.gather` on real Groq API calls
    for concurrency tests — the free-tier rate limiter (429) stalls all workers. Use a mock
    LLM with a stateful async function that returns a tool-call on iteration 1 and a final
    answer on iteration 2. Each concurrent worker MUST get its own `AsyncSession` to avoid
    `InvalidRequestError: This session is provisioning a new connection`.
