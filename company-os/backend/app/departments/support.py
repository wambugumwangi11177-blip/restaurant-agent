"""
Department 4 — Support & Incidents (directive 104)

Records: ticket, incident.
SLA:     response targets come from the workspace setting `support_sla_hours`
         (e.g. "urgent=4,high=8,normal=24,low=72" — YOUR policy; there is no
         default, because an SLA the OS invented would be a promise you never made).
Job:     sla_check — flags open tickets past their SLA, once each, and notifies founders.
Agents:  triage (LLM: finds similar past tickets, drafts a reply as an approval
         proposal), incident_scribe (deterministic: postmortem draft from the timeline).
Reports: support.queue, support.incidents
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import DateTime, ForeignKey, String, Text, or_
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.departments._kit import In, _ts, _ws, out_of, patch_of
from app.kernel import records
from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import Effect, Tool, ToolContext, register_tool
from app.kernel.agents.untrusted import wrap
from app.kernel.departments import (
    Department,
    Job,
    Report,
    SettingSpec,
    register_brief_section,
    register_department,
    register_job,
    register_report,
    register_setting,
    table,
)
from app.kernel.events import emit, register_event_types
from app.kernel.notifications import founders, notify
from app.kernel.rbac import A, C, F, S, register_permissions
from app.kernel.tenancy import Principal, get_scoped, scoped
from app.kernel.workspaces import setting

DEPT = "support"
OPEN = ("open", "pending")
Priority = Literal["low", "normal", "high", "urgent"]


class Ticket(Base):
    __tablename__ = "sup_tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default="other")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default="normal")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    resolution: Mapped[str | None] = mapped_column(Text)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_breached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Incident(Base):
    __tablename__ = "sup_incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, server_default="sev3")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="investigating")
    started_at: Mapped[datetime] = _ts()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    timeline: Mapped[str | None] = mapped_column(Text)
    postmortem: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class TicketIn(In):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    organization_id: Optional[int] = None
    person_id: Optional[int] = None
    channel: Literal["whatsapp", "email", "phone", "web", "other"] = "other"
    priority: Priority = "normal"
    status: Literal["open", "pending", "resolved", "closed"] = "open"
    resolution: Optional[str] = None
    first_response_at: Optional[datetime] = None


class IncidentIn(In):
    title: str = Field(min_length=1, max_length=300)
    severity: Literal["sev1", "sev2", "sev3"] = "sev3"
    status: Literal["investigating", "identified", "monitoring", "resolved"] = "investigating"
    started_at: Optional[datetime] = None
    summary: Optional[str] = None
    timeline: Optional[str] = Field(default=None, description="One line per update: 'HH:MM what happened'")
    postmortem: Optional[str] = None


def parse_sla(spec: str | None) -> dict[str, int]:
    """'urgent=4,high=8' -> {'urgent': 4, 'high': 8}. Invalid entries are rejected loudly."""
    out: dict[str, int] = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        key, _, val = part.partition("=")
        if key.strip() not in ("low", "normal", "high", "urgent") or not val.strip().isdigit():
            raise ValueError(f"bad support_sla_hours entry {part!r}; use e.g. urgent=4,high=8,normal=24,low=72")
        out[key.strip()] = int(val)
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ticket_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    if obj is None:
        try:
            hours = parse_sla(setting(db, p.workspace_id, "support_sla_hours")).get(values.get("priority", "normal"))
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        if hours:
            values["sla_due_at"] = _now() + timedelta(hours=hours)
    status_ = values.get("status")
    if status_ in ("resolved", "closed") and (obj is None or obj.status not in ("resolved", "closed")):
        values["resolved_at"] = _now()
        if not (values.get("resolution") or (obj is not None and obj.resolution)):
            raise HTTPException(422, "resolution is required to resolve a ticket (it feeds triage of future tickets)")
    elif status_ in OPEN:
        values["resolved_at"] = None
    return values


def _incident_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    if obj is None and not values.get("started_at"):
        values["started_at"] = _now()
    if values.get("status") == "resolved" and (obj is None or obj.status != "resolved"):
        values["resolved_at"] = _now()
    elif "status" in values and values["status"] != "resolved":
        values["resolved_at"] = None
    return values


# ── SLA job & reports ────────────────────────────────────────────────────────

def sla_check(db: Session, ws_id: int) -> str:
    now = _now()
    breached = db.execute(scoped(Ticket, ws_id).where(
        Ticket.status.in_(OPEN), Ticket.sla_due_at.is_not(None), Ticket.sla_due_at < now,
        Ticket.first_response_at.is_(None), Ticket.sla_breached_at.is_(None))).scalars().all()
    for t in breached:
        t.sla_breached_at = now
        emit(db, "ticket.sla_breached", workspace_id=ws_id, entity_type="ticket", entity_id=t.id,
             payload={"priority": t.priority, "title": t.title})
        for uid in founders(db, ws_id):
            notify(db, ws_id, uid, f"SLA breached: {t.title}", f"{t.priority} ticket #{t.id} has no response past its SLA.",
                   link="/d/support")
    return f"{len(breached)} newly breached ticket(s)"


def queue_report(db: Session, p: Principal, params: dict) -> dict:
    rows = []
    for t in db.execute(scoped(Ticket, p.workspace_id).where(Ticket.status.in_(OPEN))
                        .order_by(Ticket.sla_due_at.nulls_last(), Ticket.id)).scalars():
        sla = "breached" if t.sla_breached_at else (t.sla_due_at.isoformat(timespec="minutes") if t.sla_due_at else "no SLA")
        rows.append([t.id, t.title, t.priority, t.status, "yes" if t.first_response_at else "no", sla])
    return table("Open tickets", f"{len(rows)} open", ["#", "Ticket", "Priority", "Status", "Responded", "SLA due"], rows)


def incidents_report(db: Session, p: Principal, params: dict) -> dict:
    rows = []
    for i in db.execute(scoped(Incident, p.workspace_id).order_by(Incident.started_at.desc()).limit(50)).scalars():
        dur = (i.resolved_at - i.started_at) if i.resolved_at else None
        rows.append([i.id, i.title, i.severity, i.status, f"{dur.total_seconds() / 3600:.1f} h" if dur else "ongoing",
                     "yes" if i.postmortem else "no"])
    return table("Incidents", "", ["#", "Incident", "Severity", "Status", "Duration", "Postmortem"], rows)


def brief(db: Session, ws_id: int) -> list[str]:
    open_n = db.execute(scoped(Ticket, ws_id).where(Ticket.status.in_(OPEN))).scalars().all()
    breached = [t for t in open_n if t.sla_breached_at]
    live = db.execute(scoped(Incident, ws_id).where(Incident.status != "resolved")).scalars().all()
    out = []
    if open_n:
        out.append(f"{len(open_n)} open ticket(s), {len(breached)} past SLA")
    out += [f"ONGOING INCIDENT {i.severity}: {i.title}" for i in live]
    return out


# ── Agents & tools ───────────────────────────────────────────────────────────

def _search_tickets(ctx: ToolContext, args: dict) -> dict:
    words = [w for w in args["query"].split() if len(w) > 3][:6] or [args["query"]]
    conds = [Ticket.title.ilike(f"%{w}%") for w in words] + [Ticket.description.ilike(f"%{w}%") for w in words]
    rows = ctx.db.execute(scoped(Ticket, ctx.principal.workspace_id).where(
        Ticket.status.in_(["resolved", "closed"]), or_(*conds)).order_by(Ticket.resolved_at.desc()).limit(5)).scalars()
    return {"similar_resolved_tickets": [
        {"id": t.id, "title": t.title, "resolution": wrap(f"ticket:{t.id}", t.resolution or "")} for t in rows]}


def _get_ticket(ctx: ToolContext, args: dict) -> dict:
    t = get_scoped(ctx.db, Ticket, int(args["ticket_id"]), ctx.principal.workspace_id)
    if t is None:
        raise ValueError("ticket not found")
    from app.kernel.models import Person

    person = get_scoped(ctx.db, Person, t.person_id, ctx.principal.workspace_id) if t.person_id else None
    return {"id": t.id, "title": t.title, "priority": t.priority, "status": t.status, "channel": t.channel,
            "description": wrap(f"ticket:{t.id}", t.description or ""),
            "requester": {"name": person.full_name, "email": person.email, "phone": person.phone} if person else None}


def postmortem_draft(i: Incident) -> str:
    dur = (i.resolved_at - i.started_at) if i.resolved_at else None
    return "\n".join([
        f"# Postmortem: {i.title}",
        f"Severity: {i.severity}   Started: {i.started_at.isoformat(timespec='minutes')}   "
        f"Resolved: {i.resolved_at.isoformat(timespec='minutes') if i.resolved_at else 'not yet'}"
        + (f"   Duration: {dur.total_seconds() / 3600:.1f} h" if dur else ""),
        "", "## Summary", i.summary or "TODO (human): what happened, who was affected.",
        "", "## Timeline", i.timeline or "TODO (human): no timeline was recorded.",
        "", "## Root cause", "TODO (human): not inferred automatically.",
        "", "## What went well / what didn't", "TODO (human)",
        "", "## Action items", "- [ ] TODO (human): owner, due date",
    ])


def _incident_scribe(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return "Give the incident number.", []
    inc = get_scoped(ctx.db, Incident, int(digits), ctx.principal.workspace_id)
    if inc is None:
        return f"No incident #{digits}.", []
    draft = postmortem_draft(inc)
    if not inc.postmortem:
        records.update_record(ctx.db, ctx.principal, "incident", inc.id,
                              records.RECORD_TYPES["incident"].patch(postmortem=draft), agent_run_id=ctx.agent_run_id)
        return draft + "\n\n(saved as the incident's postmortem draft)", []
    return draft + "\n\n(not saved: the incident already has a postmortem)", []


def register() -> None:
    register_permissions({"support.read": {F, S, C, A}, "support.write": {F, S, C}, "support.delete": {F}})
    register_event_types({"ticket.sla_breached": "activity feed; founder notification"})
    register_setting(SettingSpec("support_sla_hours", DEPT,
                                 "First-response SLA hours per priority, e.g. urgent=4,high=8,normal=24,low=72 (your policy)"))
    perms = dict(read_perm="support.read", write_perm="support.write", delete_perm="support.delete", department=DEPT)
    records.register_record_type("ticket", records.RecordType(
        Ticket, TicketIn, patch_of(TicketIn), out_of(Ticket), ("title", "description", "resolution"), label="Tickets",
        refs={"organization_id": "organization", "person_id": "person"}, prepare=_ticket_hook, **perms))
    records.register_record_type("incident", records.RecordType(
        Incident, IncidentIn, patch_of(IncidentIn), out_of(Incident), ("title", "summary"), label="Incidents",
        prepare=_incident_hook, **perms))
    register_report(Report("support.queue", DEPT, "Open tickets & SLA", queue_report, "support.read"))
    register_report(Report("support.incidents", DEPT, "Incidents", incidents_report, "support.read"))
    register_job(Job("sla_check", DEPT, sla_check, "every 15 minutes"))
    register_brief_section(DEPT, "Support", brief)
    register_tool(Tool(name="search_tickets", description="Find similar resolved tickets and how they were resolved.",
                       effect=Effect.READ, permission="support.read", handler=_search_tickets,
                       input_schema={"type": "object", "additionalProperties": False, "required": ["query"],
                                     "properties": {"query": {"type": "string", "maxLength": 300}}}))
    register_tool(Tool(name="get_ticket", description="Read a ticket and its requester's contact details.",
                       effect=Effect.READ, permission="support.read", handler=_get_ticket,
                       input_schema={"type": "object", "additionalProperties": False, "required": ["ticket_id"],
                                     "properties": {"ticket_id": {"type": "integer"}}}))
    register_agent(AgentSpec(name="triage", description="Finds similar past tickets and drafts a reply for your approval.",
                             tools=("get_ticket", "search_tickets", "search_memory", "send_email", "send_whatsapp"),
                             permission="support.write", input_hint="Ticket number"))
    register_agent(AgentSpec(name="incident_scribe", description="Drafts a postmortem from an incident's recorded timeline.",
                             handler=_incident_scribe, permission="support.write", input_hint="Incident number"))
    register_department(Department(DEPT, "Support", 4, "Tickets, SLAs and incidents.", "support.read",
                                   ("ticket", "incident"), ("triage", "incident_scribe"), "directives/104_support.md"))
