"""
Booking-time guards on POST /reservations.

Until 2026-07-08 this endpoint wrote `table_id` straight from the request body:
no check that the table belonged to the caller's restaurant, no check that the
table was free, no check that it was big enough. `find_available_tables()` had
been correct since Phase 2 but no write path ever called it, so the "no DB-level
concurrency guard" caveat in its docstring understated the problem — sequential,
uncontended double-booking worked fine.

The race that remains after these checks (two writers passing the SELECT before
either INSERTs) is closed by the Postgres EXCLUDE constraint in
alembic/versions/009_add_reservation_overlap_guard.py, which cannot run on
SQLite. So it is deliberately NOT asserted here — see
test_migration_009_is_a_noop_on_sqlite for what is asserted instead, and the
migration's docstring for why the split exists.
"""

from datetime import date, time

import auth
import models


def _make_tenant_with_user_and_restaurant(db_session, suffix: str):
    tenant = models.Tenant(name=f"Tenant {suffix}")
    db_session.add(tenant)
    db_session.commit()

    user = models.User(
        tenant_id=tenant.id,
        email=f"owner_{suffix}@example.com",
        hashed_password=auth.get_password_hash("irrelevant"),
        role=models.Role.ADMIN,
    )
    db_session.add(user)

    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"Restaurant {suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()

    token = auth.create_access_token({"sub": user.email})
    return restaurant, token


def _add_table(db_session, restaurant, number: str, capacity: int = 4):
    table = models.Table(restaurant_id=restaurant.id, table_number=number, capacity=capacity)
    db_session.add(table)
    db_session.commit()
    db_session.refresh(table)
    return table


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _booking(table_id, hour=18, minute=0, duration=90, party_size=2):
    return {
        "customer_name": "Test Customer",
        "party_size": party_size,
        "reservation_date": str(date(2026, 8, 1)),
        "reservation_time": str(time(hour, minute)),
        "duration_minutes": duration,
        "table_id": table_id,
    }


def test_overlapping_booking_on_same_table_is_rejected(client, db_session):
    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "a")
    table = _add_table(db_session, restaurant, "T1")

    first = client.post("/reservations/", json=_booking(table.id, hour=18), headers=_auth_headers(token))
    assert first.status_code == 200, first.text

    # 18:45 starts inside the 18:00–19:30 window already booked.
    second = client.post("/reservations/", json=_booking(table.id, hour=18, minute=45), headers=_auth_headers(token))
    assert second.status_code == 409, second.text
    assert "overlapping" in second.json()["detail"].lower()

    assert db_session.query(models.Reservation).count() == 1


def test_adjacent_booking_is_allowed(client, db_session):
    """Half-open intervals: a slot ending at 19:30 does not conflict with one starting at 19:30."""
    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "b")
    table = _add_table(db_session, restaurant, "T1")

    first = client.post("/reservations/", json=_booking(table.id, hour=18, minute=0), headers=_auth_headers(token))
    assert first.status_code == 200, first.text

    second = client.post("/reservations/", json=_booking(table.id, hour=19, minute=30), headers=_auth_headers(token))
    assert second.status_code == 200, second.text

    assert db_session.query(models.Reservation).count() == 2


def test_cancelled_reservation_does_not_block_the_slot(client, db_session):
    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "c")
    table = _add_table(db_session, restaurant, "T1")

    first = client.post("/reservations/", json=_booking(table.id, hour=18), headers=_auth_headers(token))
    assert first.status_code == 200
    res_id = first.json()["id"]

    cancel = client.patch(
        f"/reservations/{res_id}/status", json={"status": "cancelled"}, headers=_auth_headers(token)
    )
    assert cancel.status_code == 200, cancel.text

    retry = client.post("/reservations/", json=_booking(table.id, hour=18), headers=_auth_headers(token))
    assert retry.status_code == 200, retry.text


