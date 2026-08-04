from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
# from database import get_db # Assuming db setup is done or will be done
import os
import logging

logger = logging.getLogger("health")

router = APIRouter(
    prefix="/health",
    tags=["health"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def health_check():
    return {"status": "ok", "message": "Service is healthy"}

from sqlalchemy import text
from database import get_db

@router.get("/db")
async def db_health_check(db: Session = Depends(get_db)):
    try:
        # Execute a simple query to check connection
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        # Log the error (Sentry will catch it if configured)
        logger.error(f"Database connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        )


@router.get("/notifications")
async def notifications_health_check(db: Session = Depends(get_db)):
    """
    Is the outbound notification chain alive? Point an uptime monitor here.

    Notifications are the product's daily heartbeat (morning briefing, stock
    alerts, reservation reminders) but they degrade silently — a send with no
    Twilio config returns not_configured and is logged, never raised. `/health`
    and `/health/db` both stay green through a total notification outage.

    Returns 200 for ok/degraded and 503 for down, so a monitor pages on "nothing
    can be delivered at all" without crying wolf over a missing SMS fallback.
    The body always carries the full breakdown either way. Unauthenticated to
    match the other health routes, and it exposes only counts and config
    booleans — never a credential, phone number, or message body.
    """
    from notifications_health import overall

    report = overall(db)
    if report["status"] == "down":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=report,
        )
    return report
