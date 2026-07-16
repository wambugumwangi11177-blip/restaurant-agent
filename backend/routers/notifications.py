"""
backend/routers/notifications.py
──────────────────────────────────
In-app notification feed + Web Push subscription management. See
ai/notify.py for the write side (notify_user/notify_users) — this router is
purely the read side plus subscription CRUD, both scoped to current_user.id
only (nothing here needs a staff_role gate: everyone manages their own
notifications and their own device's push subscription, never another
user's).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=schemas.NotificationListOut)
async def list_notifications(
    limit: int = 50,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    q = db.query(models.Notification).filter(models.Notification.user_id == current_user.id)
    if unread_only:
        q = q.filter(models.Notification.is_read.is_(False))
    items = q.order_by(models.Notification.created_at.desc()).limit(min(limit, 200)).all()

    unread_count = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read.is_(False),
    ).count()

    return {"items": items, "unread_count": unread_count}


@router.post("/{notification_id}/read", response_model=schemas.NotificationOut)
async def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    notif = db.query(models.Notification).filter(
        models.Notification.id == notification_id,
        models.Notification.user_id == current_user.id,
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    db.commit()
    db.refresh(notif)
    return notif


@router.post("/read-all")
async def mark_all_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    updated = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read.is_(False),
    ).update({"is_read": True})
    db.commit()
    return {"marked_read": updated}


@router.post("/subscribe", response_model=schemas.PushSubscriptionOut, status_code=201)
async def subscribe(
    body: schemas.PushSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Upsert by endpoint (not by user_id+endpoint): a Push API endpoint is
    unique per browser+origin regardless of who's logged in, so calling
    this unconditionally on every dashboard load (the standard Web Push
    client pattern) must never create duplicate rows. If the endpoint
    already belongs to a different user_id, reassign it — that's just a
    different staff member logged into the same shared device.
    """
    existing = db.query(models.PushSubscription).filter(
        models.PushSubscription.endpoint == body.endpoint
    ).first()
    if existing:
        existing.user_id = current_user.id
        existing.p256dh = body.p256dh
        existing.auth = body.auth
        existing.user_agent = body.user_agent
        from time_utils import utcnow
        existing.updated_at = utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    sub = models.PushSubscription(
        user_id=current_user.id,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
        user_agent=body.user_agent,
    )
    db.add(sub)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with a concurrent subscribe of the same endpoint —
        # re-fetch and update instead of failing the request.
        db.rollback()
        existing = db.query(models.PushSubscription).filter(
            models.PushSubscription.endpoint == body.endpoint
        ).first()
        if not existing:
            raise
        existing.user_id = current_user.id
        existing.p256dh = body.p256dh
        existing.auth = body.auth
        existing.user_agent = body.user_agent
        db.commit()
        db.refresh(existing)
        return existing
    db.refresh(sub)
    return sub


@router.post("/unsubscribe")
async def unsubscribe(
    body: schemas.PushUnsubscribeBody,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    deleted = db.query(models.PushSubscription).filter(
        models.PushSubscription.endpoint == body.endpoint,
        models.PushSubscription.user_id == current_user.id,
    ).delete()
    db.commit()
    return {"unsubscribed": bool(deleted)}
