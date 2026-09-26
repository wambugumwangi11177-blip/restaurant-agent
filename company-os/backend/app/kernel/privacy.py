"""
app/kernel/privacy.py
─────────────────────
Data-subject rights for people the company holds data on (Kenya Data
Protection Act 2019 — access and erasure). Scope: the Person record, the
links touching it, and channel messages exchanged with the person's phone
or email. Whether a given request must be honoured (legal holds, contracts,
tax records) is a legal judgement for the founder — the OS executes it, it
doesn't decide it.

Erasure scrubs PII in place and keeps the row (so links and history stay
structurally valid). The audit log needs no scrubbing: it never stored PII
values in the first place (app.kernel.audit.PII_FIELDS).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.kernel.audit import write_audit
from app.kernel.events import emit
from app.kernel.models import ChannelMessage, Link, Person
from app.kernel.schemas import PersonOut
from app.kernel.tenancy import Principal, get_or_404


def _messages_for(db: Session, workspace_id: int, person: Person) -> list[ChannelMessage]:
    addrs = [a for a in (person.phone, person.email) if a]
    if not addrs:
        return []
    return list(db.execute(
        select(ChannelMessage).where(
            ChannelMessage.workspace_id == workspace_id,
            or_(ChannelMessage.from_addr.in_(addrs), ChannelMessage.to_addr.in_(addrs)),
        ).order_by(ChannelMessage.id)
    ).scalars())


def export_person(db: Session, principal: Principal, person_id: int) -> dict:
    person = get_or_404(db, Person, person_id, principal.workspace_id)
    links = db.execute(
        select(Link).where(
            Link.workspace_id == principal.workspace_id,
            or_((Link.from_type == "person") & (Link.from_id == person_id),
                (Link.to_type == "person") & (Link.to_id == person_id)),
        )
    ).scalars()
    msgs = _messages_for(db, principal.workspace_id, person)
    write_audit(db, action="privacy.export", workspace_id=principal.workspace_id, entity_type="person",
                entity_id=person_id, actor_user_id=principal.user_id)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "person": PersonOut.model_validate(person).model_dump(mode="json"),
        "links": [{"from": f"{lk.from_type}:{lk.from_id}", "to": f"{lk.to_type}:{lk.to_id}", "relation": lk.relation}
                  for lk in links],
        "messages": [{"channel": m.channel, "direction": m.direction, "body": m.body,
                      "at": m.created_at.isoformat()} for m in msgs],
    }


def erase_person(db: Session, principal: Principal, person_id: int, reason: str) -> Person:
    if not reason or not reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A reason (e.g. the request reference) is required")
    person = get_or_404(db, Person, person_id, principal.workspace_id)
    if person.erased_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already erased")
    msgs = _messages_for(db, principal.workspace_id, person)
    for m in msgs:
        m.body = "[erased]"
        if m.from_addr in (person.phone, person.email):
            m.from_addr = "[erased]"
        if m.to_addr in (person.phone, person.email):
            m.to_addr = "[erased]"
    person.full_name = f"Erased person #{person.id}"
    person.email = None
    person.phone = None
    person.title = None
    person.notes = None
    person.erased_at = datetime.now(timezone.utc)
    person.updated_at = person.erased_at
    db.flush()
    write_audit(db, action="privacy.erase", workspace_id=principal.workspace_id, entity_type="person",
                entity_id=person_id, changes={"reason": reason.strip()[:500], "messages_scrubbed": len(msgs)},
                actor_user_id=principal.user_id)
    emit(db, "person.erased", workspace_id=principal.workspace_id, entity_type="person", entity_id=person_id,
         actor_user_id=principal.user_id)
    return person
