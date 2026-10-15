"""
S1.1 — owner settings (docs/v2/SPEC.md §3.2): RestaurantSettings model, migration 051,
owner/settings.py (get/update with bounds + audit), GET|PUT /api/v1/owner/settings.

What this pins:
  * defaults equal today's hard-coded constants, so moving thresholds to settings (S1.2) changes no number;
  * bounds are enforced (API and service), cross-field rule floor <= target, unknown fields rejected;
  * every change writes an audit row (old, new, who, when); a no-op write writes none;
  * owner-only; tenant-isolated; multi-restaurant tenants get one row per restaurant;
  * the new /owner prefix is inside the observer-mode fail-closed boundary;
  * migration 051 is idempotent (the Dockerfile runs create_all() before alembic), reversible, matches the
    model, and renders valid PostgreSQL DDL offline.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

import auth
import models
from time_utils import utcnow

BACKEND = Path(__file__).resolve().parents[1]


# ── helpers ───────────────────────────────────────────────────────────────────

def _tenant(db, suffix, *, role=models.Role.STAFF, staff_role=models.StaffRole.OWNER, restaurants=1):
    tenant = models.Tenant(name=f"Tenant {suffix}")
    db.add(tenant)
    db.flush()
    rests = []
    for n in range(restaurants):
        r = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}{n}", address="x")
        db.add(r)
        rests.append(r)
    user = models.User(tenant_id=tenant.id, email=f"u{suffix}@e.com", hashed_password=auth.get_password_hash("x"),
                       role=role, staff_role=staff_role, token_version=0)
    db.add(user)
    db.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return tenant, rests, user, {"Authorization": f"Bearer {token}"}


# ── defaults are today's constants ───────────────────────────────────────────

def test_defaults_are_the_spec_table_and_todays_numbers():
    """SPEC fig 3.2 defaults. They are also the values the engines hard-coded before S1.2 (menu's 40% food-cost
    ceiling aside, unified at 35), so moving an engine to settings changes no number — E2 proves that."""
    from owner.settings import DEFAULTS
    assert DEFAULTS.food_cost_target_pct == 35.0 and DEFAULTS.prime_cost_target_pct == 62.0
    assert DEFAULTS.margin_floor_pct == 40.0 and DEFAULTS.margin_target_pct == 55.0
    assert DEFAULTS.popular_cutoff == 0.70 and DEFAULTS.missing_stock_flag_pct == 3.0
    assert DEFAULTS.cash_tolerance_cents == 20_000 and DEFAULTS.cash_tolerance_pct == 1.0
    assert (DEFAULTS.commission_uber_eats_pct, DEFAULTS.commission_glovo_pct, DEFAULTS.commission_bolt_food_pct) == (25.0, 25.0, 20.0)
    assert (DEFAULTS.offer_size_pct, DEFAULTS.offer_lift_pct, DEFAULTS.max_raise_pct) == (10.0, 30.0, 15.0)
    assert DEFAULTS.price_step_cents == 500 and DEFAULTS.price_sensitivity == -0.7
    assert DEFAULTS.labour_target_pct == 30.0 and DEFAULTS.overtime_after_hours == 8.0
    assert (DEFAULTS.urgent_alerts_per_day, DEFAULTS.quiet_hours_start, DEFAULTS.quiet_hours_end, DEFAULTS.licence_warning_days) == (5, 22, 7, 14)
    assert DEFAULTS.commissions == {"uber_eats": 0.25, "glovo": 0.25, "bolt_food": 0.2}
    assert DEFAULTS.commission_rate("walk_in") == 0.0


def test_every_field_has_owner_words_and_defaults_inside_bounds():
    from owner.settings import FIELDS, DEFAULTS
    assert len(FIELDS) >= 24
    for spec in FIELDS:
        assert spec.label and spec.question.endswith("?"), spec.key
        assert spec.minimum <= spec.default <= spec.maximum, spec.key
        assert getattr(DEFAULTS, spec.attr) * 1 == spec.default * spec.scale, spec.key
    keys = [f.key for f in FIELDS]
    assert len(keys) == len(set(keys))


def test_get_settings_returns_defaults_when_no_row(db_session):
    from owner.settings import get_settings, DEFAULTS
    _t, (r,), _u, _h = _tenant(db_session, "a")
    assert get_settings(db_session, r.id) == DEFAULTS
    assert db_session.query(models.RestaurantSettings).count() == 0     # reading never writes


# ── API: read, write, audit ──────────────────────────────────────────────────

def test_get_returns_fields_with_value_default_bounds_and_question(client, db_session):
    _t, _r, _u, headers = _tenant(db_session, "a")
    body = client.get("/api/v1/owner/settings", headers=headers).json()
    assert body["updated_at"] is None
    fields = {f["key"]: f for f in body["fields"]}
    food = fields["food_cost_target_pct"]
    assert (food["value"], food["default"], food["min"], food["max"], food["is_default"]) == (35.0, 35.0, 20, 50, True)
    assert food["question"] == "Out of every KES 100 you sell, how much should ingredients cost at most?"
    cash = fields["cash_tolerance_kes"]                                   # money crosses the API edge in KES
    assert (cash["value"], cash["default"], cash["unit"]) == (200, 200, "KES")


def test_put_persists_converts_money_and_audits_each_changed_field(client, db_session):
    _t, (r,), user, headers = _tenant(db_session, "a")
    res = client.put("/api/v1/owner/settings", headers=headers,
                     json={"food_cost_target_pct": 32, "cash_tolerance_kes": 350, "price_step_kes": 10})
    assert res.status_code == 200, res.text
    row = db_session.query(models.RestaurantSettings).filter_by(restaurant_id=r.id).one()
    assert (row.food_cost_target_pct, row.cash_tolerance_cents, row.price_step_cents) == (32.0, 35_000, 1_000)
    assert row.updated_by_user_id == user.id and row.updated_at is not None
    body = client.get("/api/v1/owner/settings", headers=headers).json()
    fields = {f["key"]: f for f in body["fields"]}
    assert fields["food_cost_target_pct"]["value"] == 32.0 and fields["food_cost_target_pct"]["is_default"] is False
    assert fields["cash_tolerance_kes"]["value"] == 350
    assert fields["margin_floor_pct"]["is_default"] is True                # untouched fields stay defaults

    audit = db_session.query(models.RestaurantSettingsAudit).filter_by(restaurant_id=r.id).all()
    assert {(a.field, a.old_value, a.new_value) for a in audit} == {
        ("food_cost_target_pct", "35.0", "32.0"),
        ("cash_tolerance_cents", "20000", "35000"),
        ("price_step_cents", "500", "1000"),
    }
    assert all(a.changed_by_user_id == user.id and a.changed_at is not None for a in audit)


def test_a_write_that_changes_nothing_writes_no_audit_and_keeps_updated_at(client, db_session):
    _t, (r,), _u, headers = _tenant(db_session, "a")
    client.put("/api/v1/owner/settings", headers=headers, json={"margin_floor_pct": 45})
    first = db_session.query(models.RestaurantSettings).filter_by(restaurant_id=r.id).one().updated_at
    count = db_session.query(models.RestaurantSettingsAudit).count()
    res = client.put("/api/v1/owner/settings", headers=headers, json={"margin_floor_pct": 45})
    assert res.status_code == 200
    db_session.expire_all()
    assert db_session.query(models.RestaurantSettingsAudit).count() == count
    assert db_session.query(models.RestaurantSettings).filter_by(restaurant_id=r.id).one().updated_at == first


def test_history_lists_changes_newest_first(client, db_session):
    _t, _r, _u, headers = _tenant(db_session, "a")
    client.put("/api/v1/owner/settings", headers=headers, json={"margin_floor_pct": 45})
    client.put("/api/v1/owner/settings", headers=headers, json={"margin_floor_pct": 50})
    history = client.get("/api/v1/owner/settings/history?limit=10", headers=headers).json()["history"]
    assert [(h["field"], h["old_value"], h["new_value"]) for h in history] == [
        ("margin_floor_pct", "45.0", "50.0"), ("margin_floor_pct", "40.0", "45.0")]


# ── validation ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("payload", [
    {"food_cost_target_pct": 19.9}, {"food_cost_target_pct": 50.1},
    {"prime_cost_target_pct": 39}, {"prime_cost_target_pct": 81},
    {"margin_floor_pct": 19}, {"margin_floor_pct": 71},
    {"margin_target_pct": 29}, {"margin_target_pct": 81},
    {"popular_cutoff": 0.49}, {"popular_cutoff": 1.01},
    {"missing_stock_flag_pct": 0.9}, {"missing_stock_flag_pct": 10.1},
    {"cash_tolerance_kes": -1}, {"cash_tolerance_kes": 2001},
    {"cash_tolerance_pct": -0.1}, {"cash_tolerance_pct": 5.1},
    {"commission_glovo_pct": -1}, {"commission_glovo_pct": 40.1},
    {"offer_size_pct": 4.9}, {"offer_size_pct": 30.1},
    {"offer_lift_pct": -1}, {"offer_lift_pct": 100.1},
    {"max_raise_pct": 4.9}, {"max_raise_pct": 30.1},
    {"price_step_kes": 0}, {"price_step_kes": 51},
    {"price_sensitivity": -1.21}, {"price_sensitivity": -0.39},
    {"labour_target_pct": 14.9}, {"labour_target_pct": 50.1},
    {"overtime_after_hours": 5.9}, {"overtime_after_hours": 12.1},
    {"urgent_alerts_per_day": 0}, {"urgent_alerts_per_day": 21},
    {"quiet_hours_start": 24}, {"quiet_hours_start": -1}, {"quiet_hours_end": 24},
    {"licence_warning_days": 6}, {"licence_warning_days": 61},
])
def test_out_of_bounds_values_are_rejected_and_nothing_is_written(client, db_session, payload):
    _t, _r, _u, headers = _tenant(db_session, "a")
    res = client.put("/api/v1/owner/settings", headers=headers, json=payload)
    assert res.status_code == 422, (payload, res.text)
    assert db_session.query(models.RestaurantSettings).count() == 0
    assert db_session.query(models.RestaurantSettingsAudit).count() == 0


@pytest.mark.parametrize("payload", [
    {"food_cost_target_pct": 20}, {"food_cost_target_pct": 50}, {"popular_cutoff": 0.5}, {"popular_cutoff": 1.0},
    {"price_sensitivity": -1.2}, {"price_sensitivity": -0.4}, {"quiet_hours_start": 0}, {"quiet_hours_end": 23},
    {"cash_tolerance_kes": 0}, {"cash_tolerance_kes": 2000}, {"price_step_kes": 1}, {"price_step_kes": 50},
])
def test_bounds_are_inclusive(client, db_session, payload):
    _t, _r, _u, headers = _tenant(db_session, "a")
    assert client.put("/api/v1/owner/settings", headers=headers, json=payload).status_code == 200


def test_unknown_and_mistyped_fields_are_rejected(client, db_session):
    _t, _r, _u, headers = _tenant(db_session, "a")
    assert client.put("/api/v1/owner/settings", headers=headers, json={"vat_pct": 16}).status_code == 422
    assert client.put("/api/v1/owner/settings", headers=headers, json={"food_cost_target_pct": "lots"}).status_code == 422
    assert client.put("/api/v1/owner/settings", headers=headers, json={"restaurant_id": 1}).status_code == 422
    assert client.put("/api/v1/owner/settings", headers=headers, json={}).status_code == 422   # nothing to change


def test_margin_floor_must_not_exceed_margin_target(client, db_session):
    _t, _r, _u, headers = _tenant(db_session, "a")
    res = client.put("/api/v1/owner/settings", headers=headers, json={"margin_floor_pct": 60})   # target default 55
    assert res.status_code == 422 and "margin_floor_pct" in res.text and "margin_target_pct" in res.text
    assert client.put("/api/v1/owner/settings", headers=headers,
                      json={"margin_floor_pct": 60, "margin_target_pct": 65}).status_code == 200
    res = client.put("/api/v1/owner/settings", headers=headers, json={"margin_target_pct": 50})  # floor now 60
    assert res.status_code == 422
    assert client.put("/api/v1/owner/settings", headers=headers,
                      json={"margin_floor_pct": 60, "margin_target_pct": 60}).status_code == 200  # equal is allowed


# ── who may call it ──────────────────────────────────────────────────────────

def test_owner_admin_and_superadmin_may_use_settings(client, db_session):
    for i, (role, staff_role) in enumerate([(models.Role.STAFF, models.StaffRole.OWNER),
                                            (models.Role.ADMIN, None), (models.Role.SUPERADMIN, None)]):
        _t, _r, _u, headers = _tenant(db_session, f"ok{i}", role=role, staff_role=staff_role)
        assert client.get("/api/v1/owner/settings", headers=headers).status_code == 200
        assert client.put("/api/v1/owner/settings", headers=headers, json={"margin_floor_pct": 42}).status_code == 200


@pytest.mark.parametrize("staff_role", [models.StaffRole.MANAGER, models.StaffRole.SUPERVISOR, models.StaffRole.CONTROLLER,
                                        models.StaffRole.STOCKKEEPER, models.StaffRole.KITCHEN, models.StaffRole.WAITER])
def test_other_staff_roles_cannot_read_or_change_settings(client, db_session, staff_role):
    _t, _r, _u, headers = _tenant(db_session, f"s{staff_role.value}", staff_role=staff_role)
    assert client.get("/api/v1/owner/settings", headers=headers).status_code == 403
    assert client.put("/api/v1/owner/settings", headers=headers, json={"margin_floor_pct": 42}).status_code == 403
    assert client.get("/api/v1/owner/settings/history", headers=headers).status_code == 403
    assert db_session.query(models.RestaurantSettings).count() == 0


def test_unauthenticated_is_401(client):
    assert client.get("/api/v1/owner/settings").status_code == 401
    assert client.put("/api/v1/owner/settings", json={"margin_floor_pct": 42}).status_code == 401


def test_staff_user_without_a_staff_role_is_told_so(client, db_session):
    _t, _r, _u, headers = _tenant(db_session, "none", staff_role=None)
    res = client.get("/api/v1/owner/settings", headers=headers)
    assert res.status_code == 403 and res.json()["detail"] == "staff_role_unassigned"


# ── tenant isolation ─────────────────────────────────────────────────────────

def test_one_tenant_never_sees_or_changes_anothers_settings(client, db_session):
    _ta, (ra,), _ua, ha = _tenant(db_session, "a")
    _tb, (rb,), _ub, hb = _tenant(db_session, "b")
    client.put("/api/v1/owner/settings", headers=ha, json={"food_cost_target_pct": 28})

    fields_b = {f["key"]: f for f in client.get("/api/v1/owner/settings", headers=hb).json()["fields"]}
    assert fields_b["food_cost_target_pct"]["value"] == 35.0               # B still has defaults
    assert client.get("/api/v1/owner/settings/history", headers=hb).json()["history"] == []

    client.put("/api/v1/owner/settings", headers=hb, json={"food_cost_target_pct": 41})
    fields_a = {f["key"]: f for f in client.get("/api/v1/owner/settings", headers=ha).json()["fields"]}
    assert fields_a["food_cost_target_pct"]["value"] == 28.0               # A unchanged by B's write
    rows = {s.restaurant_id: s.food_cost_target_pct for s in db_session.query(models.RestaurantSettings).all()}
    assert rows == {ra.id: 28.0, rb.id: 41.0}


def test_pointing_active_restaurant_at_another_tenant_does_not_cross_the_boundary(client, db_session):
    _ta, (ra,), _ua, ha = _tenant(db_session, "a")
    _tb, (rb,), ub, hb = _tenant(db_session, "b")
    client.put("/api/v1/owner/settings", headers=ha, json={"food_cost_target_pct": 28})
    ub.active_restaurant_id = ra.id                                        # forged selection of A's restaurant
    db_session.commit()
    res = client.put("/api/v1/owner/settings", headers=hb, json={"food_cost_target_pct": 44})
    assert res.status_code == 200
    rows = {s.restaurant_id: s.food_cost_target_pct for s in db_session.query(models.RestaurantSettings).all()}
    assert rows == {ra.id: 28.0, rb.id: 44.0}                              # landed on B's own restaurant


def test_each_restaurant_of_a_chain_has_its_own_settings(client, db_session):
    _t, (r1, r2), user, headers = _tenant(db_session, "chain", restaurants=2)
    user.active_restaurant_id = r2.id
    db_session.commit()
    client.put("/api/v1/owner/settings", headers=headers, json={"margin_floor_pct": 47})
    assert {s.restaurant_id: s.margin_floor_pct for s in db_session.query(models.RestaurantSettings).all()} == {r2.id: 47.0}
    user.active_restaurant_id = r1.id
    db_session.commit()
    fields = {f["key"]: f for f in client.get("/api/v1/owner/settings", headers=headers).json()["fields"]}
    assert fields["margin_floor_pct"]["value"] == 40.0


def test_service_get_settings_reads_the_saved_row(client, db_session):
    from owner.settings import get_settings
    _t, (r,), _u, headers = _tenant(db_session, "a")
    client.put("/api/v1/owner/settings", headers=headers,
               json={"popular_cutoff": 0.8, "commission_glovo_pct": 30, "quiet_hours_start": 21})
    s = get_settings(db_session, r.id)
    assert (s.popular_cutoff, s.commission_glovo_pct, s.quiet_hours_start) == (0.8, 30.0, 21)
    assert s.margin_target_pct == 55.0 and s.commission_uber_eats_pct == 25.0       # the rest are defaults


# ── observer mode ────────────────────────────────────────────────────────────

def test_owner_api_is_inside_the_observer_mode_boundary():
    """/overview, /reports and /ai are blocked in the read-only Macsoft deployment because their figures come
    from local tables; the new /owner API composes the same numbers and must be blocked the same way."""
    from observer_mode import is_blocked_request
    for method in ("GET", "PUT", "POST"):
        assert is_blocked_request(method, "/api/v1/owner/settings")
        assert is_blocked_request(method, "/owner/home")
    assert not is_blocked_request("GET", "/api/v1/ownership")                # prefix match is on a path segment


# ── migration 051 ────────────────────────────────────────────────────────────

def _load_migration():
    import importlib.util
    path = BACKEND / "alembic" / "versions" / "051_add_restaurant_settings.py"
    spec = importlib.util.spec_from_file_location("migration_051", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(connection, fn_name):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    module = _load_migration()
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, fn_name)()


def test_migration_051_chains_after_050_and_is_in_the_single_history():
    module = _load_migration()
    assert module.down_revision == "050_creative_takes"
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1                                       # one head, whatever has been added since 051
    assert module.revision in {rev.revision for rev in script.walk_revisions()}


def test_migration_051_creates_exactly_the_model_columns_and_is_reversible_and_idempotent(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    models.Base.metadata.create_all(engine, tables=[
        models.Tenant.__table__, models.Restaurant.__table__, models.User.__table__])
    with engine.begin() as conn:
        _run_migration(conn, "upgrade")
        inspector = sa.inspect(conn)
        assert {"restaurant_settings", "restaurant_settings_audit"} <= set(inspector.get_table_names())
        for model in (models.RestaurantSettings, models.RestaurantSettingsAudit):
            built = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            later = {"expense_spike_pct", "bill_reserve_cents"}                # added to this table by migration 053 (S3.3)
            assert built == {c.name for c in model.__table__.columns} - (later if model is models.RestaurantSettings else set()), model.__tablename__
        unique = [u["column_names"] for u in inspector.get_unique_constraints("restaurant_settings")]
        indexes = inspector.get_indexes("restaurant_settings")
        assert ["restaurant_id"] in unique or any(i["unique"] and i["column_names"] == ["restaurant_id"] for i in indexes)
        _run_migration(conn, "upgrade")                                  # create_all() already ran in prod: must not raise
        _run_migration(conn, "downgrade")
        assert not {"restaurant_settings", "restaurant_settings_audit"} & set(sa.inspect(conn).get_table_names())
        _run_migration(conn, "downgrade")                                # and the reverse is safe twice
        _run_migration(conn, "upgrade")
        assert "restaurant_settings" in sa.inspect(conn).get_table_names()


def test_migration_051_renders_postgresql_ddl_offline():
    """Prod is PostgreSQL, tests are SQLite: render the real DDL (offline, no connection) and read it."""
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg2://offline:offline@localhost:5432/offline", "SECRET_KEY": "x"}
    out = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "050_creative_takes:051_restaurant_settings", "--sql"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-1500:]
    sql = out.stdout
    assert "CREATE TABLE restaurant_settings" in sql and "CREATE TABLE restaurant_settings_audit" in sql
    assert "REFERENCES restaurants (id) ON DELETE CASCADE" in sql
    assert "UNIQUE" in sql and "food_cost_target_pct" in sql and "price_step_cents" in sql
    assert "DROP" not in sql                                              # additive only

    down = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "051_restaurant_settings:050_creative_takes", "--sql"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert down.returncode == 0, down.stderr[-1500:]
    assert "DROP TABLE restaurant_settings_audit" in down.stdout and "DROP TABLE restaurant_settings;" in down.stdout
    assert down.stdout.index("restaurant_settings_audit") < down.stdout.index("DROP TABLE restaurant_settings;")
