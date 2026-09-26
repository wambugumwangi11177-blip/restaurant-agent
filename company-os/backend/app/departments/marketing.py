"""
Department 7 — Marketing & Content (directive 107)

Records: campaign, content_piece, consent (client permission to be named publicly).
Rule:    no case study naming a client without an active consent record —
         enforced in the save tool, not in a prompt.
Agents:  case_study_drafter (LLM; facts come only from recorded project data via
         the Kernel record registry; saves a note only if consent exists),
         content_calendar (deterministic).
Reports: marketing.calendar, marketing.consents
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import Date, ForeignKey, Integer, String, Text, or_
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.departments._kit import Currency, In, Money, _ts, _ws, chain, default_currency, out_of, patch_of
from app.kernel import records
from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import Effect, Tool, ToolContext, register_tool
from app.kernel.departments import Department, Report, register_brief_section, register_department, register_report, table
from app.kernel.models import Organization, Workspace
from app.kernel.rbac import A, C, F, S, register_permissions
from app.kernel.schemas import NoteIn
from app.kernel.tenancy import Principal, get_scoped, scoped
from app.kernel.workspaces import department_enabled

DEPT = "marketing"


class Campaign(Base):
    __tablename__ = "mkt_campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="planned")
    start_on: Mapped[date | None] = mapped_column(Date)
    end_on: Mapped[date | None] = mapped_column(Date)
    goal: Mapped[str | None] = mapped_column(Text)
    budget_minor: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ContentPiece(Base):
    __tablename__ = "mkt_content"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="post")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="idea")
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("mkt_campaigns.id", ondelete="SET NULL"))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    publish_on: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Consent(Base):
    __tablename__ = "mkt_consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    granted_by: Mapped[str] = mapped_column(String(200), nullable=False)
    granted_on: Mapped[date] = mapped_column(Date, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    expires_on: Mapped[date | None] = mapped_column(Date)
    revoked_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class CampaignIn(In):
    title: str = Field(min_length=1, max_length=300)
    channel: Optional[str] = Field(default=None, max_length=100)
    status: Literal["planned", "active", "done", "cancelled"] = "planned"
    start_on: Optional[date] = None
    end_on: Optional[date] = None
    goal: Optional[str] = None
    budget_minor: Optional[Money] = None
    currency: Currency = None
    notes: Optional[str] = None


class ContentPieceIn(In):
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["post", "article", "case_study", "newsletter", "video", "other"] = "post"
    status: Literal["idea", "draft", "review", "scheduled", "published"] = "idea"
    campaign_id: Optional[int] = None
    organization_id: Optional[int] = None
    publish_on: Optional[date] = None
    url: Optional[str] = Field(default=None, max_length=500)
    body: Optional[str] = None


class ConsentIn(In):
    organization_id: int
    title: str = Field(min_length=1, max_length=300, description="e.g. 'Case study consent 2026'")
    granted_by: str = Field(min_length=1, max_length=200, description="Name and role of the person who granted it")
    granted_on: date
    scope: str = Field(min_length=1, description="Exactly what they agreed to")
    document_id: Optional[int] = None
    expires_on: Optional[date] = None
    revoked_on: Optional[date] = None


def _today(db: Session, ws_id: int) -> date:
    ws = db.get(Workspace, ws_id)
    return datetime.now(ZoneInfo(ws.timezone if ws else "Africa/Nairobi")).date()


def active_consent(db: Session, ws_id: int, org_id: int) -> Consent | None:
    today = _today(db, ws_id)
    return db.execute(scoped(Consent, ws_id).where(
        Consent.organization_id == org_id, Consent.granted_on <= today, Consent.revoked_on.is_(None),
        or_(Consent.expires_on.is_(None), Consent.expires_on >= today)).order_by(Consent.granted_on.desc())).scalars().first()


def _content_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    kind = values.get("kind", obj.kind if obj else "post")
    status_ = values.get("status", obj.status if obj else "idea")
    org = values.get("organization_id", obj.organization_id if obj else None)
    if kind == "case_study" and status_ in ("scheduled", "published"):
        if not org or active_consent(db, p.workspace_id, org) is None:
            raise HTTPException(409, "A case study can't be scheduled or published without the client's active consent record")
    return values


def calendar_report(db: Session, p: Principal, params: dict) -> dict:
    today = _today(db, p.workspace_id)
    rows = [[c.publish_on.isoformat(), c.title, c.kind, c.status] for c in db.execute(
        scoped(ContentPiece, p.workspace_id).where(ContentPiece.publish_on >= today,
                                                   ContentPiece.publish_on <= today + timedelta(days=30),
                                                   ContentPiece.status != "published").order_by(ContentPiece.publish_on)).scalars()]
    ideas = sum(1 for _ in db.execute(scoped(ContentPiece, p.workspace_id).where(ContentPiece.status == "idea")).scalars())
    return table("Content calendar (30 days)", f"{len(rows)} scheduled/in progress, {ideas} idea(s) in the backlog",
                 ["Publish on", "Title", "Kind", "Status"], rows)


def consents_report(db: Session, p: Principal, params: dict) -> dict:
    rows = []
    for c in db.execute(scoped(Consent, p.workspace_id).order_by(Consent.granted_on.desc())).scalars():
        org = db.get(Organization, c.organization_id)
        state = "revoked" if c.revoked_on else ("expired" if c.expires_on and c.expires_on < _today(db, p.workspace_id) else "active")
        rows.append([org.name if org else "—", c.granted_by, c.granted_on.isoformat(), state, c.scope[:120]])
    return table("Client consents", "", ["Client", "Granted by", "On", "State", "Scope"], rows)


def brief(db: Session, ws_id: int) -> list[str]:
    today = _today(db, ws_id)
    return [f"publishing {c.publish_on}: {c.title} ({c.status})" for c in db.execute(scoped(ContentPiece, ws_id).where(
        ContentPiece.publish_on >= today, ContentPiece.publish_on <= today + timedelta(days=7),
        ContentPiece.status != "published")).scalars()]


# ── Agents & tools ───────────────────────────────────────────────────────────

def _get_project_story(ctx: ToolContext, args: dict) -> dict:
    """Reads delivery records through the Kernel registry (no import of the delivery department)."""
    ws = ctx.principal.workspace_id
    if not department_enabled(ctx.db, ws, "delivery") or "project" not in records.RECORD_TYPES:
        raise ValueError("The Delivery department is not enabled, so there is no project data to draw on")
    project_model = records.RECORD_TYPES["project"].model
    pr = get_scoped(ctx.db, project_model, int(args["project_id"]), ws)
    if pr is None:
        raise ValueError("project not found")
    ms_model = records.RECORD_TYPES["milestone"].model
    milestones = ctx.db.execute(scoped(ms_model, ws).where(ms_model.project_id == pr.id)).scalars()
    org = get_scoped(ctx.db, Organization, pr.organization_id, ws) if pr.organization_id else None
    consent = active_consent(ctx.db, ws, org.id) if org else None
    return {
        "project": {"title": pr.title, "status": pr.status, "description": pr.description,
                    "start_on": pr.start_on.isoformat() if pr.start_on else None,
                    "end_on": pr.end_on.isoformat() if pr.end_on else None},
        "client": org.name if org else None,
        "milestones": [{"title": m.title, "status": m.status,
                        "completed_on": m.completed_on.isoformat() if m.completed_on else None} for m in milestones],
        "consent": {"granted_by": consent.granted_by, "scope": consent.scope} if consent else None,
    }


def _save_case_study(ctx: ToolContext, args: dict) -> dict:
    ws = ctx.principal.workspace_id
    org = ctx.db.execute(scoped(Organization, ws).where(Organization.name == args["client_name"])).scalars().first()
    if org is None or active_consent(ctx.db, ws, org.id) is None:
        raise PermissionError(f"No active consent on record for {args['client_name']!r}: case study not saved")
    note = records.create_record(ctx.db, ctx.principal, "note",
                                 NoteIn(title=f"Case study draft: {args['client_name']}", body=args["body"]),
                                 agent_run_id=ctx.agent_run_id)
    return {"note_id": note.id}


def _content_calendar(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    r = calendar_report(ctx.db, ctx.principal, {})
    return "\n".join([r["summary"], *[" · ".join(map(str, row)) for row in r["rows"]]]), []


def register() -> None:
    register_permissions({"marketing.read": {F, S, C, A}, "marketing.write": {F, S}})
    perms = dict(read_perm="marketing.read", write_perm="marketing.write", delete_perm="marketing.write", department=DEPT)
    rr = records.register_record_type
    rr("campaign", records.RecordType(Campaign, CampaignIn, patch_of(CampaignIn), out_of(Campaign), ("title", "goal"),
                                      label="Campaigns", prepare=default_currency, **perms))
    rr("content_piece", records.RecordType(ContentPiece, ContentPieceIn, patch_of(ContentPieceIn), out_of(ContentPiece),
                                           ("title", "body"), label="Content",
                                           refs={"campaign_id": "campaign", "organization_id": "organization"},
                                           prepare=_content_hook, **perms))
    rr("consent", records.RecordType(Consent, ConsentIn, patch_of(ConsentIn), out_of(Consent), ("title", "granted_by", "scope"),
                                     label="Client consents", refs={"organization_id": "organization", "document_id": "document"},
                                     **perms))
    register_report(Report("marketing.calendar", DEPT, "Content calendar", calendar_report, "marketing.read"))
    register_report(Report("marketing.consents", DEPT, "Client consents", consents_report, "marketing.read"))
    register_brief_section(DEPT, "Marketing", brief)
    register_tool(Tool(name="get_project_story", description="Recorded facts about a delivered project, plus the client's consent status.",
                       effect=Effect.READ, permission="marketing.read", handler=_get_project_story,
                       input_schema={"type": "object", "additionalProperties": False, "required": ["project_id"],
                                     "properties": {"project_id": {"type": "integer"}}}))
    register_tool(Tool(name="save_case_study_draft", description="Save a case-study draft as a note. Refused without client consent.",
                       effect=Effect.INTERNAL, permission="marketing.write", handler=_save_case_study,
                       input_schema={"type": "object", "additionalProperties": False, "required": ["client_name", "body"],
                                     "properties": {"client_name": {"type": "string", "maxLength": 200}, "body": {"type": "string"}}}))
    register_agent(AgentSpec(name="case_study_drafter", description="Drafts a case study from recorded project facts — only with client consent.",
                             tools=("get_project_story", "save_case_study_draft", "search_memory"), permission="marketing.write",
                             input_hint="Project number"))
    register_agent(AgentSpec(name="content_calendar", description="What's scheduled to publish in the next 30 days.",
                             handler=_content_calendar, permission="marketing.read", input_hint="(no input needed)"))
    register_department(Department(DEPT, "Marketing", 7, "Campaigns, content and client consents.", "marketing.read",
                                   ("campaign", "content_piece", "consent"), ("case_study_drafter", "content_calendar"),
                                   "directives/107_marketing.md"))
