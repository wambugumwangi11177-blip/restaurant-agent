"""
backend/routers/support.py
─────────────────────────────
In-app staff support ticketing — the other half of "people need a way to
communicate while Twilio is unfunded" alongside routers/notifications.py.
Any authenticated dashboard user can open a ticket; OWNER (role=admin,
bypasses every staff_role check per auth.require_staff_role) and
MANAGER-tier users can see and triage every ticket at their restaurant.
Both directions (new ticket, new reply) notify through ai/notify.py, so a
ticket surfaces in the recipient's bell/feed exactly like an ops alert.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant, get_staff_users_for_restaurant
from ai.notify import notify_users
from time_utils import utcnow

router = APIRouter(prefix="/support", tags=["support"])

_VALID_STATUSES = {s.name for s in models.SupportTicketStatus}


def _is_triage(user: models.User) -> bool:
    """Owner (role=admin/superadmin) or Manager-tier — mirrors the same
    boundary routers/staff.py uses for who can act on behalf of the whole
    roster, not just themselves."""
    if user.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return True
    return user.staff_role == models.StaffRole.MANAGER


def _message_out(msg: models.SupportTicketMessage, db: Session) -> dict:
    sender = db.query(models.User).filter(models.User.id == msg.sender_id).first()
    return {
        "id": msg.id,
        "sender_id": msg.sender_id,
        "sender_email": sender.email if sender else "unknown",
        "body": msg.body,
        "created_at": msg.created_at,
    }


def _ticket_out(ticket: models.SupportTicket, db: Session) -> dict:
    creator = db.query(models.User).filter(models.User.id == ticket.created_by_id).first()
    last_msg = (
        db.query(models.SupportTicketMessage)
        .filter(models.SupportTicketMessage.ticket_id == ticket.id)
        .order_by(models.SupportTicketMessage.created_at.desc())
        .first()
    )
    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status.value,
        "created_by_id": ticket.created_by_id,
        "created_by_email": creator.email if creator else "unknown",
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "message_count": len(ticket.messages),
        "last_message_at": last_msg.created_at if last_msg else None,
    }


def _get_ticket_or_404(db: Session, ticket_id: int, restaurant_id: int) -> models.SupportTicket:
    ticket = db.query(models.SupportTicket).options(
        joinedload(models.SupportTicket.messages)
    ).filter(
        models.SupportTicket.id == ticket_id,
        models.SupportTicket.restaurant_id == restaurant_id,
    ).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket not found")
    return ticket


def _require_access(ticket: models.SupportTicket, user: models.User) -> None:
    if _is_triage(user) or ticket.created_by_id == user.id:
        return
    raise HTTPException(status_code=403, detail="You don't have access to this ticket")


@router.post("/tickets", response_model=schemas.SupportTicketOut, status_code=201)
async def create_ticket(
    body: schemas.SupportTicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    ticket = models.SupportTicket(
        restaurant_id=restaurant.id,
        created_by_id=current_user.id,
        subject=body.subject,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    message = models.SupportTicketMessage(
        ticket_id=ticket.id, sender_id=current_user.id, body=body.message,
    )
    db.add(message)
    db.commit()
    db.refresh(ticket)

    recipients = get_staff_users_for_restaurant(
        db, restaurant, [models.StaffRole.OWNER, models.StaffRole.MANAGER]
    )
    notify_users(
        db, [u.id for u in recipients if u.id != current_user.id],
        f"New support ticket: {body.subject}",
        body.message[:200],
        "support.ticket_created",
        "/dashboard/support",
    )

    return _ticket_out(ticket, db)


@router.get("/tickets", response_model=List[schemas.SupportTicketOut])
async def list_tickets(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    q = db.query(models.SupportTicket).filter(models.SupportTicket.restaurant_id == restaurant.id)
    if not _is_triage(current_user):
        q = q.filter(models.SupportTicket.created_by_id == current_user.id)
    if status_filter:
        if status_filter.upper() not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status_filter}")
        q = q.filter(models.SupportTicket.status == models.SupportTicketStatus[status_filter.upper()])
    tickets = q.order_by(models.SupportTicket.updated_at.desc()).limit(200).all()
    return [_ticket_out(t, db) for t in tickets]


@router.get("/tickets/{ticket_id}", response_model=schemas.SupportTicketDetailOut)
async def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    ticket = _get_ticket_or_404(db, ticket_id, restaurant.id)
    _require_access(ticket, current_user)
    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status.value,
        "created_by_id": ticket.created_by_id,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "messages": [_message_out(m, db) for m in ticket.messages],
    }


@router.post("/tickets/{ticket_id}/messages", response_model=schemas.SupportTicketDetailOut, status_code=201)
async def add_message(
    ticket_id: int,
    body: schemas.SupportTicketMessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    ticket = _get_ticket_or_404(db, ticket_id, restaurant.id)
    _require_access(ticket, current_user)

    message = models.SupportTicketMessage(
        ticket_id=ticket.id, sender_id=current_user.id, body=body.body,
    )
    db.add(message)
    ticket.updated_at = utcnow()
    # A reply reopens a resolved/closed ticket back to in-progress — silence
    # from the requester shouldn't require them to notice the ticket is
    # "closed" before they can add more context.
    if ticket.status in (models.SupportTicketStatus.RESOLVED, models.SupportTicketStatus.CLOSED):
        ticket.status = models.SupportTicketStatus.IN_PROGRESS
    db.commit()
    db.refresh(ticket)

    if _is_triage(current_user):
        recipient_ids = [ticket.created_by_id] if ticket.created_by_id != current_user.id else []
    else:
        triage = get_staff_users_for_restaurant(
            db, restaurant, [models.StaffRole.OWNER, models.StaffRole.MANAGER]
        )
        recipient_ids = [u.id for u in triage if u.id != current_user.id]
    notify_users(
        db, recipient_ids,
        f"New reply: {ticket.subject}",
        body.body[:200],
        "support.ticket_reply",
        "/dashboard/support",
    )

    return {
        "id": ticket.id,
        "subject": ticket.subject,
        "status": ticket.status.value,
        "created_by_id": ticket.created_by_id,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "messages": [_message_out(m, db) for m in ticket.messages],
    }


@router.post("/tickets/{ticket_id}/status", response_model=schemas.SupportTicketOut)
async def update_status(
    ticket_id: int,
    body: schemas.SupportTicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(models.StaffRole.MANAGER)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    ticket = _get_ticket_or_404(db, ticket_id, restaurant.id)

    if body.status.upper() not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Unknown status: {body.status}")
    ticket.status = models.SupportTicketStatus[body.status.upper()]
    ticket.updated_at = utcnow()
    db.commit()
    db.refresh(ticket)

    notify_users(
        db, [ticket.created_by_id] if ticket.created_by_id != current_user.id else [],
        f"Ticket {ticket.status.value}: {ticket.subject}",
        f"Your support ticket is now {ticket.status.value.replace('_', ' ')}.",
        "support.ticket_status",
        "/dashboard/support",
    )
    return _ticket_out(ticket, db)
