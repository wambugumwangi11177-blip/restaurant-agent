"""Owner decision detail pages."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from routers.store_control import list_approvals

router = APIRouter(prefix="/eleven/decisions", tags=["eleven-decisions"])


@router.get("/{kind}/{item_id}")
async def decision_detail(
    kind: str,
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth.get_current_user),
):
    _require_owner(current_user)
    get_or_create_restaurant(db, current_user)
    feed = await list_approvals(db=db, current_user=current_user)
    pending = feed.get("pending") or []
    match = next((p for p in pending if p.get("kind") == kind and int(p.get("id")) == item_id), None)
    if not match:
        events = feed.get("events") or []
        match = next((p for p in events if p.get("kind") == kind and int(p.get("id")) == item_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Decision not found")
    return {
        "id": item_id,
        "kind": kind,
        "headline": match.get("headline") or match.get("approval_card_title"),
        "why": match.get("owner_note") or match.get("headline") or "",
        "numbers": {
            "amount_kes": (match.get("amount_cents") or 0) / 100,
            "emphasis": match.get("emphasis"),
        },
        "photo_url": match.get("photo_path"),
        "actions": ["approve", "reject"],
        "raw": {k: match[k] for k in match if k not in ("ai",)},
    }