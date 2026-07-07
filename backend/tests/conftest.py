"""
backend/tests/conftest.py
──────────────────────────
Shared fixtures. Each test gets its own throwaway SQLite file (not :memory:,
since SQLAlchemy's default pool opens a fresh connection per session and an
in-memory DB doesn't persist across connections — see this project's own
verification scripts from the Phase 1/2 build, which hit exactly this issue).

Two hazards specific to this codebase, handled explicitly below:

1. `database.py` reads DATABASE_URL at import time and binds `engine`/
   `SessionLocal` at module level. Since pytest runs all tests in one
   process, later tests would silently reuse the FIRST test's database
   unless `database` is reloaded per test.

2. `ai/orchestrator/executive.py` does `from database import SessionLocal`
   at module level too — reloading `database` alone doesn't fix this,
   since it captured the name by value at its own import time. It must be
   reloaded separately, AFTER `database`, so its handlers pick up the
   fresh SessionLocal.

3. `events/bus.py` holds a process-wide singleton `_handlers` dict.
   Calling `register_all_handlers()` more than once per process silently
   accumulates duplicate subscriptions — a later test would see each event
   handler fire multiple times (e.g. duplicate WhatsApp sends, duplicate
   audit log writes) with no error raised. Must `clear_handlers()` first.

4. `rate_limit.py`'s `limiter` is also a process-wide singleton (in-memory
   request counters keyed by IP). Without resetting it, a rate-limit test
   earlier in the run leaves counters that make a LATER, unrelated test hit
   429s it shouldn't — or a lockout test's failed-login attempts get cut
   short by the rate limiter before reaching the lockout threshold. Reset
   before every test, not just rate-limit tests, since any test hitting
   auth/order endpoints shares the same counters.
"""

import importlib
import os
import uuid
import pytest

# auth.py reads SECRET_KEY at import time and raises RuntimeError if unset —
# and it can be imported at test-collection time (module-level `import auth`
# in a test file), before any fixture has run. Set a constant value once,
# globally, here — it doesn't need per-test isolation (JWT signing key reuse
# across tests carries no cross-test contamination risk).
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-verification-only")


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """Point the app at a fresh, isolated SQLite file for this test only."""
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-verification-only")

    import database
    importlib.reload(database)

    try:
        import ai.orchestrator.executive as executive
        importlib.reload(executive)
    except ImportError:
        pass

    from events.bus import clear_handlers
    clear_handlers()

    from rate_limit import limiter, SLOWAPI_AVAILABLE
    if SLOWAPI_AVAILABLE:
        limiter.reset()

    yield db_path


@pytest.fixture
def db_session(db_env):
    """A real DB session against the fresh test database, schema created."""
    import database
    database.init_db()
    session = database.SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(db_env):
    """
    A TestClient wired to the real FastAPI app, against the fresh test DB.
    Re-triggers the same startup sequence main.py's on_startup runs in
    production (init_db + register_all_handlers), scoped to this test's
    isolated database and a freshly cleared event bus.
    """
    from fastapi.testclient import TestClient
    import database
    database.init_db()

    from ai.orchestrator.executive import register_all_handlers
    register_all_handlers()

    from main import app
    return TestClient(app)
