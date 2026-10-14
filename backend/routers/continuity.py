"""Founder-continuity scorecard endpoint. SUPERADMIN only (platform operator)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from ai.continuity.scorecard import platform_scorecard

router = APIRouter(prefix="/continuity", tags=["continuity"])


@router.get("/scorecard")
async def scorecard(
    db: Session = Depends(get_db),
    _user: models.User = Depends(auth.require_role()),  # SUPERADMIN always passes; no other role listed
):
    return platform_scorecard(db)
