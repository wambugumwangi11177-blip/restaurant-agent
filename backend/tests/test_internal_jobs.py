"""Scheduled work must be triggerable — and provable — from outside.

Thirteen jobs run inside the web process via APScheduler. They die with the
container, restart silently on the next boot, and leave no record of whether
last night's run happened. The escalation sweep is the sharpest case: it polls
every five minutes so an unacknowledged critical alert is caught inside its
15-minute window, and a redeploy at the wrong moment means it does not run.
Nobody finds out, because the thing it protects is the case where a human is
already not responding.

This endpoint moves the trigger out, not the logic.
"""
from __future__ import annotations

import pytest

_KEY = "test-internal-job-key"


@pytest.fixture(autouse=True)
def _job_key(monkeypatch):
    monkeypatch.setenv("INTERNAL_JOB_KEY", _KEY)


def _post(client, job, key=_KEY):
    headers = {"x-job-key": key} if key is not None else {}
    return client.post(f"/internal/jobs/{job}", headers=headers)


# ── Auth ─────────────────────────────────────────────────────────────────────

def test_no_key_is_rejected(client):
    assert _post(client, "outbox_sweep", key=None).status_code == 401


def test_wrong_key_is_rejected(client):
    assert _post(client, "outbox_sweep", key="not-the-key").status_code == 401


def test_unset_key_fails_closed(client, monkeypatch):
    """An endpoint that runs privileged work must never be open because a
    variable is missing."""
    monkeypatch.setenv("INTERNAL_JOB_KEY", "")
    assert _post(client, "outbox_sweep").status_code == 401


# ── Running ──────────────────────────────────────────────────────────────────

def test_a_job_runs_and_reports_what_happened(client):
    res = _post(client, "outbox_sweep")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["job"] == "outbox_sweep"
    assert body["status"] == "completed"
    assert isinstance(body["duration_ms"], int)


def test_an_unknown_job_is_a_404_not_a_silent_success(client):
    assert _post(client, "not_a_job").status_code == 404


def test_a_failing_job_returns_500_so_the_scheduler_retries(client, monkeypatch):
    """Swallowing a failure into a 200 would recreate, in a new place, exactly
    the silent failure this endpoint exists to remove."""
    import main

    def _boom():
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(main, "_run_outbox_sweep_job", _boom)
    res = _post(client, "outbox_sweep")
    assert res.status_code == 500
    assert "database unreachable" in res.json()["detail"]


def test_a_job_already_running_is_not_started_twice(client, monkeypatch):
    """Several of these send WhatsApp messages. A scheduler retrying on timeout
    must not send them again."""
    from routers import jobs

    jobs._running.add("morning_briefing")
    try:
        assert _post(client, "morning_briefing").status_code == 409
    finally:
        jobs._running.discard("morning_briefing")


def test_the_running_set_is_cleared_after_a_failure(client, monkeypatch):
    """A job that raised must not stay marked as running forever."""
    import main
    from routers import jobs

    monkeypatch.setattr(main, "_run_outbox_sweep_job",
                        lambda: (_ for _ in ()).throw(RuntimeError("x")))
    _post(client, "outbox_sweep")
    assert "outbox_sweep" not in jobs._running


# ── Listing ──────────────────────────────────────────────────────────────────

def test_listing_names_every_job_and_the_scheduler_state(client):
    res = client.get("/internal/jobs", headers={"x-job-key": _KEY})
    assert res.status_code == 200
    body = res.json()
    assert len(body["jobs"]) == 14
    assert "escalation_sweep" in body["jobs"]
    assert isinstance(body["in_process_scheduler_enabled"], bool)


def test_every_listed_job_has_a_real_implementation(client):
    """A name in the list with no function behind it would 500 at 3am on a
    schedule nobody is watching."""
    import main
    from routers.jobs import _FUNCTION_FOR, _JOB_NAMES

    assert set(_FUNCTION_FOR) == set(_JOB_NAMES)
    for job, fn_name in _FUNCTION_FOR.items():
        assert callable(getattr(main, fn_name, None)), f"{job} -> {fn_name} missing"


# ── The scheduler switch ─────────────────────────────────────────────────────

def test_the_in_process_scheduler_is_on_by_default(monkeypatch):
    """A deploy that silently stopped running scheduled work because a variable
    was missing would be worse than running it twice."""
    import main
    monkeypatch.delenv("ENABLE_INTERNAL_SCHEDULER", raising=False)
    assert main._internal_scheduler_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "FALSE"])
def test_the_scheduler_can_be_handed_over(monkeypatch, value):
    import main
    monkeypatch.setenv("ENABLE_INTERNAL_SCHEDULER", value)
    assert main._internal_scheduler_enabled() is False


# ── Mirror reconciliation ────────────────────────────────────────────────────

@pytest.fixture
def _mirror_tables(db_env):
    import database
    from integration.models import Base as IntegrationBase
    IntegrationBase.metadata.create_all(bind=database.engine)


def test_reconciliation_is_clean_when_every_record_is_accounted_for(
        client, db_session, _mirror_tables, monkeypatch):
    monkeypatch.setenv("MACSOFT_API_KEY", "k")
    monkeypatch.setenv("MACSOFT_RESTAURANT_ID", "1")
    import models
    db_session.add(models.Tenant(id=1, name="T"))
    db_session.flush()
    db_session.add(models.Restaurant(id=1, tenant_id=1, name="R"))
    db_session.commit()

    client.post("/webhooks/macsoft/data", headers={"x-api-key": "k"}, json={
        "entity": "sale", "records": [
            {"source_id": "A-1", "version": 1, "total": "100.00", "date": "2026-09-19"}]})

    res = _post(client, "mirror_reconcile")
    assert res.status_code == 200, res.text
    assert res.json()["result"]["status"] == "clean"


def test_a_mirrored_record_with_no_link_is_a_mismatch(
        client, db_session, _mirror_tables, monkeypatch):
    """A record that fell between the mirror and the domain tables was silently
    dropped — the exact failure class that let MacSoft data land perfectly and
    change nothing on screen."""
    monkeypatch.setenv("MACSOFT_API_KEY", "k")
    from integration.models import MirrorEvent, SourceSystem

    source = SourceSystem(slug="macsoft-prod", display_name="MacSoft",
                          mechanism="webhook", is_authoritative=1)
    db_session.add(source)
    db_session.flush()
    db_session.add(MirrorEvent(
        source_system_id=source.id, entity="sale", source_id="ORPHAN-1",
        source_version="1", payload_sha256="x", action="inserted", raw={}))
    db_session.commit()

    res = _post(client, "mirror_reconcile")
    assert res.status_code == 200, res.text
    assert res.json()["result"]["status"] == "mismatch"


def test_reconciliation_is_clean_with_no_sources_at_all(client, _mirror_tables):
    """Nothing connected yet is not a failure."""
    res = _post(client, "mirror_reconcile")
    assert res.status_code == 200
    assert res.json()["result"]["status"] == "clean"
