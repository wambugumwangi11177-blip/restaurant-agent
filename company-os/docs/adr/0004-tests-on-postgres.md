# ADR 0004 — Tests run on real PostgreSQL, never SQLite

**Status:** Accepted, 2026-09-26

## Context
Restaurant-agent's suite runs on SQLite, which cannot exercise full-text search, JSONB, triggers, `FOR UPDATE` locks or the exact constraint behaviour production has.

## Decision
- Each test session creates a throwaway database, migrates it with Alembic (so the migration is under test too), and truncates all tables between tests.
- `tests/conftest.py` refuses any database host other than localhost or the CI service container.
- CI runs a `postgres:16` service container.

## Consequences
- Running tests locally needs Postgres. `dev.sh` and the README cover this.
- The suite takes about 20 seconds instead of 5.
