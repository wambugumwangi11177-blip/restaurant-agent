"""
backend/alerting.py
──────────────────────
Critical-error alerting (audit remediation, Module 13). No alerting existed
in code at all — docs/operations-and-reliability.md described this as a
still-TBD, Sentry-dashboard-only concern. This is the code half: a generic
webhook POST (Slack-compatible payload shape — also works with most
"incoming webhook" integrations: Discord, Teams-via-connector, a custom
endpoint) fired when unhandled exceptions spike, not on every single one.

Gated behind ALERT_WEBHOOK_URL, unset by default — graceful no-op exactly
like this codebase's existing Twilio/VAPID/SMTP pattern (see webhooks.py,
notify.py, email_utils.py) until someone actually sets one up. No new
dependency: uses `requests`, already a transitive dependency via httpx/other
HTTP-calling modules in this codebase (mpesa_client.py).

Fires on a SPIKE (N unhandled exceptions within a rolling window), not per
occurrence — same "alert on the pattern, not every instance" posture as
ai/fraud/detection.py and the stock-variance/discrepancy events, chosen for
the same reason: a single transient 500 is normal at any real scale and
per-exception alerting would just be noise nobody reads. A cooldown after
firing prevents re-alerting every request during a sustained outage.
"""

import logging
import os
import threading
import time
from collections import deque

logger = logging.getLogger("alerting")

ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL")
_SPIKE_THRESHOLD = int(os.getenv("ALERT_ERROR_SPIKE_THRESHOLD", "5"))
_SPIKE_WINDOW_SECONDS = int(os.getenv("ALERT_ERROR_SPIKE_WINDOW_SECONDS", "60"))
_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))

_lock = threading.Lock()
_recent_errors: deque = deque()
_last_alert_at: float = 0.0


def record_error_and_maybe_alert(method: str, path: str, exc: Exception) -> None:
    """Call from the unhandled-exception handler for every 500. No-ops
    immediately if ALERT_WEBHOOK_URL isn't set — the counting itself is
    cheap, but there's no reason to even maintain the window if nothing
    could ever fire from it."""
    if not ALERT_WEBHOOK_URL:
        return

    now = time.time()
    should_fire = False
    error_count = 0

    with _lock:
        _recent_errors.append(now)
        while _recent_errors and _recent_errors[0] < now - _SPIKE_WINDOW_SECONDS:
            _recent_errors.popleft()
        error_count = len(_recent_errors)

        global _last_alert_at
        if error_count >= _SPIKE_THRESHOLD and (now - _last_alert_at) >= _COOLDOWN_SECONDS:
            _last_alert_at = now
            should_fire = True

    if should_fire:
        _send_webhook_async(error_count, method, path, exc)


def _send_webhook_async(error_count: int, method: str, path: str, exc: Exception) -> None:
    def _send():
        try:
            import requests
            text = (
                f":rotating_light: Chakula: {error_count} unhandled errors in the last "
                f"{_SPIKE_WINDOW_SECONDS}s. Latest: `{method} {path}` -> {type(exc).__name__}: {exc}"
            )
            requests.post(ALERT_WEBHOOK_URL, json={"text": text}, timeout=5)
        except Exception:
            # A failed alert must never itself raise anywhere — this already
            # runs off the request path specifically so it can't.
            logger.warning("[Alerting] Failed to deliver error-spike webhook", exc_info=True)

    threading.Thread(target=_send, daemon=True).start()
