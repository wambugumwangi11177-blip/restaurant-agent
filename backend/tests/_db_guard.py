"""Fail-closed guard: refuse to run tests against a non-test database.

Why this exists (AUD-24): tests/conftest.py documents that a module importing
the app before the db_env fixture binds engine/SessionLocal to whatever
DATABASE_URL is in backend/.env -- which is the live Neon production pooler.
The mitigation was a hand-maintained 3-module reload list. This guard replaces
intent with a check that runs before any app import.
"""
from __future__ import annotations

from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"sqlite"})
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", ""})


def assert_test_database(url: str, *, allow: bool = False) -> None:
    """Raise RuntimeError unless `url` is provably a test database."""
    if allow:
        return
    if not url:
        raise RuntimeError(
            "DATABASE_URL is unset; refusing to run tests (fail-closed). "
            "Set TEST_DATABASE_URL to a local or sqlite database."
        )
    parsed = urlparse(url)
    scheme = parsed.scheme.split("+")[0].lower()
    if scheme in _ALLOWED_SCHEMES:
        return
    host = (parsed.hostname or "").lower()
    if host in _LOCAL_HOSTS:
        return
    raise RuntimeError(
        "Refusing to run tests against a non-test database host "
        f"({host!r}). Set TEST_DATABASE_URL to a local/sqlite database, or set "
        "AUDIT_ALLOW_NON_TEST_DB=1 to override (the override is recorded in the audit log)."
    )
