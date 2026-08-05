"""
backend/routers/notifications.py
──────────────────────────────────
The in-app notification feed the dashboard bell reads.

Tenant isolation follows the established pattern: the caller's restaurant is
resolved from their JWT via `get_restaurant_or_none`, and every query is filtered
by that restaurant_id. A notification id is never trusted on its own — see
`notifications.mark_read`, where a foreign id and a missing id are deliberately
indistinguishable so the endpoint can't be used to probe for existence.

Reads use `get_restaurant_or_none` rather than `get_or_create_restaurant`:
polling a feed must never create a restaurant as a side effect (command-query
separation — the same reasoning documented in routers/deps.py).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
import notifications as notifications_service
import schemas
from database import get_db
from routers.deps import get_restaurant_or_none

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=schemas.NotificationFeed)
async def list_notifications(
    limit: int = 50,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Newest-first feed plus the unread count, in one call.

    The badge and the panel are always rendered together, so returning both here
    keeps the dashboard to a single poll instead of two.
    """
    restaurant = get_restaurant_or_none(db, current_user)
    if not restaurant:
        # A user with no restaurant yet has no alerts — an empty feed is the
        # honest answer, not a 404.
        return {"items": [], "unread": 0}

    # Bound the page size: `limit` is client-supplied, and an unbounded value
    # would let one request pull the whole notification history into memory.
    limit = max(1, min(limit, 200))
    return {
        "items": notifications_service.list_for(
            db, restaurant.id, limit=limit, unread_only=unread_only,
            role=current_user.role, user_id=current_user.id,
        ),
        "unread": notifications_service.unread_count(db, restaurant.id, role=current_user.role,
                                                    user_id=current_user.id),
    }


@router.post("/{notification_id}/read", response_model=schemas.NotificationAck)
async def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_restaurant_or_none(db, current_user)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Notification not found")

    if not notifications_service.mark_read(db, restaurant.id, notification_id,
                                           role=current_user.role):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True, "unread": notifications_service.unread_count(
        db, restaurant.id, role=current_user.role, user_id=current_user.id)}


@router.post("/read-all", response_model=schemas.NotificationAck)
async def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_restaurant_or_none(db, current_user)
    if not restaurant:
        return {"ok": True, "unread": 0}

    notifications_service.mark_all_read(db, restaurant.id, role=current_user.role,
                                        user_id=current_user.id)
    return {"ok": True, "unread": notifications_service.unread_count(
        db, restaurant.id, role=current_user.role, user_id=current_user.id)}


@router.get("/preferences", response_model=schemas.NotificationPreferences)
async def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Every category this user can receive, with its label and mute state.

    Categories the caller's role can never see are omitted rather than shown
    switched off — a dead switch reads as "you turned this off", which is a
    different and wrong statement.
    """
    return {"items": notifications_service.preferences_for(db, current_user)}


@router.put("/preferences", response_model=schemas.NotificationPreferences)
async def set_notification_preferences(
    update: schemas.NotificationMuteUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Replace this user's muted categories.

    Unknown categories and the two that must stay audible (stock critical, out
    of stock) are dropped rather than rejected: the client sends the whole set
    it rendered, and a 4xx over one stale name would lose every other choice the
    user just made. The response is the authoritative state, so a client that
    sent something unacceptable sees it reflected back unmuted.
    """
    notifications_service.set_mutes(db, current_user.id, update.muted)
    return {"items": notifications_service.preferences_for(db, current_user)}
