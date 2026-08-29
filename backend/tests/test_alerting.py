"""
alerting.py — critical-error alerting (audit remediation, Module 13).

No alerting existed in code at all before this. These tests prove: nothing
fires with ALERT_WEBHOOK_URL unset (the default, graceful-no-op posture
every other optional integration in this codebase already uses), a spike
(N errors within the window) does fire exactly once — not per error — and a
cooldown prevents re-firing on every subsequent request during a sustained
outage.
"""

import time

import alerting


def _reset_state(monkeypatch, threshold=3, window=60, cooldown=300):
    monkeypatch.setattr(alerting, "_SPIKE_THRESHOLD", threshold)
    monkeypatch.setattr(alerting, "_SPIKE_WINDOW_SECONDS", window)
    monkeypatch.setattr(alerting, "_COOLDOWN_SECONDS", cooldown)
    alerting._recent_errors.clear()
    alerting._last_alert_at = 0.0


def test_noop_when_webhook_url_unset(monkeypatch):
    monkeypatch.setattr(alerting, "ALERT_WEBHOOK_URL", None)
    _reset_state(monkeypatch, threshold=1)

    fired = []
    monkeypatch.setattr(alerting, "_send_webhook_async", lambda *a, **k: fired.append(a))

    alerting.record_error_and_maybe_alert("GET", "/x", RuntimeError("boom"))

    assert fired == []
    assert len(alerting._recent_errors) == 0  # doesn't even track when unconfigured


def test_fires_once_a_spike_is_reached_not_before(monkeypatch):
    monkeypatch.setattr(alerting, "ALERT_WEBHOOK_URL", "https://example.com/webhook")
    _reset_state(monkeypatch, threshold=3)

    fired = []
    monkeypatch.setattr(alerting, "_send_webhook_async", lambda *a, **k: fired.append(a))

    alerting.record_error_and_maybe_alert("GET", "/x", RuntimeError("1"))
    assert fired == []
    alerting.record_error_and_maybe_alert("GET", "/x", RuntimeError("2"))
    assert fired == []
    alerting.record_error_and_maybe_alert("GET", "/x", RuntimeError("3"))
    assert len(fired) == 1  # exactly on the 3rd, matching threshold=3


def test_old_errors_outside_the_window_dont_count_toward_the_spike(monkeypatch):
    monkeypatch.setattr(alerting, "ALERT_WEBHOOK_URL", "https://example.com/webhook")
    _reset_state(monkeypatch, threshold=3, window=60)

    fired = []
    monkeypatch.setattr(alerting, "_send_webhook_async", lambda *a, **k: fired.append(a))

    # Two errors "long ago" (outside the window), pruned on the next call.
    old = time.time() - 120
    alerting._recent_errors.extend([old, old])

    alerting.record_error_and_maybe_alert("GET", "/x", RuntimeError("recent"))

    assert fired == []  # only 1 error actually inside the window, below threshold=3


def test_cooldown_prevents_refiring_on_every_subsequent_error(monkeypatch):
    monkeypatch.setattr(alerting, "ALERT_WEBHOOK_URL", "https://example.com/webhook")
    _reset_state(monkeypatch, threshold=2, cooldown=300)

    fired = []
    monkeypatch.setattr(alerting, "_send_webhook_async", lambda *a, **k: fired.append(a))

    alerting.record_error_and_maybe_alert("GET", "/x", RuntimeError("1"))
    alerting.record_error_and_maybe_alert("GET", "/x", RuntimeError("2"))
    assert len(fired) == 1

    # A sustained outage keeps producing errors — must not re-fire every time.
    for _ in range(10):
        alerting.record_error_and_maybe_alert("GET", "/x", RuntimeError("more"))
    assert len(fired) == 1
