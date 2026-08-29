"""
routers/health.py — audit remediation, Tier 1 item 4.

GET /health/ used to unconditionally return {"status": "ok"} regardless of DB
state — a shallow check that would pass even with the database down. If a
hosting platform's uptime probe is pointed at the bare root (the common
default) rather than /health/db, it never caught an outage. Both routes now
share the same DB check.
"""

from database import get_db
from main import app


def test_health_root_returns_ok_when_db_is_up(client):
    resp = client.get("/health/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_db_returns_ok_when_db_is_up(client):
    resp = client.get("/health/db")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "connected"}


def test_health_root_returns_503_when_db_is_down(client):
    def _broken_get_db():
        class _BrokenSession:
            def execute(self, *args, **kwargs):
                raise RuntimeError("simulated DB outage")

        yield _BrokenSession()

    app.dependency_overrides[get_db] = _broken_get_db
    try:
        resp = client.get("/health/")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_health_db_returns_503_when_db_is_down(client):
    def _broken_get_db():
        class _BrokenSession:
            def execute(self, *args, **kwargs):
                raise RuntimeError("simulated DB outage")

        yield _BrokenSession()

    app.dependency_overrides[get_db] = _broken_get_db
    try:
        resp = client.get("/health/db")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.pop(get_db, None)
