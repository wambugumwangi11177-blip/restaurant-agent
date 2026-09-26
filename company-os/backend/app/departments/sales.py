"""
Department 2 — Customers & Sales (directive 102)

Records: deal, activity (organizations and people are Kernel records).
Rule:    no open deal goes more than `sales_stale_days` (default 14) without a
         next step, a future next-step date, and recent activity.
Agents:  pipeline_reviewer (deterministic), followup_drafter (LLM; outgoing
         messages become approval proposals), research_organizer (LLM; turns
         pasted research into a profile note marked UNVERIFIED — the OS has no web
         search provider, so it never "looks things up").
Reports: sales.pipeline, sales.stale
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import Field
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.departments._kit import Currency, In, Money, _ts, _ws, chain, default_currency, money, out_of, patch_of
from app.kernel import records
from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import Effect, Tool, ToolContext, register_tool
from app.kernel.departments import (
    Department,
    Report,
    SettingSpec,
    register_brief_section,
    register_department,
    register_report,
    register_setting,
    table,
)
from app.kernel.models import Organization, Person, Workspace
from app.kernel.rbac import A, F, S, register_permissions
from app.kernel.tenancy import Principal, get_scoped, scoped
from app.kernel.workspaces import setting

DEPT = "sales"
OPEN_STAGES = ("lead", "qualified", "proposal", "negotiation")
Stage = Literal["lead", "qualified", "proposal", "negotiation", "won", "lost"]


class Deal(Base):
    __tablename__ = "sales_deals"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    primary_contact_id: Mapped[int | None] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"))
    stage: Mapped[str] = mapped_column(String(20), nullable=False, server_default="lead")
    value_minor: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    probability_pct: Mapped[int | None] = mapped_column(Integer)
    expected_close_on: Mapped[date | None] = mapped_column(Date)
    next_step: Mapped[str | None] = mapped_column(String(500))
    next_step_due: Mapped[date | None] = mapped_column(Date)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    lost_reason: Mapped[str | None] = mapped_column(Text)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Activity(Base):
    __tablename__ = "sales_activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    deal_id: Mapped[int | None] = mapped_column(ForeignKey("sales_deals.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = _ts()
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class DealIn(In):
    title: str = Field(min_length=1, max_length=300)
    organization_id: Optional[int] = None
    primary_contact_id: Optional[int] = None
    stage: Stage = "lead"
    value_minor: Money = 0
    currency: Currency = None
    probability_pct: Optional[int] = Field(default=None, ge=0, le=100)
    expected_close_on: Optional[date] = None
    next_step: Optional[str] = Field(default=None, max_length=500)
    next_step_due: Optional[date] = None
    owner_user_id: Optional[int] = None
    lost_reason: Optional[str] = None
    notes: Optional[str] = None


class ActivityIn(In):
    deal_id: Optional[int] = None
    organization_id: Optional[int] = None
    person_id: Optional[int] = None
    kind: Literal["call", "email", "meeting", "whatsapp", "note"] = "note"
    summary: str = Field(min_length=1)
    occurred_at: Optional[datetime] = None


def _deal_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    stage = values.get("stage")
    if stage in ("won", "lost") and (obj is None or obj.stage != stage):
        values["closed_at"] = datetime.now(timezone.utc)
    elif stage in OPEN_STAGES:
        values["closed_at"] = None
    if stage == "lost" and not (values.get("lost_reason") or (obj is not None and obj.lost_reason)):
        from fastapi import HTTPException

        raise HTTPException(422, "lost_reason is required when a deal is lost — it is how the pipeline learns")
    return values


def _activity_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    if obj is None and not values.get("occurred_at"):
        values["occurred_at"] = datetime.now(timezone.utc)
    return values


def _activity_after(db: Session, p: Principal, act: Activity, deleted: bool) -> None:
    if deleted or act.deal_id is None:
        return
    deal = get_scoped(db, Deal, act.deal_id, p.workspace_id)
    if deal and (deal.last_activity_at is None or act.occurred_at > deal.last_activity_at):
        deal.last_activity_at = act.occurred_at


# ── Pipeline logic ───────────────────────────────────────────────────────────

def _today(db: Session, ws_id: int) -> date:
    ws = db.get(Workspace, ws_id)
    return datetime.now(ZoneInfo(ws.timezone if ws else "Africa/Nairobi")).date()


def stale_deals(db: Session, ws_id: int) -> list[tuple[Deal, str]]:
    days = int(setting(db, ws_id, "sales_stale_days", 14))
    today = _today(db, ws_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for d in db.execute(scoped(Deal, ws_id).where(Deal.stage.in_(OPEN_STAGES)).order_by(Deal.id)).scalars():
        last = d.last_activity_at or d.created_at
        if not d.next_step:
            out.append((d, "no next step"))
        elif d.next_step_due is None:
            out.append((d, "next step has no date"))
        elif d.next_step_due < today:
            out.append((d, f"next step overdue since {d.next_step_due.isoformat()}"))
        elif last < cutoff:
            out.append((d, f"no activity for {days}+ days"))
    return out


def _org_name(db: Session, org_id: int | None) -> str:
    o = db.get(Organization, org_id) if org_id else None
    return o.name if o else "—"


def pipeline_report(db: Session, p: Principal, params: dict) -> dict:
    rows = []
    for stage in (*OPEN_STAGES, "won", "lost"):
        deals = db.execute(scoped(Deal, p.workspace_id).where(Deal.stage == stage)).scalars().all()
        totals: dict[str, int] = {}
        for d in deals:
            totals[d.currency] = totals.get(d.currency, 0) + d.value_minor
        rows.append([stage, len(deals), ", ".join(money(v, c) for c, v in sorted(totals.items())) or "—"])
    return table("Pipeline", "Totals are per currency; no exchange rates are applied.", ["Stage", "Deals", "Value"], rows)


def stale_report(db: Session, p: Principal, params: dict) -> dict:
    items = stale_deals(db, p.workspace_id)
    rows = [[d.id, d.title, _org_name(db, d.organization_id), d.stage, reason] for d, reason in items]
    return table("Deals needing a next step", f"{len(rows)} open deal(s) breaking the next-step rule",
                 ["#", "Deal", "Organization", "Stage", "Problem"], rows)


def brief(db: Session, ws_id: int) -> list[str]:
    items = stale_deals(db, ws_id)
    return [f"#{d.id} {d.title}: {reason}" for d, reason in items[:5]] + (
        [f"…and {len(items) - 5} more"] if len(items) > 5 else [])


# ── Agents & tools ───────────────────────────────────────────────────────────

def _get_deal(ctx: ToolContext, args: dict) -> dict:
    d = get_scoped(ctx.db, Deal, int(args["deal_id"]), ctx.principal.workspace_id)
    if d is None:
        raise ValueError("deal not found")
    contact = get_scoped(ctx.db, Person, d.primary_contact_id, ctx.principal.workspace_id) if d.primary_contact_id else None
    acts = ctx.db.execute(scoped(Activity, ctx.principal.workspace_id).where(Activity.deal_id == d.id)
                          .order_by(Activity.occurred_at.desc()).limit(10)).scalars()
    return {
        "deal": {"id": d.id, "title": d.title, "stage": d.stage, "value": money(d.value_minor, d.currency),
                 "next_step": d.next_step, "next_step_due": d.next_step_due.isoformat() if d.next_step_due else None,
                 "organization": _org_name(ctx.db, d.organization_id)},
        "contact": {"name": contact.full_name, "email": contact.email, "phone": contact.phone} if contact else None,
        "recent_activity": [{"kind": a.kind, "at": a.occurred_at.isoformat(), "summary": a.summary} for a in acts],
    }


def _pipeline_reviewer(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    items = stale_deals(ctx.db, ctx.principal.workspace_id)
    if not items:
        return "Every open deal has a dated next step and recent activity.", []
    lines = [f"{len(items)} deal(s) need attention:"]
    lines += [f"• #{d.id} {d.title} ({_org_name(ctx.db, d.organization_id)}, {d.stage}): {reason}" for d, reason in items]
    return "\n".join(lines), []


def register() -> None:
    register_permissions({"sales.read": {F, S, A}, "sales.write": {F, S}, "sales.delete": {F}})
    register_setting(SettingSpec("sales_stale_days", DEPT, "Days without activity before an open deal is flagged (default 14)", kind="integer"))
    perms = dict(read_perm="sales.read", write_perm="sales.write", delete_perm="sales.delete", department=DEPT)
    records.register_record_type("deal", records.RecordType(
        Deal, DealIn, patch_of(DealIn), out_of(Deal), ("title", "next_step", "notes"), label="Deals",
        refs={"organization_id": "organization", "primary_contact_id": "person", "owner_user_id": "user"},
        prepare=chain(default_currency, _deal_hook), **perms))
    records.register_record_type("activity", records.RecordType(
        Activity, ActivityIn, patch_of(ActivityIn), out_of(Activity), ("summary",), label="Activities",
        title_field="summary", refs={"deal_id": "deal", "organization_id": "organization", "person_id": "person"},
        prepare=_activity_hook, after=_activity_after, **perms))
    register_report(Report("sales.pipeline", DEPT, "Pipeline by stage", pipeline_report, "sales.read"))
    register_report(Report("sales.stale", DEPT, "Deals needing a next step", stale_report, "sales.read"))
    register_brief_section(DEPT, "Sales follow-ups", brief)
    register_tool(Tool(
        name="get_deal", description="Read a deal with its contact and last 10 activities.", effect=Effect.READ,
        permission="sales.read", handler=_get_deal,
        input_schema={"type": "object", "additionalProperties": False, "required": ["deal_id"],
                      "properties": {"deal_id": {"type": "integer"}}}))
    register_agent(AgentSpec(name="pipeline_reviewer", description="Lists open deals breaking the next-step rule.",
                             handler=_pipeline_reviewer, permission="sales.read", input_hint="(no input needed)"))
    register_agent(AgentSpec(name="followup_drafter", description="Drafts a follow-up for a deal; sending waits for your approval.",
                             tools=("get_deal", "search_memory", "send_email", "send_whatsapp"), permission="sales.write",
                             input_hint="Deal number and what the follow-up should achieve"))
    register_agent(AgentSpec(name="research_organizer", description="Turns research you paste into an UNVERIFIED company profile note.",
                             tools=("create_note", "search_memory"), permission="sales.write",
                             input_hint="Company name + the notes/links you collected"))
    register_department(Department(DEPT, "Sales", 2, "Pipeline, deals, activities and follow-ups.", "sales.read",
                                   ("deal", "activity", "organization", "person"),
                                   ("pipeline_reviewer", "followup_drafter", "research_organizer"), "directives/102_sales.md"))
