"""The owner is told the real delivery state of the MacSoft source.

Before this, /vibanda/reports carried a hardcoded "Prototype data · Macsoft is
not connected" line and /overview/today asserted integration_verified: False
unconditionally. Both would have stayed wrong after the integration went live,
because only a deploy could correct them.
"""
import datetime

import pytest

import models
from integration.models import MirrorEvent, ReconcileRun, SourceSystem
from routers.overview import _source_connection
from routers.webhooks import MACSOFT_SOURCE_SLUG


@pytest.fixture
def mirror_tables(db_env):
    """integration/models.py has its own declarative Base, so database.init_db()
    does not create these — alembic 046 does, which the Dockerfile runs on boot.
    Deliberately NOT autouse: one test below needs them absent."""
    import database
    from integration.models import Base as IntegrationBase
    IntegrationBase.metadata.create_all(bind=database.engine)


@pytest.fixture
def source(mirror_tables, db_session):
    row = SourceSystem(slug=MACSOFT_SOURCE_SLUG, display_name="MacSoft",
                       mechanism="webhook", is_authoritative=1)
    db_session.add(row)
    db_session.commit()
    return row


def _event(source_id: int, received_at: datetime.datetime, ref: str) -> MirrorEvent:
    return MirrorEvent(source_system_id=source_id, entity="sale", source_id=ref,
                       source_version="1", payload_sha256="0" * 64,
                       action="inserted", received_at=received_at)


def test_no_source_row_means_awaiting_not_broken(mirror_tables, db_session):
    state = _source_connection(db_session)
    assert state["state"] == "awaiting_first_delivery"
    assert state["records"] == 0
    assert state["last_received_at"] is None
    assert state["reconciled"] is False


def test_registered_source_with_no_records_is_still_awaiting(db_session, source):
    """The source row is created on first use, so its mere existence proves
    nothing about delivery."""
    assert _source_connection(db_session)["state"] == "awaiting_first_delivery"


def test_delivered_records_report_receiving_with_the_latest_timestamp(db_session, source):
    older = datetime.datetime(2026, 9, 18, 10, 0, 0)
    newer = datetime.datetime(2026, 9, 19, 11, 30, 0)
    db_session.add(_event(source.id, older, "INV-1"))
    db_session.add(_event(source.id, newer, "INV-2"))
    db_session.commit()

    state = _source_connection(db_session)
    assert state["state"] == "receiving"
    assert state["records"] == 2
    assert state["last_received_at"] == newer.isoformat()


def test_delivered_is_not_reconciled(db_session, source):
    """Records arriving proves delivery, never completeness."""
    db_session.add(_event(source.id, datetime.datetime(2026, 9, 19, 9, 0, 0), "INV-1"))
    db_session.commit()
    assert _source_connection(db_session)["reconciled"] is False


def test_a_mismatched_reconcile_run_does_not_count_as_reconciled(db_session, source):
    db_session.add(_event(source.id, datetime.datetime(2026, 9, 19, 9, 0, 0), "INV-1"))
    db_session.add(ReconcileRun(source_system_id=source.id, entity="sale",
                                source_count=5, mirror_count=1,
                                source_checksum="a", mirror_checksum="b",
                                status="mismatch"))
    db_session.commit()
    assert _source_connection(db_session)["reconciled"] is False


def test_a_clean_reconcile_run_is_what_verifies_the_integration(db_session, source):
    db_session.add(_event(source.id, datetime.datetime(2026, 9, 19, 9, 0, 0), "INV-1"))
    db_session.add(ReconcileRun(source_system_id=source.id, entity="sale",
                                source_count=1, mirror_count=1,
                                source_checksum="a", mirror_checksum="a",
                                status="clean"))
    db_session.commit()
    assert _source_connection(db_session)["reconciled"] is True


def test_unreadable_mirror_says_unknown_not_not_connected(db_session):
    """Migration 046 missing or the database down must not read as 'no data'.

    No mirror_tables fixture here, so the tables genuinely do not exist and the
    real database error is raised — not a stub standing in for one.
    """
    state = _source_connection(db_session)
    assert state["state"] == "unavailable"
    assert state["records"] is None
    assert state["reconciled"] is False


def test_a_failed_mirror_read_leaves_the_session_usable(db_session):
    """The savepoint's whole job.

    On PostgreSQL a failed statement aborts the transaction, so swallowing the
    error without a savepoint would make every later query in the same /today
    request fail too — the owner would get a 500 for a missing migration in a
    table none of the figures come from.
    """
    assert _source_connection(db_session)["state"] == "unavailable"

    restaurant = models.Restaurant(name="Still writable")
    db_session.add(restaurant)
    db_session.commit()
    assert db_session.query(models.Restaurant).filter_by(name="Still writable").one()


def test_overview_today_carries_the_state_and_a_matching_notice(mirror_tables, client):
    import secrets

    resp = client.post("/api/v1/auth/register", json={
        "email": f"src{secrets.token_hex(4)}@example.com",
        "password": "CorrectHorseBattery1!", "tenant_name": "Vibanda Village",
    })
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    r = client.get("/api/v1/overview/today", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()

    provenance = body["data_provenance"]
    assert provenance["source_connection"]["state"] == "awaiting_first_delivery"
    assert provenance["integration_verified"] is False
    assert "Macsoft has delivered nothing yet" in provenance["notice"]
    assert body["source_status"]["integration"]["state"] == "awaiting_first_delivery"
    # The old copy asserted a fact about the integration that no deploy kept true.
    assert "prototype" not in provenance["notice"].lower()
