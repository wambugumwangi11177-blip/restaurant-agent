"""
tests/conftest.py
─────────────────
Tests run against a real PostgreSQL (full-text search, the append-only audit
trigger, row locks and constraints only exist there — SQLite would test a
different system). A throwaway database is created per test session, migrated
with Alembic (so the migration itself is under test), and every table is
truncated between tests.

Point TEST_DATABASE_ADMIN_URL at a server you can create databases on; the
default matches the local dev server and the CI service container. Any
non-local host is refused so a test run can never touch a real database.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text

ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL", "postgresql+psycopg2://cos:cos@localhost:5432/postgres")
_host = urlparse(ADMIN_URL.replace("+psycopg2", "")).hostname
if _host not in {"localhost", "127.0.0.1", "postgres"}:
    raise RuntimeError(f"Refusing to run tests against non-local database host {_host!r}")

TEST_DB = f"cos_test_{uuid.uuid4().hex[:8]}"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"

# Must be set before anything imports app.* (settings are cached on first read).
os.environ["DATABASE_URL"] = TEST_URL
os.environ["ENV"] = "test"
os.environ["PUBLIC_BASE_URL"] = "https://os.example.test"
os.environ["TWILIO_AUTH_TOKEN"] = "test-twilio-token"
for _k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY", "TWILIO_ACCOUNT_SID",
           "TWILIO_WHATSAPP_FROM", "SMTP_HOST", "SMTP_FROM"):
    os.environ.pop(_k, None)

STRONG_PASSWORD = "Correct-Horse-9-Battery"


@pytest.fixture(scope="session", autouse=True)
def database():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    from alembic import command
    from alembic.config import Config

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(cfg, "head")
    yield
    from app import db as app_db

    app_db.engine().dispose()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(autouse=True)
def clean_tables(database):
    yield
    from app import db as app_db

    with app_db.engine().begin() as c:
        tables = [r[0] for r in c.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'"))]
        c.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def db():
    from app.db import session_factory

    s = session_factory()()
    yield s
    s.rollback()
    s.close()


def _login(client, email: str, password: str = STRONG_PASSWORD, **extra) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password, **extra})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def make_workspace(client, db):
    """Create a workspace + founder; returns dict(ws, user, token, h)."""

    def _make(slug: str = "acme", email: str | None = None, phone: str | None = None) -> dict:
        from app.kernel.bootstrap import create_workspace_with_founder

        email = email or f"founder@{slug}.example.com"
        ws, user = create_workspace_with_founder(db, slug=slug, name=slug.title(), email=email,
                                                 full_name="Founder " + slug, password=STRONG_PASSWORD, phone=phone)
        db.commit()
        token = _login(client, email)
        return {"ws": ws, "user": user, "token": token, "h": {"Authorization": f"Bearer {token}"}}

    return _make


@pytest.fixture
def add_member(client):
    """Founder adds a member with a role; returns their auth header."""

    def _add(founder_h: dict, role: str, email: str, phone: str | None = None) -> dict:
        r = client.post("/api/v1/members", headers=founder_h, json={
            "email": email, "full_name": role.title(), "role": role, "password": STRONG_PASSWORD, "phone": phone})
        assert r.status_code == 201, r.text
        return {"Authorization": f"Bearer {_login(client, email)}"}

    return _add
