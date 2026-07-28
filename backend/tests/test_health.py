"""
Composite readiness check (GET /health/ready) added alongside the existing
GET /health/ (pure liveness) and GET /health/db (DB-only). Covers audit item
"health check quality" — neither of the two original endpoints checked the
LLM/Twilio/M-Pesa credentials, and they were split across two calls instead
of one an uptime monitor can poll.
"""


def test_health_ready_returns_200_with_dependency_flags(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["dependencies"]) == {"database", "llm_provider", "whatsapp", "mpesa"}
    assert body["dependencies"]["database"] is True


def test_health_ready_requires_no_auth(client):
    """An uptime monitor has no JWT — this must not be gated like /ai/*."""
    resp = client.get("/health/ready")
    assert resp.status_code != 401
    assert resp.status_code != 403


def test_health_ready_returns_503_when_db_is_down(client, monkeypatch):
    """
    get_db() does `db = SessionLocal()` — a name looked up against database's
    module globals at call time, not bound at import time — so patching
    database.SessionLocal (rather than FastAPI's dependency_overrides, which
    keys by the exact get_db object and misses it here because db_env's
    importlib.reload(database) rebinds get_db to a new function each test)
    is what actually reaches the router's real dependency.
    """
    import database

    class _Broken:
        def execute(self, *a, **k):
            raise Exception("simulated db outage")

        def close(self):
            pass

    monkeypatch.setattr(database, "SessionLocal", lambda: _Broken())

    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json()["detail"]["dependencies"]["database"] is False


def test_liveness_and_db_health_still_work_unchanged(client):
    """Original two endpoints must be untouched by adding /ready."""
    r1 = client.get("/health/")
    assert r1.status_code == 200
    assert r1.json() == {"status": "ok", "message": "Service is healthy"}

    r2 = client.get("/health/db")
    assert r2.status_code == 200
    assert r2.json()["database"] == "connected"
