from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

import schemas
from database import get_db

logger = logging.getLogger("health")

router = APIRouter(
    prefix="/health",
    tags=["health"],
    responses={404: {"description": "Not found"}},
)


def _check_db(db: Session) -> None:
    """Raise 503 unless a trivial query round-trips. Shared by both routes
    below so an uptime prober hitting either one exercises the same check —
    the bare "/" route used to return a hardcoded 200 regardless of DB state."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        )


@router.get("/", response_model=schemas.HealthOut)
async def health_check(db: Session = Depends(get_db)):
    _check_db(db)
    return {"status": "ok", "message": "Service is healthy"}


@router.get("/db", response_model=schemas.DbHealthOut)
async def db_health_check(db: Session = Depends(get_db)):
    _check_db(db)
    return {"status": "ok", "database": "connected"}
