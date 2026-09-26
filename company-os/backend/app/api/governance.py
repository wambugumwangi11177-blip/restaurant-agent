"""
app/api/governance.py
─────────────────────
Audit log, activity feed, notifications, data-subject rights, and operational
status. Plus the unauthenticated health check.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.api.deps import get_principal, require
from app.config import get_settings
from app.db import get_db
from app.kernel import privacy
from app.kernel.agents import llm, spend
from app.kernel.models import AuditLog, Event, Notification, Proposal
from app.kernel.tenancy import Principal, get_or_404, scoped

router = APIRouter()
public_router = APIRouter()

VERSION = "0.1.0-phase0"


@public_router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": VERSION}


@router.get("/audit")
def audit_log(
    entity_type: str | None = None,
    entity_id: int | None = None,
    before_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require("audit.read")),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(AuditLog).where(AuditLog.workspace_id == principal.workspace_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if before_id is not None:
        stmt = stmt.where(AuditLog.id < before_id)
    rows = db.execute(stmt.order_by(AuditLog.id.desc()).limit(limit)).scalars()
    return [
        {"id": a.id, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id,
         "changes": a.changes, "actor_user_id": a.actor_user_id, "actor_agent_run_id": a.actor_agent_run_id,
         "request_id": a.request_id, "created_at": a.created_at.isoformat()}
        for a in rows
    ]


@router.get("/events")
def activity_feed(limit: int = Query(default=50, ge=1, le=200), principal: Principal = Depends(require("events.read")),
                  db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(scoped(Event, principal.workspace_id).order_by(Event.id.desc()).limit(limit)).scalars()
    return [
        {"id": e.id, "type": e.type, "entity_type": e.entity_type, "entity_id": e.entity_id, "payload": e.payload,
         "actor_user_id": e.actor_user_id, "actor_agent_run_id": e.actor_agent_run_id,
         "created_at": e.created_at.isoformat()}
        for e in rows
    ]


@router.get("/notifications")
def notifications(unread_only: bool = False, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)) -> list[dict]:
    stmt = scoped(Notification, principal.workspace_id).where(Notification.user_id == principal.user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.execute(stmt.order_by(Notification.id.desc()).limit(100)).scalars()
    return [{"id": n.id, "title": n.title, "body": n.body, "link": n.link,
             "read": n.read_at is not None, "created_at": n.created_at.isoformat()} for n in rows]


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> None:
    n = get_or_404(db, Notification, notification_id, principal.workspace_id)
    if n.user_id == principal.user_id and n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        db.commit()


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> None:
    db.execute(update(Notification).where(
        Notification.workspace_id == principal.workspace_id, Notification.user_id == principal.user_id,
        Notification.read_at.is_(None)).values(read_at=datetime.now(timezone.utc)))
    db.commit()


@router.get("/privacy/people/{person_id}/export")
def export_person(person_id: int, principal: Principal = Depends(require("privacy.manage")),
                  db: Session = Depends(get_db)) -> dict:
    data = privacy.export_person(db, principal, person_id)
    db.commit()
    return data


class EraseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


@router.post("/privacy/people/{person_id}/erase")
def erase_person(person_id: int, body: EraseIn, principal: Principal = Depends(require("privacy.manage")),
                 db: Session = Depends(get_db)) -> dict:
    p = privacy.erase_person(db, principal, person_id, body.reason)
    db.commit()
    return {"id": p.id, "erased_at": p.erased_at.isoformat()}


@router.get("/ops/status")
def ops_status(principal: Principal = Depends(require("ops.read")), db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    pending = db.execute(select(func.count()).select_from(Proposal).where(
        Proposal.workspace_id == principal.workspace_id, Proposal.status == "pending")).scalar_one()
    return {
        "version": VERSION,
        "env": s.env,
        "llm_provider": llm.provider(),
        "llm_spend_today_usd": str(spend.today_spend_usd(db, principal.workspace_id)),
        "llm_daily_cap_usd": str(spend.cap_usd()),
        "channels": {"whatsapp": s.twilio_configured, "email": s.smtp_configured},
        "pending_approvals": int(pending),
    }
