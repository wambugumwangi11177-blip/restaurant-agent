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


@router.get("/ready")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Composite readiness check: DB connectivity + presence-only checks of the
    integration credentials (LLM, Twilio, M-Pesa) — no outbound calls to any
    of them, so this stays fast enough for a 1-minute uptime monitor.

    Only the DB check can fail the response (503); the others are informational
    dependency flags so an operator can tell "DB is up but WhatsApp send is
    unconfigured" apart from "the app is actually down." Reuses the same
    presence checks the rest of the app already uses to gate those features
    (ai/llm_client.is_available, ai/whatsapp/twilio_client.CONFIGURED,
    startup_checks._mpesa_configured) rather than re-deriving the env var list.
    """
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        db_ok = False

    from ai.llm_client import is_available as llm_is_available
    from ai.whatsapp.twilio_client import CONFIGURED as twilio_configured
    from startup_checks import _mpesa_configured

    dependencies = {
        "database": db_ok,
        "llm_provider": llm_is_available(),
        "whatsapp": twilio_configured,
        "mpesa": _mpesa_configured(),
    }

    if not db_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "dependencies": dependencies},
        )

    return {"status": "ok", "dependencies": dependencies}
