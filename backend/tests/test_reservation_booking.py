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

from datetime import date, time, timedelta

# Fixed future dates rot; anchor bookings to tomorrow so the suite stays
# green regardless of when it runs.
_BOOKING_DAY = date.today() + timedelta(days=1)
_BOOKING_DAY_NEXT = _BOOKING_DAY + timedelta(days=1)

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
        "reservation_date": str(_BOOKING_DAY),
        "reservation_time": str(time(hour, minute)),
        "duration_minutes": duration,
        "table_id": table_id,
    }


def test_overlapping_booking_on_same_table_is_rejected(client, db_session):
    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "a")
    table = _add_table(db_session, restaurant, "T1")

    first = client.post("/reservations/", json=_booking(table.id, hour=18), headers=_auth_headers(token))
    assert first.status_code == 201, first.text

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
    assert first.status_code == 201, first.text

    second = client.post("/reservations/", json=_booking(table.id, hour=19, minute=30), headers=_auth_headers(token))
    assert second.status_code == 201, second.text

    assert db_session.query(models.Reservation).count() == 2


def test_cancelled_reservation_does_not_block_the_slot(client, db_session):
    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "c")
    table = _add_table(db_session, restaurant, "T1")

    first = client.post("/reservations/", json=_booking(table.id, hour=18), headers=_auth_headers(token))
    assert first.status_code == 201
    res_id = first.json()["id"]

    cancel = client.post(
        f"/reservations/{res_id}/status", json={"status": "cancelled"}, headers=_auth_headers(token)
    )
    assert cancel.status_code == 200, cancel.text

    retry = client.post("/reservations/", json=_booking(table.id, hour=18), headers=_auth_headers(token))
    assert retry.status_code == 201, retry.text


def test_reconfirming_a_reservation_into_an_occupied_slot_is_rejected(client, db_session):
    """
    Re-confirming a previously-freed reservation must re-run the overlap check.
    A NO_SHOW frees the slot; another booking takes it; flipping the first back
    to CONFIRMED would double-book the table, so it must 409 (the same answer
    create_reservation gives), not silently succeed.
    """
    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "reconfirm")
    table = _add_table(db_session, restaurant, "T1")

    first = client.post("/reservations/", json=_booking(table.id, hour=18), headers=_auth_headers(token))
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]

    # Free the slot, then let a second booking take the same table/time.
    no_show = client.post(
        f"/reservations/{first_id}/status", json={"status": "no_show"}, headers=_auth_headers(token)
    )
    assert no_show.status_code == 200, no_show.text

    second = client.post("/reservations/", json=_booking(table.id, hour=18), headers=_auth_headers(token))
    assert second.status_code == 201, second.text

    # Undoing the no-show would collide with the second booking.
    reconfirm = client.post(
        f"/reservations/{first_id}/status", json={"status": "confirmed"}, headers=_auth_headers(token)
    )
    assert reconfirm.status_code == 409, reconfirm.text
    assert "overlapping" in reconfirm.json()["detail"].lower()

    confirmed = db_session.query(models.Reservation).filter(
        models.Reservation.status == models.ReservationStatus.CONFIRMED
    ).count()
    assert confirmed == 1


def test_reconfirming_when_slot_is_free_succeeds(client, db_session):
    """The guard must not block a legitimate un-cancel when nothing else took the slot."""
    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "reconfirm_ok")
    table = _add_table(db_session, restaurant, "T1")

    booked = client.post("/reservations/", json=_booking(table.id, hour=18), headers=_auth_headers(token))
    assert booked.status_code == 201
    res_id = booked.json()["id"]

    client.post(f"/reservations/{res_id}/status", json={"status": "cancelled"}, headers=_auth_headers(token))
    reconfirm = client.post(
        f"/reservations/{res_id}/status", json={"status": "confirmed"}, headers=_auth_headers(token)
    )
    assert reconfirm.status_code == 200, reconfirm.text
    assert reconfirm.json()["status"] == "confirmed"


def test_cross_midnight_reservation_blocks_next_day_overlap(client, db_session):
    """
    A reservation starting 23:00 with a 120-min duration runs to 01:00 the next
    calendar day. is_table_available scoped to the exact reservation_date used to
    miss it, letting a 00:00 next-day booking double-book the table.
    """
    from datetime import time

    from ai.reservation_optimizer import is_table_available

    restaurant, token = _make_tenant_with_user_and_restaurant(db_session, "midnight")
    table = _add_table(db_session, restaurant, "T1")

    late = {
        "customer_name": "Late Diner",
        "party_size": 2,
        "reservation_date": str(_BOOKING_DAY),
        "reservation_time": str(time(23, 0)),
        "duration_minutes": 120,
        "table_id": table.id,
    }
    resp = client.post("/reservations/", json=late, headers=_auth_headers(token))
    assert resp.status_code == 201, resp.text

    # A 00:00 booking on the next day overlaps the 23:00–01:00 window from 08-01.
    assert is_table_available(
        db_session,
        restaurant_id=restaurant.id,
        table_id=table.id,
        reservation_date=_BOOKING_DAY_NEXT,
        reservation_time=time(0, 0),
        duration_minutes=60,
    ) is False


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
    assert resp.status_code == 201, resp.text


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

    # upgrade() first reconciles pre-existing overlaps via bind.execute(UPDATE ...)
    # in a loop that stops when rowcount == 0 (added with the reconciliation step,
    # commit e2bc6e4). The fake bind must therefore support .execute returning a
    # result whose rowcount is 0 (no overlaps to cancel in this control-flow test).
    class _FakeResult:
        rowcount = 0

    fake_bind = type("Bind", (), {
        "dialect": type("D", (), {"name": "postgresql"})(),
        "execute": lambda self, *a, **k: _FakeResult(),
    })()
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
