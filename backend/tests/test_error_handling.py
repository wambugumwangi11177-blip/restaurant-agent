"""
backend/tests/test_error_handling.py
──────────────────────────────────────
The error-handling spine: unhandled exceptions are correlatable, and optional
paths that fail are countable instead of silent.

Two defects these lock down:

1. The only registered exception handler was RateLimitExceeded, so any other
   unhandled error returned a bare {"detail": "Internal Server Error"} with no
   correlation id in the BODY. The id existed in the X-Request-ID header, but a
   user reporting a failure can't read response headers, so a reported 500 could
   not be tied back to its log lines.

2. `except Exception: pass` with no logger — most acutely seven times in
   ai/roi/savings.py, where each one could zero out a contributor to a
   customer-facing "money saved" figure with no trace anywhere.
"""

import pytest
from fastapi import APIRouter

import metrics
from observability import degraded


# ── Unhandled exceptions ─────────────────────────────────────────────────────


@pytest.fixture
def boom_client(db_env):
    """
    The real app plus one route that always raises.

    Built directly rather than via conftest's `client` fixture because
    `raise_server_exceptions` must be passed at construction — TestClient hands
    it to its transport there, so setting the attribute afterwards has no
    effect. False makes TestClient return the exception handler's response
    instead of re-raising, i.e. behave like a real HTTP client.
    """
    from fastapi.testclient import TestClient
    import database

    database.init_db()

    from ai.orchestrator.executive import register_all_handlers
    register_all_handlers()

    from main import app

    router = APIRouter()

    # include_in_schema=False keeps this out of the OpenAPI document, which
    # tests/test_versioning_and_sessions.py asserts against.
    @router.get("/__test__/boom", include_in_schema=False)
    def _boom():
        raise RuntimeError("intentional test explosion")

    # `app` is a module-level singleton shared by every test in the process, so
    # the route must be removed again — otherwise each use of this fixture
    # appends another copy and leaks into unrelated tests' view of the app.
    original_routes = list(app.router.routes)
    app.include_router(router)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.router.routes[:] = original_routes


def test_unhandled_exception_returns_500_with_request_id(boom_client):
    resp = boom_client.get("/__test__/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == "Internal Server Error"

    # The correlation id must be in the BODY, not only the header — that is the
    # whole point, since a user can quote a body field and not a header.
    assert body.get("request_id")
    assert body["request_id"] != "-"


def test_request_id_in_body_matches_header(boom_client):
    resp = boom_client.get("/__test__/boom")
    assert resp.json()["request_id"] == resp.headers.get("X-Request-ID")


def test_inbound_request_id_is_echoed_on_error(boom_client):
    """A caller-supplied id survives all the way to the error body, so a chain of
    services can share one id across a failure."""
    resp = boom_client.get("/__test__/boom", headers={"X-Request-ID": "trace-me-123"})
    assert resp.json()["request_id"] == "trace-me-123"


def test_error_body_leaks_no_exception_detail(boom_client):
    """The client gets an id to quote; the operator gets the traceback in logs.
    The exception text must not travel to the client."""
    text = boom_client.get("/__test__/boom").text
    assert "intentional test explosion" not in text
    assert "RuntimeError" not in text
    assert "Traceback" not in text


def test_unhandled_exception_is_logged_with_traceback(boom_client, caplog):
    import logging

    with caplog.at_level(logging.ERROR):
        boom_client.get("/__test__/boom")

    # Returning a response from the handler suppresses the re-raise that would
    # otherwise produce uvicorn's traceback, so the handler must log it itself —
    # without this, a 500 would be LESS visible than before the handler existed.
    assert any("Unhandled exception" in r.message for r in caplog.records)
    assert any(r.exc_info for r in caplog.records)


# ── Degradation is counted, not swallowed ────────────────────────────────────


def test_degraded_increments_component_counter():
    before = metrics._degradations_total.get("test.component", 0)
    degraded("test.component", ValueError("nope"))
    assert metrics._degradations_total["test.component"] == before + 1


def test_degraded_component_appears_in_metrics_output():
    degraded("test.rendered_component", ValueError("nope"))
    rendered = metrics.render()
    assert "app_degradations_total" in rendered
    assert 'app_degradations_total{component="test.rendered_component"}' in rendered


def test_degraded_logs_a_warning_with_traceback(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        degraded("test.logged", ValueError("kaboom"), restaurant_id=7)

    record = next(r for r in caplog.records if "test.logged" in r.getMessage())
    assert record.levelno == logging.WARNING
    assert record.exc_info is not None
    # Structured context is attached for the JSON formatter to emit.
    assert record.component == "test.logged"
    assert record.restaurant_id == 7


def test_degraded_never_raises():
    """A failure in the failure handler must not replace the original error with
    a more confusing one."""
    class Hostile(Exception):
        def __str__(self):
            raise RuntimeError("even my repr explodes")

    degraded("test.hostile", Hostile())  # must not raise


def test_metrics_label_values_are_escaped():
    degraded('test.quo"ted', ValueError("x"))
    assert '\\"' in metrics.render()


# ── ROI is wired to the helper, not to `pass` ────────────────────────────────


def test_roi_savings_reports_degradation_instead_of_silent_zero(db_session, monkeypatch):
    """A failing ROI contributor must leave a trace. Before this, the category
    silently contributed 0 and the dashboard showed a confidently wrong number."""
    import ai.roi.savings as savings

    def _explode(*a, **kw):
        raise RuntimeError("inventory predictor down")

    monkeypatch.setattr(
        "ai.inventory_predictor.get_inventory_predictions", _explode, raising=False
    )

    before = metrics._degradations_total.get("roi.inventory_waste", 0)
    result = savings.get_roi_savings(db_session, restaurant_id=1)

    # Still degrades rather than crashing — the original intent is preserved.
    assert isinstance(result, dict)
    assert metrics._degradations_total.get("roi.inventory_waste", 0) > before


def test_savings_module_has_no_silent_pass_handlers():
    """Regression guard: this module is the reason the helper exists."""
    import pathlib

    source = pathlib.Path(__file__).resolve().parents[1] / "ai" / "roi" / "savings.py"
    lines = source.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines[:-1]):
        if line.strip().startswith("except"):
            assert lines[i + 1].strip() != "pass", (
                f"silent exception handler reintroduced at savings.py:{i + 1}"
            )
