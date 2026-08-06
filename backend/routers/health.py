from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
# from database import get_db # Assuming db setup is done or will be done
import os
import logging

import auth
import models

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


@router.get("/config")
async def config_readiness(
    current_user=Depends(auth.require_role(models.Role.ADMIN)),
):
    """
    Post-deploy readiness report: which required configuration is actually
    present in THIS running process.

    Why this exists: `startup_checks.enforce_startup_checks()` runs once at boot
    and writes to the log. On Railway that means the answer to "did my env vars
    actually take effect?" lives in a log line that has usually scrolled away by
    the time anyone asks — and a soft warning (CORS_ORIGINS, Sentry) doesn't
    block the boot at all, so a degraded deploy looks identical to a healthy one
    from the outside. This surfaces the same check on demand.

    **Admin-only, and reports presence only — never values.** An unauthenticated
    endpoint announcing "MPESA_CALLBACK_TOKEN is not set" would tell an attacker
    the payment callback is forgeable, which is precisely the thing the token
    exists to prevent.
    """
    import startup_checks

    hard, soft = startup_checks.collect_problems()
    integrations = {
        "database":  bool(os.getenv("DATABASE_URL")),
        "mpesa":     bool(os.getenv("MPESA_CONSUMER_KEY") and os.getenv("MPESA_PASSKEY")),
        "mpesa_callback_token": bool(os.getenv("MPESA_CALLBACK_TOKEN")),
        "twilio":    bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN")),
        "llm":       bool(os.getenv("GROQ_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),
        "sentry":    bool(os.getenv("SENTRY_DSN")),
        "cors_origins_explicit": bool(os.getenv("CORS_ORIGINS")),
    }

    if hard:
        state = "blocked"      # would refuse to boot in production
    elif soft:
        state = "degraded"     # running, but not fully configured
    else:
        state = "ready"

    return {
        "status": state,
        "is_production": startup_checks.is_production(),
        "blocking_problems": hard,
        "warnings": soft,
        "integrations": integrations,
    }