def test_cannot_book_another_tenants_table(client, db_session):
    """IDOR: guessing another restaurant's table id must look like a missing table, not a forbidden one."""
    _restaurant_a, token_a = _make_tenant_with_user_and_restaurant(db_session, "a")
    restaurant_b, _token_b = _make_tenant_with_user_and_restaurant(db_session, "b")
    table_b = _add_table(db_session, restaurant_b, "B1")

    resp = client.post("/reservations/", json=_booking(table_b.id), headers=_auth_headers(token_a))
    assert resp.status_code == 404, resp.text
    assert db_session.query(models.Reservation).count() == 0


def test_table_too_small_for_party_is_rejected(client, db_session):
    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "d")
    table = _add_table(db_session, restaurant, "T1", capacity=2)

    resp = client.post("/reservations/", json=_booking(table.id, party_size=6), headers=_auth_headers(token))
    assert resp.status_code == 400, resp.text
    assert db_session.query(models.Reservation).count() == 0


def test_booking_without_a_table_still_works(client, db_session):
    """table_id is optional — a walk-in-style reservation with no table assigned must not 404."""
    _restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "e")

    resp = client.post("/reservations/", json=_booking(None), headers=_auth_headers(token))
    assert resp.status_code == 200, resp.text


def _load_migration_009():
    """alembic/versions/ is not a package and '009_...' is not a valid identifier, so load by path."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "009_add_reservation_overlap_guard.py"
    spec = importlib.util.spec_from_file_location("migration_009", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_009_is_a_noop_on_sqlite(monkeypatch):
    """
    The EXCLUDE constraint is Postgres-only. Assert the dialect guard actually
    short-circuits rather than emitting DDL SQLite would choke on — this is what
    keeps `alembic upgrade head` usable in local dev and CI.
    """
    from alembic import op as alembic_op

    fake_bind = type("Bind", (), {"dialect": type("D", (), {"name": "sqlite"})()})()
    monkeypatch.setattr(alembic_op, "get_bind", lambda: fake_bind)

    def _explode(*_a, **_k):
        raise AssertionError("migration 009 emitted DDL on a non-Postgres dialect")

    monkeypatch.setattr(alembic_op, "execute", _explode)

    module = _load_migration_009()
    module.upgrade()   # must return before touching op.execute
    module.downgrade()


def test_migration_009_emits_exclude_constraint_on_postgres(monkeypatch):
    """
    Guard the other direction: on Postgres it must create btree_gist and add the
    constraint. The DDL itself is unverified against a real server (no local
    Postgres — see the migration docstring); this only pins the control flow so a
    future edit can't silently turn the production backstop into a no-op.
    """
    from alembic import op as alembic_op

    fake_bind = type("Bind", (), {"dialect": type("D", (), {"name": "postgresql"})()})()
    monkeypatch.setattr(alembic_op, "get_bind", lambda: fake_bind)

    statements = []
    monkeypatch.setattr(alembic_op, "execute", lambda sql, *a, **k: statements.append(str(sql)))

    module = _load_migration_009()
    monkeypatch.setattr(module, "_constraint_exists", lambda _name: False)
    module.upgrade()

    joined = " ".join(statements)
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in joined
    assert "EXCLUDE USING gist" in joined
    assert "table_id WITH =" in joined
    assert "status = 'CONFIRMED'" in joined  # enum NAME, not the 'confirmed' value


def test_migration_009_is_idempotent_when_constraint_exists(monkeypatch):
    from alembic import op as alembic_op

    fake_bind = type("Bind", (), {"dialect": type("D", (), {"name": "postgresql"})()})()
    monkeypatch.setattr(alembic_op, "get_bind", lambda: fake_bind)

    statements = []
    monkeypatch.setattr(alembic_op, "execute", lambda sql, *a, **k: statements.append(str(sql)))

    module = _load_migration_009()
    monkeypatch.setattr(module, "_constraint_exists", lambda _name: True)
    module.upgrade()

    assert not any("EXCLUDE USING gist" in s for s in statements)
