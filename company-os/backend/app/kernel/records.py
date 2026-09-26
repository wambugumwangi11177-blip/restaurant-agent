"""
app/kernel/records.py
─────────────────────
Service layer for core records. Every write goes through here so that every
write gets, in one transaction: the tenant filter, an audit row, and an event.
Routes and agent tools both call these functions — neither touches the ORM for
writes directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.kernel import schemas as sc
from app.kernel.audit import diff, snapshot, write_audit
from app.kernel.events import emit
from app.kernel.models import (
    Decision,
    Document,
    Link,
    Membership,
    Note,
    Organization,
    Person,
    Task,
)
from app.kernel.tenancy import Principal, get_or_404, get_scoped, scoped


@dataclass(frozen=True)
class RecordType:
    model: type
    create: type[BaseModel]
    patch: type[BaseModel]
    out: type[BaseModel]
    search_fields: tuple[str, ...]


RECORD_TYPES: dict[str, RecordType] = {
    "person": RecordType(Person, sc.PersonIn, sc.PersonPatch, sc.PersonOut, ("full_name", "email", "title")),
    "organization": RecordType(Organization, sc.OrganizationIn, sc.OrganizationPatch, sc.OrganizationOut, ("name", "industry")),
    "task": RecordType(Task, sc.TaskIn, sc.TaskPatch, sc.TaskOut, ("title", "description")),
    "decision": RecordType(Decision, sc.DecisionIn, sc.DecisionPatch, sc.DecisionOut, ("title", "decision")),
    "note": RecordType(Note, sc.NoteIn, sc.NotePatch, sc.NoteOut, ("title", "body")),
}

# Types that can be the endpoint of a link (documents are created by memory ingest).
LINKABLE: dict[str, type] = {**{k: v.model for k, v in RECORD_TYPES.items()}, "document": Document}


def record_type(name: str) -> RecordType:
    rt = RECORD_TYPES.get(name)
    if rt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown record type {name!r}")
    return rt


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_assignee(db: Session, principal: Principal, user_id: int | None) -> None:
    if user_id is None:
        return
    member = db.execute(
        select(Membership).where(
            Membership.workspace_id == principal.workspace_id, Membership.user_id == user_id
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "assignee_user_id is not a member of this workspace")


def list_records(
    db: Session, principal: Principal, type_name: str, q: str | None = None, limit: int = 50, offset: int = 0
) -> list[Any]:
    rt = record_type(type_name)
    stmt = scoped(rt.model, principal.workspace_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(*[getattr(rt.model, f).ilike(like) for f in rt.search_fields]))
    stmt = stmt.order_by(rt.model.id.desc()).limit(min(limit, 200)).offset(offset)
    return list(db.execute(stmt).scalars())


def get_record(db: Session, principal: Principal, type_name: str, record_id: int) -> Any:
    return get_or_404(db, record_type(type_name).model, record_id, principal.workspace_id)


def create_record(
    db: Session, principal: Principal, type_name: str, data: BaseModel, agent_run_id: int | None = None
) -> Any:
    rt = record_type(type_name)
    values = data.model_dump()
    if type_name == "task":
        _check_assignee(db, principal, values.get("assignee_user_id"))
        if values.get("status") == "done":
            values["completed_at"] = _now()
    if type_name == "decision":
        values["decided_by_user_id"] = principal.user_id
    obj = rt.model(workspace_id=principal.workspace_id, **values)
    db.add(obj)
    db.flush()
    write_audit(
        db, action="record.create", workspace_id=principal.workspace_id, entity_type=type_name,
        entity_id=obj.id, changes=diff(type_name, None, snapshot(obj)),
        actor_user_id=principal.user_id, actor_agent_run_id=agent_run_id,
    )
    emit(db, "record.created", workspace_id=principal.workspace_id, entity_type=type_name, entity_id=obj.id,
         actor_user_id=principal.user_id, actor_agent_run_id=agent_run_id)
    return obj


def update_record(
    db: Session, principal: Principal, type_name: str, record_id: int, patch: BaseModel,
    agent_run_id: int | None = None,
) -> Any:
    rt = record_type(type_name)
    obj = get_or_404(db, rt.model, record_id, principal.workspace_id)
    if type_name == "person" and obj.erased_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This person was erased under a data-rights request")
    before = snapshot(obj)
    changes = patch.model_dump(exclude_unset=True)
    if type_name == "task":
        if "assignee_user_id" in changes:
            _check_assignee(db, principal, changes["assignee_user_id"])
        if changes.get("status") == "done" and obj.status != "done":
            obj.completed_at = _now()
        elif "status" in changes and changes["status"] != "done":
            obj.completed_at = None
    for key, value in changes.items():
        setattr(obj, key, value)
    obj.updated_at = _now()
    db.flush()
    d = diff(type_name, before, snapshot(obj))
    if d:
        write_audit(
            db, action="record.update", workspace_id=principal.workspace_id, entity_type=type_name,
            entity_id=obj.id, changes=d, actor_user_id=principal.user_id, actor_agent_run_id=agent_run_id,
        )
        emit(db, "record.updated", workspace_id=principal.workspace_id, entity_type=type_name, entity_id=obj.id,
             payload={"fields": sorted(d)}, actor_user_id=principal.user_id, actor_agent_run_id=agent_run_id)
    return obj


def delete_record(db: Session, principal: Principal, type_name: str, record_id: int) -> None:
    rt = record_type(type_name)
    obj = get_or_404(db, rt.model, record_id, principal.workspace_id)
    before = snapshot(obj)
    db.execute(
        Link.__table__.delete().where(
            Link.workspace_id == principal.workspace_id,
            or_(
                (Link.from_type == type_name) & (Link.from_id == record_id),
                (Link.to_type == type_name) & (Link.to_id == record_id),
            ),
        )
    )
    db.delete(obj)
    db.flush()
    write_audit(
        db, action="record.delete", workspace_id=principal.workspace_id, entity_type=type_name,
        entity_id=record_id, changes=diff(type_name, before, None), actor_user_id=principal.user_id,
    )
    emit(db, "record.deleted", workspace_id=principal.workspace_id, entity_type=type_name, entity_id=record_id,
         actor_user_id=principal.user_id)


def create_link(db: Session, principal: Principal, data: sc.LinkIn, agent_run_id: int | None = None) -> Link:
    for t, i in ((data.from_type, data.from_id), (data.to_type, data.to_id)):
        if get_scoped(db, LINKABLE[t], i, principal.workspace_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{t} {i} not found")
    if (data.from_type, data.from_id) == (data.to_type, data.to_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A record cannot link to itself")
    link = Link(workspace_id=principal.workspace_id, **data.model_dump())
    db.add(link)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Link already exists") from None
    write_audit(
        db, action="link.create", workspace_id=principal.workspace_id, entity_type="link", entity_id=link.id,
        changes=data.model_dump(), actor_user_id=principal.user_id, actor_agent_run_id=agent_run_id,
    )
    emit(db, "link.created", workspace_id=principal.workspace_id, entity_type="link", entity_id=link.id,
         payload=data.model_dump(), actor_user_id=principal.user_id, actor_agent_run_id=agent_run_id)
    return link


def links_for(db: Session, principal: Principal, type_name: str, record_id: int) -> list[Link]:
    get_or_404(db, LINKABLE[type_name], record_id, principal.workspace_id)
    stmt = scoped(Link, principal.workspace_id).where(
        or_(
            (Link.from_type == type_name) & (Link.from_id == record_id),
            (Link.to_type == type_name) & (Link.to_id == record_id),
        )
    ).order_by(Link.id)
    return list(db.execute(stmt).scalars())
