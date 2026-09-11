from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from integration.models import Base
from integration.reconcile import checksum_ids, reconcile


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def test_equal_sets_are_clean(db) -> None:
    r = reconcile(db, source_system_id=1, entity="orders", source_ids=["1", "2"], mirror_ids=["2", "1"])
    assert r.status == "clean"


def test_missing_id_is_a_mismatch_not_clean(db) -> None:
    r = reconcile(db, source_system_id=1, entity="orders", source_ids=["1", "2"], mirror_ids=["1"])
    assert r.status == "mismatch"
    assert "missing=1" in r.detail


def test_extra_id_is_a_mismatch(db) -> None:
    r = reconcile(db, source_system_id=1, entity="orders", source_ids=["1"], mirror_ids=["1", "9"])
    assert r.status == "mismatch"


def test_checksum_is_order_independent() -> None:
    assert checksum_ids(["b", "a"]) == checksum_ids(["a", "b"])


def test_empty_source_with_nonempty_mirror_is_a_mismatch(db) -> None:
    r = reconcile(db, source_system_id=1, entity="orders", source_ids=[], mirror_ids=["1"])
    assert r.status == "mismatch", "an empty source must never silently look clean"