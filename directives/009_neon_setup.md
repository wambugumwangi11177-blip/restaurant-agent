# Directive: Database Setup (Railway Postgres)

> **Superseded 2026-09-19.** This file used to describe Neon. Production has
> run on **Railway Postgres** since the Railway migration; anyone following
> the old version provisioned the wrong database and pointed `DATABASE_URL`
> somewhere the app does not live. The Neon steps are kept at the bottom for
> anyone reading an old commit, clearly marked as historical.

**Goal**: Point the backend at its PostgreSQL database.

**Inputs**:
-   The Railway project (backend service + Postgres plugin in the same project).

**Steps**:

1.  **Get the connection string**
    -   Railway dashboard → the Postgres service → *Variables* → `DATABASE_URL`.
    -   Inside the same Railway project, reference it as
        `${{Postgres.DATABASE_URL}}` on the backend service rather than pasting
        the literal — the value rotates, and a pasted copy goes stale silently.
2.  **Local development**
    -   Put a connection string in `backend/.env` as `DATABASE_URL`.
    -   Local work should NOT point at production. `backend/dev_snapshot.py`
        copies production into a local SQLite file for fast, safe local
        queries; `execution/_guard.py` exists because several scripts run
        destructive statements against whatever `DATABASE_URL` is configured.
3.  **Migrations**
    -   The Dockerfile runs `alembic upgrade head` on every boot, so a deploy
        migrates itself. Nothing manual is needed in normal operation.
    -   By hand: `python -m alembic upgrade head` from `backend/`.
    -   The chain is linear — one head, no branches. Check with
        `python -m alembic heads`; more than one means two migrations claim
        the same parent and the next deploy will fail.

**Verification**:
-   `GET /health/db` returns ok against the running service.
-   `python -m alembic current` matches `python -m alembic heads`.

**Backups**: `backend/scripts/backup/` dumps nightly to a Railway bucket.
`.github/workflows/backup.yml` is an off-provider S3 copy, off until its
secrets exist. `.github/workflows/restore-drill.yml` proves a dump can be
restored — until that has passed once, the backups are configured, not proven.
See `backend/DISASTER_RECOVERY.md`.

---

## Historical: Neon setup (no longer used)

Kept so an old commit or runbook reference still resolves. Do not follow this
for a new environment.

1.  User logs into the Neon console, creates a project, copies the *pooled*
    connection string (`postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require`).
2.  Paste into `backend/.env` as `DATABASE_URL`.
3.  `python -m alembic upgrade head`.
4.  Verify the tables exist in the Neon dashboard.
