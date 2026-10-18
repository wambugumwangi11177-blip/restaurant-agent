"""
S3.3 — two owner settings for the money layer (docs/v2/SPEC.md S3.3: expense spike "≥ 25% (setting)"; the bill radar's opening
position), added to the settings service (one source of truth for thresholds) and migration 053.

  expense_spike_pct   how far above its usual a cost must be before it is flagged       default 25 %, 10–100
  bill_reserve_kes    cash kept aside for bills — the bill radar's opening position     default KES 0, 0–10,000,000
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

import auth
import models

BACKEND = Path(__file__).resolve().parents[1]
API = "/api/v1/owner/settings"


def _owner(db, suffix="a"):
    t = models.Tenant(name=f"T{suffix}")
    db.add(t)
    db.flush()
    r = models.Restaurant(tenant_id=t.id, name=f"R{suffix}", address="x")
    db.add(r)
    u = models.User(tenant_id=t.id, email=f"{suffix}@s33.test", hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF,
                    staff_role=models.StaffRole.OWNER, token_version=0)
    db.add(u)
    db.commit()
    return r, u, {"Authorization": f"Bearer {auth.create_access_token({'sub': u.email, 'ver': 0})}"}


def test_defaults_and_owner_words():
    from owner.settings import BY_KEY, DEFAULTS
    assert DEFAULTS.expense_spike_pct == 25.0 and DEFAULTS.bill_reserve_cents == 0
    spike, reserve = BY_KEY["expense_spike_pct"], BY_KEY["bill_reserve_kes"]
    assert (spike.group, spike.default, spike.minimum, spike.maximum) == ("Money", 25.0, 10, 100)
    assert (reserve.group, reserve.default, reserve.minimum, reserve.maximum, reserve.attr, reserve.scale) == ("Money", 0, 0, 10_000_000, "bill_reserve_cents", 100)
    for spec in (spike, reserve):
        assert spec.question.endswith("?") and spec.label


def test_the_reserve_is_shillings_at_the_edge_and_cents_inside(client, db_session):
    r, u, h = _owner(db_session)
    res = client.put(API, headers=h, json={"bill_reserve_kes": 45_000, "expense_spike_pct": 30})
    assert res.status_code == 200, res.text
    fields = {f["key"]: f for f in res.json()["fields"]}
    assert fields["bill_reserve_kes"]["value"] == 45_000 and fields["expense_spike_pct"]["value"] == 30.0
    row = db_session.query(models.RestaurantSettings).one()
    assert row.bill_reserve_cents == 4_500_000 and isinstance(row.bill_reserve_cents, int) and row.expense_spike_pct == 30.0
    from owner.settings import get_settings
    s = get_settings(db_session, r.id)
    assert (s.bill_reserve_cents, s.expense_spike_pct) == (4_500_000, 30.0)
    changed = {a.field for a in db_session.query(models.RestaurantSettingsAudit)}
    assert {"bill_reserve_cents", "expense_spike_pct"} <= changed             # audited like every other setting


@pytest.mark.parametrize("payload", [{"expense_spike_pct": 9}, {"expense_spike_pct": 101}, {"bill_reserve_kes": -1}, {"bill_reserve_kes": 10_000_001},
                                     {"bill_reserve_kes": 1500.5}, {"expense_spike_pct": "lots"}])
def test_out_of_range_values_are_refused(client, db_session, payload):
    _r, _u, h = _owner(db_session)
    assert client.put(API, headers=h, json=payload).status_code == 422
    assert db_session.query(models.RestaurantSettings).count() == 0


def test_a_new_restaurant_reads_the_defaults(client, db_session):
    _r, _u, h = _owner(db_session)
    fields = {f["key"]: f for f in client.get(API, headers=h).json()["fields"]}
    assert (fields["expense_spike_pct"]["value"], fields["bill_reserve_kes"]["value"]) == (25.0, 0)
    assert fields["expense_spike_pct"]["is_default"] and fields["bill_reserve_kes"]["is_default"]


# ── migration 053 ────────────────────────────────────────────────────────────

def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("migration_053", BACKEND / "alembic" / "versions" / "053_add_money_settings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    module = _load()
    with Operations.context(MigrationContext.configure(conn)):
        getattr(module, fn)()


def test_migration_053_follows_052_and_the_chain_has_one_head():
    """(It used to say 053 *is* the head; every later migration made that false. What matters: it follows 052 and nothing forks.)"""
    module = _load()
    assert module.down_revision == "052_money_ledger"
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1 and module.revision in {r.revision for r in script.walk_revisions()}


def test_migration_053_adds_the_columns_with_defaults_to_an_existing_table_and_is_idempotent(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        # the table as migration 051 made it: without the two new columns, with one row already in it
        conn.execute(sa.text("create table restaurant_settings (id integer primary key, restaurant_id integer not null, food_cost_target_pct float not null)"))
        conn.execute(sa.text("insert into restaurant_settings (id, restaurant_id, food_cost_target_pct) values (1, 7, 33.0)"))
        _run(conn, "upgrade")
        cols = {c["name"]: c for c in sa.inspect(conn).get_columns("restaurant_settings")}
        assert {"expense_spike_pct", "bill_reserve_cents"} <= set(cols)
        row = conn.execute(sa.text("select expense_spike_pct, bill_reserve_cents from restaurant_settings")).one()
        assert (row[0], row[1]) == (25.0, 0)                                   # a row written before the migration reads as the defaults
        _run(conn, "upgrade")                                                  # a column create_all already made is skipped
        _run(conn, "downgrade")
        assert not {"expense_spike_pct", "bill_reserve_cents"} & {c["name"] for c in sa.inspect(conn).get_columns("restaurant_settings")}
        _run(conn, "downgrade")
        _run(conn, "upgrade")


def test_migration_053_renders_postgresql_ddl_offline():
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg2://offline:offline@localhost:5432/offline", "SECRET_KEY": "x"}
    up = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "052_money_ledger:053_money_settings", "--sql"],
                        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert up.returncode == 0, up.stderr[-1500:]
    assert "ALTER TABLE restaurant_settings ADD COLUMN expense_spike_pct FLOAT DEFAULT '25' NOT NULL" in up.stdout
    assert "ALTER TABLE restaurant_settings ADD COLUMN bill_reserve_cents INTEGER DEFAULT '0' NOT NULL" in up.stdout
    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "053_money_settings:052_money_ledger", "--sql"],
                          cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert down.returncode == 0, down.stderr[-1500:]
    assert "DROP COLUMN bill_reserve_cents" in down.stdout and "DROP COLUMN expense_spike_pct" in down.stdout
