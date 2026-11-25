"""Owner decision detail pages."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from services.decision_detail import build_decision_detail

router = APIRouter(prefix="/eleven/decisions", tags=["eleven-decisions"])


@router.get("/{kind}/{item_id}")
async def decision_detail(
    kind: str,
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    payload = await build_decision_detail(db, restaurant, current_user, kind, item_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Decision not found")
    return payload