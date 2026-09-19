"""
MacSoft inbound data push: the client's POS is the system of record and refused
direct database access, so this endpoint is the whole integration surface.

The behaviour that matters is that accepting a record and STORING it are the
same event. An earlier version of this endpoint authenticated, logged the
payload and returned {"status": "received"} without writing anything — MacSoft
would have pushed a week of trade, seen 200s, and we would have held nothing.
Every test here exists to stop that regressing.
"""
from __future__ import annotations

import pytest

_KEY = "test-macsoft-key"


@pytest.fixture(autouse=True)
def _macsoft_key(monkeypatch):
    monkeypatch.setenv("MACSOFT_API_KEY", _KEY)


@pytest.fixture(autouse=True)
def _mirror_tables(db_env):
    """
    The mirror tables live on integration/models.py's own declarative Base, so
    database.init_db() (models.Base only) does not create them — in production
    alembic migration 046 does, which the Dockerfile runs on every boot.
    """
    import database
    from integration.models import Base as IntegrationBase
    IntegrationBase.metadata.create_all(bind=database.engine)


def _post(client, body, key=_KEY):
    headers = {"x-api-key": key} if key is not None else {}
    return client.post("/webhooks/macsoft/data", json=body, headers=headers)


def _events(db_session):
    from integration.models import MirrorEvent
    return db_session.query(MirrorEvent).order_by(MirrorEvent.id).all()


def _sale(source_id="INV-001", version=1, total=125050):
    return {
        "entity": "sale",
        "records": [{
            "source_id": source_id,
            "version": version,
            "occurred_at": "2026-09-19T14:30:11+03:00",
            "total_cents": total,
        }],
    }


# ── Auth ─────────────────────────────────────────────────────────────────────

def test_missing_key_is_rejected(client):
    assert _post(client, _sale(), key=None).status_code == 401


def test_wrong_key_is_rejected(client):
    assert _post(client, _sale(), key="not-the-key").status_code == 401


def test_unset_key_fails_closed(client, monkeypatch):
    """No configured key means nothing to compare against — reject, never trust."""
    monkeypatch.setenv("MACSOFT_API_KEY", "")
    assert _post(client, _sale()).status_code == 401


def test_rejected_request_stores_nothing(client, db_session):
    _post(client, _sale(), key="not-the-key")
    assert _events(db_session) == []


# ── The core guarantee: a 200 means it is stored ─────────────────────────────

def test_accepted_record_is_actually_persisted(client, db_session):
    res = _post(client, _sale())
    assert res.status_code == 200
    assert res.json()["inserted"] == 1

    rows = _events(db_session)
    assert len(rows) == 1
    assert rows[0].source_id == "INV-001"
    assert rows[0].action == "inserted"
    # The payload itself is retained verbatim: we have not seen MacSoft's real
    # format yet, so the mirror is the staging area we map from later.
    assert rows[0].raw["total_cents"] == 125050


def test_response_never_claims_more_than_was_stored(client, db_session):
    body = {"entity": "sale", "records": [
        {"source_id": f"INV-{i}", "version": 1, "total_cents": 100} for i in range(5)
    ]}
    res = _post(client, body)
    assert res.json()["received"] == 5
    assert res.json()["inserted"] == 5
    assert len(_events(db_session)) == 5


# ── Idempotency: retries must be free ────────────────────────────────────────

def test_same_record_twice_stores_one_and_reports_the_duplicate(client, db_session):
    first = _post(client, _sale())
    second = _post(client, _sale())

    assert first.json()["inserted"] == 1
    assert second.json()["inserted"] == 0
    assert second.json()["duplicates_ignored"] == 1

    actions = [e.action for e in _events(db_session)]
    assert actions == ["inserted", "skipped"], (
        "both attempts are audited, but only one is a real insert"
    )


def test_higher_version_supersedes_rather_than_overwrites(client, db_session):
    _post(client, _sale(version=1, total=125050))
    res = _post(client, _sale(version=2, total=99900))

    assert res.json()["updated"] == 1
    rows = _events(db_session)
    assert [e.action for e in rows] == ["inserted", "superseded"]
    # History survives: the original figure is still recoverable.
    assert rows[0].raw["total_cents"] == 125050
    assert rows[1].raw["total_cents"] == 99900


# ── Shape tolerance: MacSoft sends their format, we adapt ────────────────────

def test_bare_array_is_accepted(client, db_session):
    res = _post(client, [{"id": "T-1", "version": 1}, {"id": "T-2", "version": 1}])
    assert res.status_code == 200
    assert len(_events(db_session)) == 2


def test_single_bare_object_is_accepted(client, db_session):
    res = _post(client, {"invoice_no": "INV-9", "updated_at": "2026-09-19T10:00:00+03:00"})
    assert res.status_code == 200
    rows = _events(db_session)
    assert len(rows) == 1
    assert rows[0].source_id == "INV-9"


def test_alternative_container_keys_are_found(client, db_session):
    res = _post(client, {"entity": "sale", "transactions": [{"id": "X-1", "version": 1}]})
    assert res.status_code == 200
    assert len(_events(db_session)) == 1


