"""
app/kernel/records.py
─────────────────────
Service layer for core records. Every write goes through here so that every
write gets, in one transaction: the tenant filter, an audit row, and an event.
Routes and agent tools both call these functions — neither touches the ORM for
writes directly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
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
from app.kernel.rbac import role_has
from app.kernel.tenancy import Principal, get_or_404, get_scoped, scoped


Hook = Callable[[Session, Principal, dict, Any], dict]


@dataclass(frozen=True)
class RecordType:
    """A record type the generic records API serves. Departments register their
    own with `register_record_type` (ADR 0001) and get CRUD, workspace scoping,
    audit rows, events, reference checks and a schema-driven UI for free."""
    model: type
    create: type[BaseModel]
    patch: type[BaseModel]
    out: type[BaseModel]
    search_fields: tuple[str, ...]
    label: str = ""
    department: str = "kernel"
    title_field: str = "title"
    read_perm: str = "records.read"
    write_perm: str = "records.write"
    delete_perm: str = "records.delete"
    # field -> record type it points at ("user" = a workspace member)
    refs: dict[str, str] = field(default_factory=dict)
    # (db, principal, values, existing_or_None) -> values; validates / computes fields
    prepare: Hook | None = None
    # (db, principal, obj, deleted) — runs after the write is flushed (e.g. recompute a parent's totals)
    after: Callable[[Session, Principal, Any, bool], None] | None = None


def _prepare_task(db: Session, principal: Principal, values: dict, obj: Any) -> dict:
    if values.get("status") == "done" and (obj is None or obj.status != "done"):
        values["completed_at"] = _now()
    elif "status" in values and values["status"] != "done":
        values["completed_at"] = None
    return values


def _prepare_decision(db: Session, principal: Principal, values: dict, obj: Any) -> dict:
    if obj is None:
        values["decided_by_user_id"] = principal.user_id
    return values


def _prepare_person(db: Session, principal: Principal, values: dict, obj: Any) -> dict:
    if obj is not None and obj.erased_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This person was erased under a data-rights request")
    return values


RECORD_TYPES: dict[str, RecordType] = {
    "person": RecordType(Person, sc.PersonIn, sc.PersonPatch, sc.PersonOut, ("full_name", "email", "title"),
                         label="People", title_field="full_name", prepare=_prepare_person),
    "organization": RecordType(Organization, sc.OrganizationIn, sc.OrganizationPatch, sc.OrganizationOut,
                               ("name", "industry"), label="Organizations", title_field="name"),
    "task": RecordType(Task, sc.TaskIn, sc.TaskPatch, sc.TaskOut, ("title", "description"), label="Tasks",
                       refs={"assignee_user_id": "user"}, prepare=_prepare_task),
    "decision": RecordType(Decision, sc.DecisionIn, sc.DecisionPatch, sc.DecisionOut, ("title", "decision"),
                           label="Decisions", prepare=_prepare_decision),
    "note": RecordType(Note, sc.NoteIn, sc.NotePatch, sc.NoteOut, ("title", "body"), label="Notes"),
}


def register_record_type(name: str, rt: RecordType) -> None:
    existing = RECORD_TYPES.get(name)
    if existing is not None and existing is not rt:
        raise ValueError(f"Record type {name!r} already registered")
    RECORD_TYPES[name] = rt


def linkable_model(name: str) -> type | None:
    if name == "document":
        return Document
    rt = RECORD_TYPES.get(name)
    return rt.model if rt else None


def record_type(name: str) -> RecordType:
    rt = RECORD_TYPES.get(name)
    if rt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown record type {name!r}")
    return rt


def record_type_for(db: Session, principal: Principal, name: str, perm: str = "read") -> RecordType:
    """Resolve a type for this caller: exists, department enabled for the
    workspace, and the caller's role holds the needed permission."""
    from app.kernel.workspaces import department_enabled  # local: workspaces imports nothing from here

    rt = record_type(name)
    if rt.department != "kernel" and not department_enabled(db, principal.workspace_id, rt.department):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown record type {name!r}")
    needed = {"read": rt.read_perm, "write": rt.write_perm, "delete": rt.delete_perm}[perm]
    if not role_has(principal.role, needed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role ({principal.role}) lacks '{needed}'")
    return rt


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_refs(db: Session, principal: Principal, rt: RecordType, values: dict) -> None:
    for fld, target in rt.refs.items():
        ref_id = values.get(fld)
        if ref_id is None:
            continue
        if target == "user":
            ok = db.execute(select(Membership).where(
                Membership.workspace_id == principal.workspace_id, Membership.user_id == ref_id)).scalar_one_or_none()
        else:
            model = linkable_model(target)
            ok = model is not None and get_scoped(db, model, ref_id, principal.workspace_id) is not None
        if not ok:
            what = "a member of this workspace" if target == "user" else f"an existing {target} in this workspace"
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{fld} is not {what}")


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
    _check_refs(db, principal, rt, values)
    if rt.prepare:
        values = rt.prepare(db, principal, values, None)
    obj = rt.model(workspace_id=principal.workspace_id, **values)
    db.add(obj)
    db.flush()
    if rt.after:
        rt.after(db, principal, obj, False)
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
    before = snapshot(obj)
    changes = patch.model_dump(exclude_unset=True)
    _check_refs(db, principal, rt, changes)
    if rt.prepare:
        changes = rt.prepare(db, principal, changes, obj)
    for key, value in changes.items():
        setattr(obj, key, value)
    if hasattr(obj, "updated_at"):
        obj.updated_at = _now()
    db.flush()
    if rt.after:
        rt.after(db, principal, obj, False)
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
    if rt.after:
        rt.after(db, principal, obj, True)
    write_audit(
        db, action="record.delete", workspace_id=principal.workspace_id, entity_type=type_name,
        entity_id=record_id, changes=diff(type_name, before, None), actor_user_id=principal.user_id,
    )
    emit(db, "record.deleted", workspace_id=principal.workspace_id, entity_type=type_name, entity_id=record_id,
         actor_user_id=principal.user_id)


def create_link(db: Session, principal: Principal, data: sc.LinkIn, agent_run_id: int | None = None) -> Link:
    for t, i in ((data.from_type, data.from_id), (data.to_type, data.to_id)):
        model = linkable_model(t)
        if model is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{t!r} is not a record type")
        if get_scoped(db, model, i, principal.workspace_id) is None:
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
    model = linkable_model(type_name)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown record type {type_name!r}")
    get_or_404(db, model, record_id, principal.workspace_id)
    stmt = scoped(Link, principal.workspace_id).where(
        or_(
            (Link.from_type == type_name) & (Link.from_id == record_id),
            (Link.to_type == type_name) & (Link.to_id == record_id),
        )
    ).order_by(Link.id)
    return list(db.execute(stmt).scalars())
