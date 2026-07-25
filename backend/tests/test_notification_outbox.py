"""
events/bus.py's NotificationOutbox — audit remediation, Tier 2 item 5.

Before this, emit() log-and-dropped a failed handler call with zero
persistence, and emit_async()'s fire-and-forget daemon thread lost anything
in flight on a restart. These tests prove: a failing handler's call is
recorded (not the successful ones — those stay purely in-process), the sweep
retries and can flip a row to delivered once the underlying problem clears,
and a row exceeding max_attempts is dead-lettered instead of retried forever.
"""

import models
from events.bus import emit, subscribe, clear_handlers, sweep_outbox, EventType


def _row(db_session):
    return db_session.query(models.NotificationOutbox).first()


def test_emit_persists_outbox_row_only_on_handler_failure(db_session):
    clear_handlers()

    def ok_handler(payload):
        pass

    def failing_handler(payload):
        raise RuntimeError("simulated delivery failure")

    subscribe(EventType.ORDER_CREATED, ok_handler)
    subscribe(EventType.ORDER_CREATED, failing_handler)

    emit(EventType.ORDER_CREATED, {"order_id": 1})

    rows = db_session.query(models.NotificationOutbox).all()
    assert len(rows) == 1
    assert rows[0].handler_name == "failing_handler"
    assert rows[0].status == "pending"
    assert rows[0].attempts == 1
    assert "simulated delivery failure" in rows[0].last_error


def test_emit_writes_nothing_when_all_handlers_succeed(db_session):
    clear_handlers()

    def ok_handler(payload):
        pass

    subscribe(EventType.ORDER_CREATED, ok_handler)
    emit(EventType.ORDER_CREATED, {"order_id": 1})

    assert db_session.query(models.NotificationOutbox).count() == 0


def test_sweep_retries_and_marks_delivered_once_handler_recovers(db_session):
    clear_handlers()
    call_count = {"n": 0}

    def flaky_handler(payload):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("first attempt fails")
        # Second call (the retry, driven by sweep_outbox) succeeds.

    subscribe(EventType.ORDER_CREATED, flaky_handler)
    emit(EventType.ORDER_CREATED, {"order_id": 1})

    row = _row(db_session)
    assert row.status == "pending"
    assert row.attempts == 1

    result = sweep_outbox()

    assert result["delivered"] == 1
    db_session.refresh(row)
    assert row.status == "delivered"
    assert row.attempts == 2


def test_sweep_dead_letters_after_max_attempts(db_session):
    clear_handlers()

    def always_fails(payload):
        raise RuntimeError("permanent failure")

    subscribe(EventType.ORDER_CREATED, always_fails)
    emit(EventType.ORDER_CREATED, {"order_id": 1})

    row = _row(db_session)
    row.attempts = 5  # simulate 4 prior sweep retries, all failed
    db_session.commit()

    result = sweep_outbox(max_attempts=5)

    assert result["dead"] == 1
    db_session.refresh(row)
    assert row.status == "dead"


def test_sweep_dead_letters_when_handler_no_longer_registered(db_session):
    clear_handlers()

    def vanishing_handler(payload):
        raise RuntimeError("fails once, then we unsubscribe it")

    subscribe(EventType.ORDER_CREATED, vanishing_handler)
    emit(EventType.ORDER_CREATED, {"order_id": 1})

    clear_handlers()  # simulate the handler no longer being registered

    result = sweep_outbox()

    assert result["dead"] == 1
    row = _row(db_session)
    assert row.status == "dead"
    assert "no longer registered" in row.last_error
