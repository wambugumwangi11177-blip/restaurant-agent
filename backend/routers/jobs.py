"""Scheduled work, triggered from outside the process.

WHY
Thirteen jobs run inside the web process, started by main.py's
_start_scheduler(). APScheduler holds them in memory, which means all thirteen
share four properties: they die with the container, they restart silently on
the next boot, a failure is a log line nobody reads, and nothing anywhere
records whether last night's run happened. The escalation sweep is the sharpest
case — it polls every five minutes so an unacknowledged critical alert is caught
inside its 15-minute window, and a redeploy at the wrong moment means it simply
does not run. Nobody finds out, because the thing it protects is the case where
a human is already not responding.

WHAT THIS IS, AND IS NOT
This moves the TRIGGER out, not the logic. The business rules stay in the
repo where they are version-controlled and tested; n8n (or cron, or any
scheduler) calls this endpoint, the app does the work, and the caller keeps the
execution history, the retry and the alert on failure. Rebuilding any of this
as nodes in a visual tool would trade a tested guarantee for a diagram.

FAIL CLOSED
INTERNAL_JOB_KEY unset means there is nothing to compare against, so every
request is rejected — the same posture as the MacSoft push key. An endpoint
that runs privileged work must never be open because a variable is missing.

SAFE TO CALL TWICE
Several of these send WhatsApp messages. A scheduler that retries on timeout
would send them again, so a job already running returns 409 rather than
starting a second copy. Within one process this is exact; across replicas it is
not, which is why the deploy runs a single worker (see the Dockerfile) and why
the jobs themselves carry their own per-subject cooldowns.
"""
from __future__ import annotations

import hmac
import logging
import threading
import time
from typing import Callable

from fastapi import APIRouter, Header, HTTPException

from rate_limit import limiter
from fastapi import Request
import os

logger = logging.getLogger("jobs")

router = APIRouter(prefix="/internal/jobs", tags=["internal"])

# Job name -> the function in main.py that does the work. Names are the same
# ids APScheduler registers them under, so the two views agree.
_JOB_NAMES = (
    "morning_briefing",
    "po_late_check",
    "stock_check",
    "variance_check",
    "slow_day_check",
    "reorder_check",
    "reservation_reminders",
    "learning_cycle",
    "strategist_review",
    "fraud_check",
    "escalation_sweep",
    "outbox_sweep",
    "audit_log_purge",
    "mirror_reconcile",
)

_FUNCTION_FOR = {
    "morning_briefing": "_send_all_morning_briefings",
    "po_late_check": "_check_late_purchase_orders",
    "stock_check": "_run_stock_check_job",
    "variance_check": "_run_variance_check_job",
    "slow_day_check": "_run_slow_day_check_job",
    "reorder_check": "_run_reorder_check_job",
    "reservation_reminders": "_run_reservation_reminders_job",
    "learning_cycle": "_run_learning_cycle_job",
    "strategist_review": "_run_strategist_review_job",
    "fraud_check": "_run_fraud_check_job",
    "escalation_sweep": "_run_escalation_sweep_job",
    "outbox_sweep": "_run_outbox_sweep_job",
    "audit_log_purge": "_run_audit_log_purge_job",
    "mirror_reconcile": "_run_mirror_reconcile_job",
}

_running: set[str] = set()
_lock = threading.Lock()


def _verify_key(supplied: str | None) -> None:
    expected = (os.getenv("INTERNAL_JOB_KEY") or "").strip()
    if not expected:
        logger.error("[jobs] INTERNAL_JOB_KEY is not set — refusing every request")
        raise HTTPException(status_code=401, detail="Job trigger is not configured")
    if not supplied or not hmac.compare_digest(supplied.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid job key")


def _resolve(job_name: str) -> Callable:
    """The job function, imported at call time.

    main.py imports this router, so importing main at module scope would be
    circular. Lazy import inside the handler is the pattern used throughout
    this codebase for exactly that reason.
    """
    import main
    fn = getattr(main, _FUNCTION_FOR[job_name], None)
    if fn is None or not callable(fn):
        raise HTTPException(status_code=500,
                            detail=f"Job '{job_name}' has no implementation")
    return fn


@router.get("")
async def list_jobs(x_job_key: str | None = Header(default=None)):
    """The jobs this endpoint can run, and whether the in-process scheduler is
    also running them. Both at once is not an error — it is what a cautious
    cutover looks like — but it is worth being able to see."""
    _verify_key(x_job_key)
    scheduler_on = (os.getenv("ENABLE_INTERNAL_SCHEDULER") or "true").strip().lower() \
        not in ("0", "false", "no", "off")
    with _lock:
        running = sorted(_running)
    return {
        "jobs": list(_JOB_NAMES),
        "in_process_scheduler_enabled": scheduler_on,
        "currently_running": running,
    }


@router.post("/{job_name}")
@limiter.limit("60/minute")
async def run_job(request: Request, job_name: str,
                  x_job_key: str | None = Header(default=None)):
    """Run one job now, synchronously, and report what happened.

    Synchronous on purpose: the caller's whole value here is knowing whether
    the run succeeded. Returning 202 and finishing in a background thread would
    hand back the same blindness this endpoint exists to remove.

    A failure returns 500 with the error, so the scheduler's own retry and
    alerting fire. Swallowing it into a 200 would recreate the silent failure
    in a new place.
    """
    _verify_key(x_job_key)
    if job_name not in _FUNCTION_FOR:
        raise HTTPException(status_code=404, detail=f"Unknown job '{job_name}'")

    with _lock:
        if job_name in _running:
            raise HTTPException(
                status_code=409,
                detail=f"'{job_name}' is already running — not starting a second copy",
            )
        _running.add(job_name)

    fn = _resolve(job_name)
    started = time.monotonic()
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 — surfaced, not swallowed
        logger.exception("[jobs] %s failed", job_name)
        raise HTTPException(
            status_code=500,
            detail=f"{job_name} failed: {type(exc).__name__}: {exc}",
        ) from exc
    finally:
        with _lock:
            _running.discard(job_name)

    duration_ms = round((time.monotonic() - started) * 1000)
    logger.info("[jobs] %s completed in %sms", job_name, duration_ms)
    return {
        "job": job_name,
        "status": "completed",
        "duration_ms": duration_ms,
        # Most job functions return None; the ones that report counts
        # (learning_cycle, outbox_sweep) return a dict worth passing on.
        "result": result if isinstance(result, (dict, list, int, str)) else None,
    }
