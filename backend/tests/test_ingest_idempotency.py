"""Re-running ingest must be safe (integration design contract)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from integration.ingest import ingest, payload_sha256
from integration.models import Base, MirrorEvent


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_first_ingest_inserts(db) -> None:
    action = ingest(db, source_system_id=1, entity="orders", source_id="A1",
                    source_version="v1", payload={"id": "A1", "total": 500})
    assert action == "inserted"


def test_identical_version_is_skipped(db) -> None:
    ingest(db, source_system_id=1, entity="orders", source_id="A1", source_version="v1", payload={"id": "A1"})
    action = ingest(db, source_system_id=1, entity="orders", source_id="A1", source_version="v1", payload={"id": "A1"})
    assert action == "skipped"
    assert db.query(MirrorEvent).count() == 2


def test_new_version_supersedes_and_history_is_kept(db) -> None:
    ingest(db, source_system_id=1, entity="orders", source_id="A1", source_version="v1", payload={"total": 500})
    action = ingest(db, source_system_id=1, entity="orders", source_id="A1", source_version="v2", payload={"total": 600})
    assert action == "superseded"
    assert db.query(MirrorEvent).count() == 2
    assert db.query(MirrorEvent).first().raw == {"total": 500}, "history must not be overwritten"


def test_hash_is_stable_across_key_order() -> None:
    assert payload_sha256({"a": 1, "b": 2}) == payload_sha256({"b": 2, "a": 1})


def test_repeated_retries_do_not_forget_the_applied_version(db):
    actions = [ingest(db, source_system_id=1, entity="orders", source_id="A1",
                      source_version="v1", payload={"total": 500}) for _ in range(5)]
    assert actions == ["inserted", "skipped", "skipped", "skipped", "skipped"]
    corrected = ingest(db, source_system_id=1, entity="orders", source_id="A1",
                       source_version="v2", payload={"total": 600})
    assert corrected == "superseded"
    assert db.query(MirrorEvent).filter_by(action="inserted").count() == 1
    assert db.query(MirrorEvent).first().raw == {"total": 500}
