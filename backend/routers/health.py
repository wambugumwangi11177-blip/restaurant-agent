from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
# from database import get_db # Assuming db setup is done or will be done
import os

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
        print(f"Database connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable"
        )
