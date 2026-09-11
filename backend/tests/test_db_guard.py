"""Fail-closed database guard for the test suite (AUD-24)."""
from __future__ import annotations

import pytest

from tests._db_guard import assert_test_database


def test_sqlite_url_is_allowed() -> None:
    assert_test_database("sqlite:///./test.db")


def test_sqlite_plus_driver_is_allowed() -> None:
    assert_test_database("sqlite+pysqlite:///:memory:")


def test_localhost_postgres_is_allowed() -> None:
    assert_test_database("postgresql://user:pw@localhost:5432/restaurant_test")


def test_remote_production_pooler_is_refused() -> None:
    with pytest.raises(RuntimeError, match="Refusing to run tests"):
        assert_test_database(
            "postgresql://user:pw@ep-patient-cloud-anksz8fw-pooler.c-6.us-east-1.aws.neon.tech/db"
        )


def test_empty_url_is_refused() -> None:
    with pytest.raises(RuntimeError, match="fail-closed"):
        assert_test_database("")


def test_explicit_override_is_honoured() -> None:
    assert_test_database("postgresql://user:pw@prod.example.com/db", allow=True)
