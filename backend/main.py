"""
backend/main.py
────────────────
Application entry point.

FIXES:
  - register_all_handlers() is now called at startup so the event bus
    actually has subscribers. Previously the orchestrator was wired but
    never activated — events fired into the void.
  - Added APScheduler for the WhatsApp morning briefing cron job.
  - Rate limiting middleware added (slowapi).
"""

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from logging_config import configure_logging
from routers import orders, inventory, health, webhooks, auth, menu, analytics, reservations, ai, export, flags, events, billing, enterprise, staff, stock_custody, suppliers, purchase_orders, notifications, support, tables, attendance, fraud, cash_reconciliation, restaurants
from middleware.timing import TimingMiddleware
from middleware.security_headers import SecurityHeadersMiddleware
from middleware.body_limit import BodySizeLimitMiddleware
from middleware.correlation import CorrelationIdMiddleware

# Install structured logging before anything else logs.
configure_logging()
logger = logging.getLogger(__name__)

# ── Sentry (optional) ─────────────────────────────────────────────────────────
try:
    import sentry_sdk
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.2)
except Exception:
    pass

# ── Rate limiting ───────────────────────────────────────────────────────────
# limiter now lives in rate_limit.py so routers can import it too — see that
# file's docstring for why (it was configured here but never applied to any
# endpoint, since routers importing from main.py would be circular).
from rate_limit import limiter, SLOWAPI_AVAILABLE
from time_utils import utcnow

app = FastAPI(title="Restaurant Agent API", version="2.0.0")

