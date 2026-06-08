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
  - Added Proactive Executive Agent initialization for agentic capabilities.
"""

import os
import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from routers import orders, inventory, health, webhooks, auth, menu, analytics, reservations, ai
from middleware.timing import TimingMiddleware
from middleware.security import SecurityHeadersMiddleware, RequestSizeLimitMiddleware
from sqlalchemy.orm import Session
from database import SessionLocal, get_db

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
    from middleware.rate_limit_enhanced import (
        get_rate_limit_key, custom_rate_limit_exceeded_handler
    )
    limiter = Limiter(
        key_func=get_rate_limit_key,
        default_limits=["100 per hour"]
    )
    _slowapi_available = True
    # Set custom exception handler for logging
    _rate_limit_exceeded_handler = custom_rate_limit_exceeded_handler
except ImportError:
    _slowapi_available = False
    logger.warning("[Startup] slowapi not installed — rate limiting disabled. Run: pip install slowapi")

app = FastAPI(title="Restaurant Agent API", version="2.1.0", lifespan=lifespan)  # Version bump for agentic features

if _slowapi_available:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Define a global scheduler variable for access in shutdown
scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
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

    # 3. Initialize Proactive Executive Agent for agentic capabilities
    try:
        db = SessionLocal()
        try:
            from ai.orchestrator.proactive_executive import initialize_proactive_executive
            initialize_proactive_executive(db)
            print("[OK] Proactive Executive Agent initialized")
        finally:
            db.close()
    except Exception as e:
        print(f"[WARN] Proactive Executive initialization failed: {e}")

    # 4. Schedule morning WhatsApp briefing (07:00 EAT = 04:00 UTC)
    global scheduler
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

        scheduler.start()
        print("[OK] Scheduler started (morning briefing: 07:00 EAT)")
    except ImportError:
        print("[WARN] APScheduler not installed — scheduled jobs disabled. Run: pip install apscheduler")
        scheduler = None
    except Exception as e:
        print(f"[WARN] Scheduler failed to start: {e}")
        scheduler = None

    yield  # Application runs here

    # Shutdown logic
    if scheduler:
        try:
            scheduler.shutdown()
            print("[OK] Scheduler shut down")
        except Exception as e:
            print(f"[WARN] Scheduler shutdown failed: {e}")


def _send_all_morning_briefings():
    """Send WhatsApp morning briefing to every active restaurant owner."""
    try:
        from database import SessionLocal
        from ai.whatsapp.brain import compose_morning_briefing
        from ai.whatsapp import send_whatsapp_message
        import models

        db = SessionLocal()
        try:
            restaurants = db.query(models.Restaurant).all()
            for restaurant in restaurants:
                owner_phone = os.getenv(f"OWNER_PHONE_{restaurant.id}", os.getenv("OWNER_PHONE", ""))
                if not owner_phone:
                    continue
                try:
                    msg = compose_morning_briefing(db, restaurant.id)
                    send_whatsapp_message(
                        owner_phone, msg, db=db,
                        restaurant_id=restaurant.id,
                        message_type="morning_briefing",
                    )
                    logger.info(f"[Briefing] Sent to restaurant {restaurant.id}")
                except Exception as exc:
                    logger.error(f"[Briefing] Failed for restaurant {restaurant.id}: {exc}")
        finally:
            db.close()
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


# ── Proactive Executive Endpoints ────────────────────────────────────────────

@app.get("/agentic/goals", tags=["Agentic"])
def get_active_goals(db: Session = Depends(get_db)):
    """Get all active goals from the Proactive Executive Agent"""
    try:
        from ai.orchestrator.proactive_executive import get_proactive_executive
        executive = get_proactive_executive()
        goals = executive.get_active_goals()
        return {"goals": goals, "count": len(goals)}
    except Exception as e:
        logger.error(f"Failed to get active goals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agentic/goals", tags=["Agentic"])
@app.post("/agentic/goals", tags=["Agentic"])
def propose_goal(
    goal_type: str = Body(...),
    description: str = Body(...),
    success_criteria: str = Body(...),
    priority: int = Body(1),
    db: Session = Depends(get_db)
):
    """Propose a new goal for the Proactive Executive Agent to pursue"""
    try:
        import json
        from ai.orchestrator.proactive_executive import get_proactive_executive, GoalType
        executive = get_proactive_executive()

        # Validate goal type
        try:
            goal_type_enum = GoalType(goal_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid goal type. Valid types: {[gt.value for gt in GoalType]}")

        # Parse success_criteria from JSON string
        try:
            success_criteria_dict = json.loads(success_criteria)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="success_criteria must be a valid JSON string")

        goal_id = executive.propose_goal(
            goal_type=goal_type_enum,
            description=description,
            success_criteria=success_criteria_dict,
            priority=priority
        )
        return {"goal_id": goal_id, "status": "proposed", "message": "Goal proposed successfully"}
    except Exception as e:
        logger.error(f"Failed to propose goal: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def activate_goal(goal_id: str, db: Session = Depends(get_db)):
    """Activate a proposed goal"""
    try:
        from ai.orchestrator.proactive_executive import get_proactive_executive
        executive = get_proactive_executive()
        success = executive.activate_goal(goal_id)
        if success:
            return {"goal_id": goal_id, "status": "activated", "message": "Goal activated successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to activate goal - may not exist or already active")
    except Exception as e:
        logger.error(f"Failed to activate goal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agentic/goals/{goal_id}", tags=["Agentic"])
def get_goal_details(goal_id: str, db: Session = Depends(get_db)):
    """Get detailed information about a specific goal"""
    try:
        from ai.orchestrator.proactive_executive import get_proactive_executive
        executive = get_proactive_executive()
        details = executive.get_goal_details(goal_id)
        if details:
            return details
        else:
            raise HTTPException(status_code=404, detail="Goal not found")
    except Exception as e:
        logger.error(f"Failed to get goal details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agentic/agents", tags=["Agentic"])
def get_registered_agents(db: Session = Depends(get_db)):
    """Get all registered agents in the system"""
    try:
        from ai.orchestrator.proactive_executive import get_proactive_executive
        executive = get_proactive_executive()
        if executive.communication_hub:
            # This is a simplified version - in reality we'd query the agent registry directly
            return {"message": "Agent registry query not yet implemented in this endpoint"}
        else:
            return {"message": "Communication hub not initialized"}
    except Exception as e:
        logger.error(f"Failed to get registered agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── CORS ────────────────────────────────────────────────────────────────────

default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://192.168.100.4:3000"
cors_origins = os.getenv("CORS_ORIGINS", default_origins).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add security middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware, max_size=5 * 1024 * 1024)  # 5MB limit

app.add_middleware(TimingMiddleware)

# ── Routers ─────────────────────────────────────────────────────────────────

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
    return {"service": "Restaurant Agent API", "version": "2.1.0", "status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)