def test_records_without_id_still_store_and_are_flagged(client, db_session):
    """
    We fall back to a content hash so nothing is dropped, but we say so in the
    response rather than hiding it — that number is how we learn MacSoft's real
    field names.
    """
    res = _post(client, {"entity": "sale", "records": [{"amount": 500, "till": "3"}]})
    assert res.status_code == 200
    assert res.json()["records_without_id_or_version"] == 1
    assert len(_events(db_session)) == 1


def test_empty_batch_is_a_400_not_a_silent_success(client):
    res = _post(client, {"entity": "sale", "records": []})
    assert res.status_code == 400


def test_oversized_batch_is_refused(client, db_session):
    body = {"entity": "sale", "records": [{"id": str(i), "version": 1} for i in range(501)]}
    assert _post(client, body).status_code == 413
    assert _events(db_session) == []


def test_malformed_json_is_a_400(client):
    res = client.post(
        "/webhooks/macsoft/data",
        content=b"{not json",
        headers={"x-api-key": _KEY, "Content-Type": "application/json"},
    )
    assert res.status_code == 400


# ── Data protection ──────────────────────────────────────────────────────────

def test_payload_contents_never_reach_the_application_log(client, caplog):
    """
    The previous implementation logged the whole payload at INFO. Restaurant
    transactions carry customer names and phone numbers; application logs are
    not covered by our retention or erasure path (Kenya DPA 2019), so the
    payload must stay in the mirror table and out of the log stream.
    """
    import logging
    caplog.set_level(logging.DEBUG)

    _post(client, {"entity": "sale", "records": [{
        "source_id": "INV-77", "version": 1,
        "customer_name": "Wanjiku Kamau",
        "customer_phone": "254712345678",
        "total_cents": 4500,
    }]})

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "Wanjiku Kamau" not in logged
    assert "254712345678" not in logged
    # The operational counts we DO want are still there.
    assert "entity=sale" in logged


# ── Batch transaction semantics ──────────────────────────────────────────────

def test_record_repeated_inside_one_batch_stores_once(client, db_session):
    """
    The batch commits once at the end, and SessionLocal is autoflush=False, so
    without an explicit flush per row the dedupe lookup would not see earlier
    rows of the same batch and a repeat would insert twice. MacSoft batching
    a record that also appeared earlier in the same push is exactly the case.
    """
    body = {"entity": "sale", "records": [
        {"source_id": "INV-DUP", "version": 1, "total_cents": 100},
        {"source_id": "INV-DUP", "version": 1, "total_cents": 100},
    ]}
    res = _post(client, body)
    assert res.json()["inserted"] == 1
    assert res.json()["duplicates_ignored"] == 1
    assert [e.action for e in _events(db_session)] == ["inserted", "skipped"]


def test_correction_later_in_the_same_batch_supersedes(client, db_session):
    body = {"entity": "sale", "records": [
        {"source_id": "INV-FIX", "version": 1, "total_cents": 100},
        {"source_id": "INV-FIX", "version": 2, "total_cents": 250},
    ]}
    res = _post(client, body)
    assert res.json()["inserted"] == 1
    assert res.json()["updated"] == 1
    rows = _events(db_session)
    assert [e.action for e in rows] == ["inserted", "superseded"]
    assert rows[1].raw["total_cents"] == 250


def test_a_failing_batch_stores_nothing(client, db_session, monkeypatch):
    """
    All-or-nothing. A partly-applied batch that still returned an error would
    make MacSoft's retry ambiguous; a clean rollback makes resending free.
    """
    import routers.webhooks as wh

    calls = {"n": 0}
    real = wh.ingest

    def exploding(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("database went away mid-batch")
        return real(*args, **kwargs)

    monkeypatch.setattr(wh, "ingest", exploding)

    body = {"entity": "sale", "records": [
        {"source_id": f"INV-{i}", "version": 1, "total_cents": 100} for i in range(5)
    ]}
    assert _post(client, body).status_code == 500
    assert _events(db_session) == [], "the two rows written before the failure must be rolled back"


def test_large_batch_commits_once(client, db_session, monkeypatch):
    """Guards the batching itself: 500 records must not mean 500 commits."""
    import database
    real_commit = database.SessionLocal.class_.commit
    commits = {"n": 0}

    def counting_commit(self, *a, **k):
        commits["n"] += 1
        return real_commit(self, *a, **k)

    monkeypatch.setattr(database.SessionLocal.class_, "commit", counting_commit)

    body = {"entity": "sale", "records": [
        {"source_id": f"B-{i}", "version": 1, "total_cents": i} for i in range(500)
    ]}
    res = _post(client, body)
    assert res.json()["inserted"] == 500
    assert len(_events(db_session)) == 500
    # One for the source_systems row on first use, one for the batch. The point
    # is that it does not scale with record count.
    assert commits["n"] <= 3, f"expected a handful of commits, got {commits['n']}"