if SLOWAPI_AVAILABLE:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Global exception handler ─────────────────────────────────────────────────
# Catches anything a route/dependency didn't handle itself (FastAPI's own
# HTTPException/RequestValidationError handling still takes precedence —
# this only fires for genuinely unexpected exceptions) so a client always
# gets a clean JSON error instead of whatever the default framework/server
# error page would otherwise return.
from fastapi import Request
from fastapi.responses import JSONResponse


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    from alerting import record_error_and_maybe_alert
    record_error_and_maybe_alert(request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    # 0. Fail-closed config validation — in production, refuse to boot with a
    #    security-critical misconfig (e.g. an unauthenticated M-Pesa callback).
    from startup_checks import enforce_startup_checks
    enforce_startup_checks()

    # 1. Init DB tables
    from database import init_db
    try:
        init_db()
        logger.info("[OK] Database tables initialised")
    except Exception as e:
        logger.warning(f"[WARN] DB init deferred: {e}")

    # 2. Wire the event bus — THIS WAS MISSING.
    #    Without this call, all orchestrator handlers were registered as
    #    functions but never subscribed to the bus. Events fired into void.
    try:
        from ai.orchestrator.executive import register_all_handlers
        register_all_handlers()
        logger.info("[OK] Orchestrator event handlers registered")
    except Exception as e:
        logger.warning(f"[WARN] Orchestrator registration failed: {e}")

    # 2b. Second, independent event-bus subscriber: in-app + push
    #     notifications (ai/notify.py), alongside (not instead of) the
    #     WhatsApp handlers above. A failure here must never block boot or
    #     affect the WhatsApp pipeline — same posture as 2.
    try:
        from ai.orchestrator.push_notifier import register_push_handlers
        register_push_handlers()
        logger.info("[OK] Push/in-app notification handlers registered")
    except Exception as e:
        logger.warning(f"[WARN] Push notification handler registration failed: {e}")

    # 3. Schedule morning WhatsApp briefing (07:00 EAT = 04:00 UTC)
    _start_scheduler()


def _start_scheduler():
    """Start APScheduler for the morning briefing cron job."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BackgroundScheduler(timezone="UTC")

        scheduler.add_job(
            _send_all_morning_briefings,
            CronTrigger(hour=4, minute=0),   # 07:00 EAT
            id="morning_briefing",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Also check for late purchase orders every 2 hours
        scheduler.add_job(
            _check_late_purchase_orders,
            CronTrigger(hour="*/2"),
            id="po_late_check",
            replace_existing=True,
        )

        # ai/whatsapp/brain.py defines run_stock_check and run_slow_day_check
        # with docstrings describing exactly this schedule, but neither was
        # ever actually registered — found 2026-07-07 auditing the event/
        # scheduler orchestration end to end. Both are real, already-tested
        # functions (run_stock_check wraps get_critical_stock_alerts, already
        # exercised via the WhatsApp STOCK command this session).
        scheduler.add_job(
            _run_stock_check_job,
            CronTrigger(hour="8-22/2"),  # every 2 hours, 08:00-22:00 EAT window
            id="stock_check",
            replace_existing=True,
        )
        # Directive 016: theoretical-vs-actual usage variance, once daily
        # after most of the day's covers — deliberately NOT on the 2-hourly
        # cadence above. A shift-level summary, not a per-movement ping (see
        # ai/stock_custody.py and the stock-loss-prevention skill).
        scheduler.add_job(
            _run_variance_check_job,
            CronTrigger(hour=18, minute=0),  # 21:00 EAT
            id="variance_check",
            replace_existing=True,
        )
        scheduler.add_job(
            _run_slow_day_check_job,
            CronTrigger(hour=11, minute=0),  # 14:00 EAT — matches the function's own gate (only fires after 14:00 EAT)
            id="slow_day_check",
            replace_existing=True,
        )
        # Directive 018: par-level reorder check, once daily early — a draft
        # PO should be ready for the owner to approve before/during opening,
        # not discovered mid-shift.
        scheduler.add_job(
            _run_reorder_check_job,
            CronTrigger(hour=3, minute=0),   # 06:00 EAT
            id="reorder_check",
            replace_existing=True,
        )
        # Same-day reservation reminders to cut no-shows. Once per day so it never
        # re-sends (there is no per-reservation reminded flag) — see
        # brain.run_reservation_reminders.
        scheduler.add_job(
            _run_reservation_reminders_job,
            CronTrigger(hour=7, minute=0),   # 10:00 EAT
            id="reservation_reminders",
            replace_existing=True,
        )

        # Phase 5 continuous-learning loop — once daily, early, before the
        # morning briefing so the accuracy/drift numbers it feeds are fresh.
        scheduler.add_job(
            _run_learning_cycle_job,
            CronTrigger(hour=2, minute=0),   # 05:00 EAT
            id="learning_cycle",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Weekly unattended strategist review — off by default (see
        # autonomous_strategist in feature_flags.py); registered unconditionally
        # so a redeploy-free env flip turns it on. Monday, after learning_cycle
        # has refreshed the accuracy numbers the strategist reads about itself.
        scheduler.add_job(
            _run_strategist_review_job,
            CronTrigger(day_of_week="mon", hour=5, minute=0),   # 08:00 EAT Monday
            id="strategist_review",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Sprint 3 — suspicious-transaction (fraud) scan. Every 2h, same
        # cadence as po_late_check/stock_check above — frequent enough to
        # catch a same-shift burst, not so frequent it re-scans the same
        # 24h window pointlessly.
        scheduler.add_job(
            _run_fraud_check_job,
            CronTrigger(hour="*/2"),
            id="fraud_check",
            replace_existing=True,
        )

        # Sprint 2 — manager escalation sweep. Every 5 min, not daily/hourly
        # like everything else above: the whole point is catching an
        # unacknowledged critical alert within its 15-minute timeout, so the
        # poll interval has to be short relative to that.
        from apscheduler.triggers.interval import IntervalTrigger
        scheduler.add_job(
            _run_escalation_sweep_job,
            IntervalTrigger(minutes=5),
            id="escalation_sweep",
            replace_existing=True,
        )

        # Audit remediation, Tier 2 item 5 — retry failed event-bus deliveries
        # (see events/bus.py's NotificationOutbox). Same 5-min cadence as
        # escalation_sweep above, for the same reason: this is the one job in
        # this scheduler where "someone didn't get notified" degrades with
        # every extra minute of delay, unlike the once-daily analytics jobs.
        scheduler.add_job(
            _run_outbox_sweep_job,
            IntervalTrigger(minutes=5),
            id="outbox_sweep",
            replace_existing=True,
        )

        # Audit remediation, Tier 2 item 6 — purge AgentAuditLog rows older
        # than 90 days, closing the gap docs/compliance-matrix.md flagged as
        # open ("Append-only (no auto-purge today) — reconcile vs DPA
        # '90-day rolling'"). Once daily, off-peak.
        scheduler.add_job(
            _run_audit_log_purge_job,
            CronTrigger(hour=1, minute=30),  # 04:30 EAT
            id="audit_log_purge",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("[OK] Scheduler started (morning briefing: 07:00 EAT)")
    except ImportError:
        logger.warning("[WARN] APScheduler not installed — scheduled jobs disabled. Run: pip install apscheduler")
    except Exception as e:
        logger.warning(f"[WARN] Scheduler failed to start: {e}")


def _send_all_morning_briefings():
    """Send WhatsApp morning briefing to every active restaurant owner."""
    # Was a near-exact duplicate of ai.whatsapp.brain.run_morning_briefing —
    # same DRY pattern already fixed elsewhere this session (routers/deps.py).
    # Delegates to the real implementation instead of maintaining two copies.
    try:
        from database import SessionLocal
        from ai.whatsapp.brain import run_morning_briefing
        run_morning_briefing(SessionLocal)
    except Exception as exc:
        logger.error(f"[Briefing] Scheduler job failed: {exc}")


def _check_late_purchase_orders():
    """Emit PURCHASE_ORDER_LATE events for overdue POs."""
    try:
        from database import SessionLocal
        from events.bus import emit_async, EventType
        import models

        db = SessionLocal()
        try:
            now = utcnow()
            late_pos = (
                db.query(models.PurchaseOrder)
                .filter(
                    models.PurchaseOrder.status.in_(["PENDING", "SENT"]),
                    models.PurchaseOrder.expected_at < now,
                )
                .all()
            )
            for po in late_pos:
                days_late = (now - po.expected_at).days
                emit_async(EventType.PURCHASE_ORDER_LATE, {
                    "restaurant_id": po.restaurant_id,
                    "supplier_id": po.supplier_id,
                    "supplier_name": po.supplier.name if po.supplier else "",
                    "item_name": po.inventory_item.item_name if po.inventory_item else "",
                    "days_late": days_late,
                })
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"[PO Check] Failed: {exc}")


def _run_stock_check_job():
    try:
        from database import SessionLocal
        from ai.whatsapp.brain import run_stock_check
        run_stock_check(SessionLocal)
    except Exception as exc:
        logger.error(f"[Stock Check] Scheduler job failed: {exc}")


def _run_variance_check_job():
    """Directive 016: compute the theoretical-vs-actual variance report for
    every restaurant and emit STOCK_VARIANCE_FLAGGED for any with at least
    one item over threshold. Emitting only when there's something to flag
    (rather than one event per restaurant regardless) is what keeps this a
    real signal instead of a daily no-op ping."""
    try:
        from database import SessionLocal
        from events.bus import emit_async, EventType
        from ai.stock_custody import flagged_items
        import models

        db = SessionLocal()
        try:
            for restaurant in db.query(models.Restaurant).all():
                items = flagged_items(db, restaurant.id, hours=24)
                if not items:
                    continue
                emit_async(EventType.STOCK_VARIANCE_FLAGGED, {
                    "restaurant_id": restaurant.id,
                    "items": [
                        {
                            "item_name": i.item_name,
                            "variance_pct": i.variance_pct,
                            "theoretical": i.theoretical_usage,
                            "actual": i.actual_usage,
                        }
                        for i in items
                    ],
                })
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"[Variance Check] Scheduler job failed: {exc}")


def _run_fraud_check_job():
    """Sprint 3: run the suspicious-transaction report for every restaurant,
    emit SUSPICIOUS_TRANSACTION_FLAGGED only for ones with at least one
    flagged pattern — mirrors _run_variance_check_job's "alert on the report,
    not a daily no-op ping" shape exactly."""
    try:
        from database import SessionLocal
        from events.bus import emit_async, EventType
        from ai.fraud.detection import compute_fraud_report
        import models

        db = SessionLocal()
        try:
            for restaurant in db.query(models.Restaurant).all():
                report = compute_fraud_report(db, restaurant.id)
                if not report or not report.flagged_transactions:
                    continue
                emit_async(EventType.SUSPICIOUS_TRANSACTION_FLAGGED, {
                    "restaurant_id": restaurant.id,
                    "flagged_transactions": [
                        {
                            "transaction_id": t.transaction_id,
                            "reason": t.reason,
                            "amount": t.amount,
                        }
                        for t in report.flagged_transactions
                    ],
                })
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"[Fraud Check] Scheduler job failed: {exc}")


