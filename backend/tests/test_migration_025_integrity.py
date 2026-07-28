"""
Control-flow tests for alembic/versions/025_add_tenant_not_null_and_owner_phone_unique.py,
same style as test_reservation_booking.py's migration-009 tests: no local Postgres
in CI, so these pin the DDL sequence/control-flow against a mocked bind+inspector
rather than a real server. The actual DDL was hand-verified against a real local
Postgres 16 instance during development (upgrade head, re-run no-op, downgrade,
re-upgrade, and both skip-on-dirty-data paths — orders.restaurant_id with an
existing NULL row, and a duplicate owner_phone) — this file guards against a
future edit silently breaking that control flow.
"""
import importlib.util
from pathlib import Path

import pytest


def _load_migration_025():
    path = (
        Path(__file__).resolve().parent.parent
        / "alembic" / "versions" / "025_add_tenant_not_null_and_owner_phone_unique.py"
    )
    spec = importlib.util.spec_from_file_location("migration_025", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeInspector:
    """Minimal sa.inspect() stand-in. `columns` maps table -> {col: nullable}.
    `checks`/`uniques` map table -> set of existing constraint names."""

    def __init__(self, columns, checks=None, uniques=None, tables=None):
        self._columns = columns
        self._checks = checks or {}
        self._uniques = uniques or {}
        self._tables = tables if tables is not None else set(columns.keys())

    def has_table(self, table):
        return table in self._tables

    def get_columns(self, table):
        return [{"name": c, "nullable": n} for c, n in self._columns.get(table, {}).items()]

    def get_check_constraints(self, table):
        return [{"name": n} for n in self._checks.get(table, set())]

    def get_unique_constraints(self, table):
        return [{"name": n} for n in self._uniques.get(table, set())]


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


def _all_clean_columns():
    """All 5 target columns nullable=True (needs fixing), no existing constraints."""
    return {
        "orders": {"restaurant_id": True},
        "reservations": {"restaurant_id": True},
        "menu_items": {"restaurant_id": True},
        "tables": {"restaurant_id": True},
        "inventory_items": {"restaurant_id": True},
        "restaurants": {"tenant_id": True, "owner_phone": True},
    }


def test_no_op_on_sqlite(monkeypatch):
    from alembic import op as alembic_op

    fake_bind = type("Bind", (), {"dialect": type("D", (), {"name": "sqlite"})()})()
    monkeypatch.setattr(alembic_op, "get_bind", lambda: fake_bind)

    def _explode(*_a, **_k):
        raise AssertionError("migration 025 emitted DDL on a non-Postgres dialect")

    monkeypatch.setattr(alembic_op, "execute", _explode)

    module = _load_migration_025()
    module.upgrade()
    module.downgrade()


def test_scope_excludes_tenant_id_columns():
    """restaurants.tenant_id / users.tenant_id must never be in the NOT NULL
    list — that's the deliberate scope-narrowing this migration documents."""
    module = _load_migration_025()
    targeted_tables = {t for t, _ in module._NOT_NULL_COLUMNS}
    assert "restaurants" not in targeted_tables or ("restaurants", "tenant_id") not in module._NOT_NULL_COLUMNS
    assert ("users", "tenant_id") not in module._NOT_NULL_COLUMNS
    assert len(module._NOT_NULL_COLUMNS) == 5


def test_clean_data_gets_not_null_and_unique_applied(monkeypatch):
    from alembic import op as alembic_op
    import sqlalchemy as sa

    fake_bind = type("Bind", (), {
        "dialect": type("D", (), {"name": "postgresql"})(),
        "execute": lambda self, *a, **k: _FakeResult(0),  # zero NULLs, zero dupes
    })()
    monkeypatch.setattr(alembic_op, "get_bind", lambda: fake_bind)
    monkeypatch.setattr(sa, "inspect", lambda _bind: _FakeInspector(_all_clean_columns()))

    statements = []
    monkeypatch.setattr(alembic_op, "execute", lambda sql, *a, **k: statements.append(str(sql)))

    module = _load_migration_025()
    module.upgrade()

    joined = " ".join(statements)
    # Each of the 5 columns goes through CHECK NOT VALID -> VALIDATE -> SET NOT NULL -> DROP
    assert joined.count("CHECK (") == 5
    assert joined.count("NOT VALID") == 5
    assert joined.count("VALIDATE CONSTRAINT") == 5
    assert joined.count("SET NOT NULL") == 5
    assert joined.count("DROP CONSTRAINT") == 5
    assert "ADD CONSTRAINT uq_restaurants_owner_phone UNIQUE" in joined


def test_column_with_existing_null_is_skipped_not_failed(monkeypatch, caplog):
    from alembic import op as alembic_op
    import sqlalchemy as sa

    def fake_execute(self, sql, *a, **k):
        # orders.restaurant_id has 1 existing NULL row; everything else clean.
        if "orders" in str(sql) and "IS NULL" in str(sql):
            return _FakeResult(1)
        return _FakeResult(0)

    fake_bind = type("Bind", (), {
        "dialect": type("D", (), {"name": "postgresql"})(),
        "execute": fake_execute,
    })()
    monkeypatch.setattr(alembic_op, "get_bind", lambda: fake_bind)
    monkeypatch.setattr(sa, "inspect", lambda _bind: _FakeInspector(_all_clean_columns()))

    statements = []
    monkeypatch.setattr(alembic_op, "execute", lambda sql, *a, **k: statements.append(str(sql)))

    module = _load_migration_025()
    with caplog.at_level("WARNING"):
        module.upgrade()  # must not raise

    joined = " ".join(statements)
    assert "orders" not in joined.split("ADD CONSTRAINT")[0] or "ck_orders_restaurant_id_not_null" not in joined
    # The other 4 clean columns still get fixed:
    assert joined.count("SET NOT NULL") == 4
    assert any("Skipping NOT NULL on orders.restaurant_id" in r.message for r in caplog.records)


def test_duplicate_owner_phone_is_skipped_not_failed(monkeypatch, caplog):
    from alembic import op as alembic_op
    import sqlalchemy as sa

    def fake_execute(self, sql, *a, **k):
        if "owner_phone" in str(sql) and "GROUP BY" in str(sql):
            return _FakeResult(1)  # 1 duplicate group
        return _FakeResult(0)

    fake_bind = type("Bind", (), {
        "dialect": type("D", (), {"name": "postgresql"})(),
        "execute": fake_execute,
    })()
    monkeypatch.setattr(alembic_op, "get_bind", lambda: fake_bind)
    monkeypatch.setattr(sa, "inspect", lambda _bind: _FakeInspector(_all_clean_columns()))

    statements = []
    monkeypatch.setattr(alembic_op, "execute", lambda sql, *a, **k: statements.append(str(sql)))

    module = _load_migration_025()
    with caplog.at_level("WARNING"):
        module.upgrade()  # must not raise

    joined = " ".join(statements)
    assert "uq_restaurants_owner_phone" not in joined
    assert any("Skipping" in r.message and "owner_phone" in r.message for r in caplog.records)


def test_idempotent_when_already_applied(monkeypatch):
    """If NOT NULL / UNIQUE are already in place (inspector reports it), upgrade()
    must emit zero DDL — matches migration 016's idempotency guarantee."""
    from alembic import op as alembic_op
    import sqlalchemy as sa

    already_applied = {
        "orders": {"restaurant_id": False},
        "reservations": {"restaurant_id": False},
        "menu_items": {"restaurant_id": False},
        "tables": {"restaurant_id": False},
        "inventory_items": {"restaurant_id": False},
        "restaurants": {"tenant_id": True, "owner_phone": True},
    }
    fake_bind = type("Bind", (), {
        "dialect": type("D", (), {"name": "postgresql"})(),
        "execute": lambda self, *a, **k: _FakeResult(0),
    })()
    monkeypatch.setattr(alembic_op, "get_bind", lambda: fake_bind)
    monkeypatch.setattr(
        sa, "inspect",
        lambda _bind: _FakeInspector(
            already_applied,
            uniques={"restaurants": {"uq_restaurants_owner_phone"}},
        ),
    )

    statements = []
    monkeypatch.setattr(alembic_op, "execute", lambda sql, *a, **k: statements.append(str(sql)))

    module = _load_migration_025()
    module.upgrade()

    assert statements == []
