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
from routers import orders, inventory, health, webhooks, auth, menu, analytics, reservations, ai
from middleware.timing import TimingMiddleware

logger = logging.getLogger(__name__)

# ── Sentry (optional) ─────────────────────────────────────────────────────────
try:
    import sentry_sdk
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.2)
except Exception:
    pass

# ── Rate limiting (optional — gracefully skipped if slowapi not installed) ────
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    limiter = Limiter(key_func=get_remote_address)
    _slowapi_available = True
except ImportError:
    _slowapi_available = False
    logger.warning("[Startup] slowapi not installed — rate limiting disabled. Run: pip install slowapi")

app = FastAPI(title="Restaurant Agent API", version="2.0.0")

if _slowapi_available:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    # 1. Init DB tables
    from database import init_db
    try:
        init_db()
        print("[OK] Database tables initialised")
    except Exception as e:
        print(f"[WARN] DB init deferred: {e}")

    # 2. Wire the event bus — THIS WAS MISSING.
    #    Without this call, all orchestrator handlers were registered as
    #    functions but never subscribed to the bus. Events fired into void.
    try:
        from ai.orchestrator.executive import register_all_handlers
        register_all_handlers()
        print("[OK] Orchestrator event handlers registered")
    except Exception as e:
        print(f"[WARN] Orchestrator registration failed: {e}")

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
        scheduler.add_job(
            _run_slow_day_check_job,
            CronTrigger(hour=11, minute=0),  # 14:00 EAT — matches the function's own gate (only fires after 14:00 EAT)
            id="slow_day_check",
            replace_existing=True,
        )

        scheduler.start()
        print("[OK] Scheduler started (morning briefing: 07:00 EAT)")
    except ImportError:
        print("[WARN] APScheduler not installed — scheduled jobs disabled. Run: pip install apscheduler")
    except Exception as e:
        print(f"[WARN] Scheduler failed to start: {e}")


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
        from datetime import datetime
        from database import SessionLocal
        from events.bus import emit_async, EventType
        import models

        db = SessionLocal()
        try:
            now = datetime.utcnow()
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


def _run_slow_day_check_job():
    try:
        from database import SessionLocal
        from ai.whatsapp.brain import run_slow_day_check
        run_slow_day_check(SessionLocal)
    except Exception as exc:
        logger.error(f"[Slow Day Check] Scheduler job failed: {exc}")


# ── CORS ──────────────────────────────────────────────────────────────────────
# Real Vercel production domain is included as a fallback default (not just
# localhost) — found 2026-07-07 that a misconfigured/placeholder CORS_ORIGINS
# on Railway silently breaks frontend login with a browser-side "network
# error" (CORS preflight is rejected before the request body is ever sent,
# so the backend logs show nothing — this is invisible without checking the
# preflight response directly). CORS_ORIGINS env var still takes priority
# when set correctly; this is a safety net, not a replacement for setting it.
default_origins = (
    "http://localhost:3000,http://127.0.0.1:3000,http://192.168.100.4:3000,"
    "https://restaurant-agent-o38i.vercel.app"
)
cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", default_origins).split(",")]
logger.info(f"[CORS] Allowed origins: {cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(TimingMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(inventory.router)
app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(analytics.router)
app.include_router(reservations.router)
app.include_router(ai.router)


@app.get("/")
def read_root():
    return {"service": "Restaurant Agent API", "version": "2.0.0", "status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