def _run_slow_day_check_job():
    try:
        from database import SessionLocal
        from ai.whatsapp.brain import run_slow_day_check
        run_slow_day_check(SessionLocal)
    except Exception as exc:
        logger.error(f"[Slow Day Check] Scheduler job failed: {exc}")


def _run_reorder_check_job():
    try:
        from database import SessionLocal
        from ai.whatsapp.brain import run_reorder_check
        run_reorder_check(SessionLocal)
    except Exception as exc:
        logger.error(f"[Reorder Check] Scheduler job failed: {exc}")


def _run_reservation_reminders_job():
    try:
        from database import SessionLocal
        from ai.whatsapp.brain import run_reservation_reminders
        run_reservation_reminders(SessionLocal)
    except Exception as exc:
        logger.error(f"[Reservation Reminders] Scheduler job failed: {exc}")


def _run_learning_cycle_job():
    try:
        from database import SessionLocal
        from ai.learning.cycle import run_learning_cycle
        run_learning_cycle(SessionLocal)
    except Exception as exc:
        logger.error(f"[Learning Cycle] Scheduler job failed: {exc}")


def _run_strategist_review_job():
    try:
        from database import SessionLocal
        from ai.strategist import run_strategist_review
        run_strategist_review(SessionLocal)
    except Exception as exc:
        logger.error(f"[Strategist Review] Scheduler job failed: {exc}")


def _run_escalation_sweep_job():
    try:
        from database import SessionLocal
        from ai.escalation import run_escalation_sweep
        run_escalation_sweep(SessionLocal)
    except Exception as exc:
        logger.error(f"[Escalation Sweep] Scheduler job failed: {exc}")


def _run_outbox_sweep_job():
    try:
        from database import SessionLocal
        from events.bus import run_outbox_sweep
        run_outbox_sweep(SessionLocal)
    except Exception as exc:
        logger.error(f"[Outbox Sweep] Scheduler job failed: {exc}")


def _run_audit_log_purge_job():
    try:
        from database import SessionLocal
        from ai.audit import purge_old_audit_logs
        purge_old_audit_logs(SessionLocal)
    except Exception as exc:
        logger.error(f"[Audit Log Purge] Scheduler job failed: {exc}")