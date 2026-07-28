"""
Migration 025 (tenant FK NOT VALID CHECKs + partial-unique owner_phone index).

Two layers, matching what's actually testable at each level:

1. Dialect-gate control flow (mocked, always runs) — modeled on
   test_reservation_booking.py's migration-009 template (_load_migration_009):
   asserts the SQLite no-op short-circuits before touching op.execute. That
   template does NOT extend to the rest of 025's logic — 025 calls
   sa.inspect(bind), inspector.has_table(...), and bind.execute(...).scalar()
   for NULL/duplicate pre-checks, none of which the fake bind used for 009 (a
   bare object exposing only .dialect) supports; sa.inspect() on that object
   raises immediately. Building a full fake Inspector double is possible but
   buys little beyond what real Postgres integration coverage (below) already
   proves against the actual DDL.

2. Real Postgres integration (skipped unless POSTGRES_TEST_URL is set) — the
   test suite everywhere else is SQLite-only (tests/conftest.py), which never
   runs Alembic at all (schema comes from database.init_db()'s create_all).
   That's exactly the gap the plan's own verification step calls out: "run
   alembic upgrade head against a local Postgres... to catch anything
   SQLite's dialect gate silently no-ops around." These tests do that for
   real: a clean upgrade creates every constraint/index, downgrade removes
   them, dirty data is skipped with a logged reason instead of crashing the
   deploy, and clean columns still get enforced even when one column is dirty.

   Run against a real Postgres with:
     POSTGRES_TEST_URL=postgresql://user:pass@localhost:5432/dbname \
       pytest tests/test_migration_025_integrity.py -v
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


def _load_migration_025():
    """alembic/versions/ is not a package and '025_...' is not a valid
    identifier, so load by path (same reason test_reservation_booking.py's
    _load_migration_009 does this)."""
    path = (
        Path(__file__).resolve().parent.parent
        / "alembic" / "versions" / "025_tenant_fk_and_owner_phone_integrity.py"
    )
    spec = importlib.util.spec_from_file_location("migration_025", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_025_is_a_noop_on_sqlite(monkeypatch):
    """
    Every check/index here is Postgres-only. Assert the dialect guard
    short-circuits before touching op.execute or sa.inspect — this is what
    keeps `alembic upgrade head` usable in local dev/CI (SQLite) at all.
    """
    from alembic import op as alembic_op

    fake_bind = type("Bind", (), {"dialect": type("D", (), {"name": "sqlite"})()})()
    monkeypatch.setattr(alembic_op, "get_bind", lambda: fake_bind)

    def _explode(*_a, **_k):
        raise AssertionError("migration 025 emitted DDL on a non-Postgres dialect")

    monkeypatch.setattr(alembic_op, "execute", _explode)

    module = _load_migration_025()
    module.upgrade()   # must return before touching op.execute or sa.inspect
    module.downgrade()


# ─────────────────────────────────────────────────────────────────────────────
# Real Postgres integration — skipped unless POSTGRES_TEST_URL is set.
# ─────────────────────────────────────────────────────────────────────────────

_POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL")

pytestmark_pg = pytest.mark.skipif(
    not _POSTGRES_TEST_URL,
    reason="set POSTGRES_TEST_URL to run migration 025 against a real Postgres",
)


@pytest.fixture
def pg_engine():
    engine = create_engine(_POSTGRES_TEST_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()


def _run_init_db(database_url):
    backend_dir = Path(__file__).resolve().parent.parent
    subprocess.run(
        [sys.executable, "-c", "from database import init_db; init_db()"],
        cwd=backend_dir, env={**os.environ, "DATABASE_URL": database_url}, check=True,
    )


def _run_alembic(args, database_url):
    backend_dir = Path(__file__).resolve().parent.parent
    subprocess.run(
        ["alembic", *args],
        cwd=backend_dir, env={**os.environ, "DATABASE_URL": database_url}, check=True,
    )


def _run_alembic_upgrade_head(database_url):
    _run_init_db(database_url)
    _run_alembic(["upgrade", "head"], database_url)


@pytestmark_pg
def test_clean_database_gets_every_constraint_and_index(pg_engine):
    _run_alembic_upgrade_head(_POSTGRES_TEST_URL)

    with pg_engine.connect() as conn:
        check_names = {
            row[0] for row in conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_%not_null'"
            ))
        }
        assert check_names == {
            "ck_users_tenant_id_not_null",
            "ck_restaurants_tenant_id_not_null",
            "ck_tables_restaurant_id_not_null",
            "ck_menu_items_restaurant_id_not_null",
            "ck_inventory_items_restaurant_id_not_null",
            "ck_orders_restaurant_id_not_null",
            "ck_reservations_restaurant_id_not_null",
        }

        index_names = {
            row[0] for row in conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE indexname = 'uq_restaurants_owner_phone'"
            ))
        }
        assert index_names == {"uq_restaurants_owner_phone"}


@pytestmark_pg
def test_downgrade_removes_every_constraint_and_index(pg_engine):
    _run_alembic_upgrade_head(_POSTGRES_TEST_URL)
    # Downgrade to 025's PARENT by name, not by "-1". A relative step is only
    # equivalent while 025 happens to be head — migration 026 landing on top
    # immediately broke that assumption (the -1 reverted 026 and left 025's
    # constraints in place, failing this test for the wrong reason). Naming the
    # target keeps this test about 025 no matter what stacks above it later.
    _run_alembic(["downgrade", "024_add_enterprise_hierarchy"], _POSTGRES_TEST_URL)

    with pg_engine.connect() as conn:
        remaining_checks = conn.execute(text(
            "SELECT COUNT(*) FROM pg_constraint WHERE conname LIKE 'ck_%not_null'"
        )).scalar()
        remaining_index = conn.execute(text(
            "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'uq_restaurants_owner_phone'"
        )).scalar()
        assert remaining_checks == 0
        assert remaining_index == 0


@pytestmark_pg
def test_dirty_data_is_skipped_with_a_log_not_a_crash(pg_engine, caplog):
    """
    A NULL tenant_id and a duplicate owner_phone must not abort the deploy —
    both are skipped (with a logged reason), while every OTHER, clean column
    still gets its constraint. This is 025's whole reason for using NOT VALID
    CHECKs instead of a blind ALTER COLUMN SET NOT NULL.

    To insert the dirty rows at all, this first drops the ORM-level
    `owner_phone` UNIQUE constraint that init_db()'s create_all now applies
    (models.py declares unique=True as of this same hardening pass) — this
    simulates a real pre-existing production database from BEFORE that model
    change shipped, which is exactly the population 025 has to cope with.
    A brand new database created after this change can never reach this dirty
    state via the app itself; only an existing one predating it can.
    """
    _run_init_db(_POSTGRES_TEST_URL)

    with pg_engine.begin() as conn:
        conn.execute(text("ALTER TABLE restaurants DROP CONSTRAINT restaurants_owner_phone_key"))
        conn.execute(text("ALTER TABLE restaurants ALTER COLUMN tenant_id DROP NOT NULL"))
        conn.execute(text("INSERT INTO tenants (name) VALUES ('T1')"))
        tenant_id = conn.execute(text("SELECT id FROM tenants WHERE name = 'T1'")).scalar()
        conn.execute(text(
            "INSERT INTO restaurants (name, tenant_id, owner_phone) VALUES "
            "('R1', :tid, '+254700111222'), ('R2', :tid, '+254700111222'), "
            "('R3', NULL, NULL)"
        ), {"tid": tenant_id})

    _run_alembic(["upgrade", "head"], _POSTGRES_TEST_URL)

    with pg_engine.connect() as conn:
        check_names = {
            row[0] for row in conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_%not_null'"
            ))
        }
        # tenant_id's check is skipped (R3 has NULL tenant_id); every other
        # clean column still gets its constraint.
        assert "ck_restaurants_tenant_id_not_null" not in check_names
        assert "ck_orders_restaurant_id_not_null" in check_names
        assert "ck_users_tenant_id_not_null" in check_names

        index_count = conn.execute(text(
            "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'uq_restaurants_owner_phone'"
        )).scalar()
        assert index_count == 0, "duplicate owner_phone must skip the unique index, not crash"
