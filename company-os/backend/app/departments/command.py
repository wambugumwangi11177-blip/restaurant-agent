"""
Department 1 — Founder Command Center (directive 101)

Records: goal, meeting (tasks, decisions and notes are Kernel records).
Agents:  chief_of_staff (deterministic daily brief), decision_recorder (LLM; drafts
         decisions as "proposed", the founder accepts them).
Job:     daily_brief — in-app notification to every founder, plus WhatsApp when the
         founder has a phone and Twilio is configured (members are internal, so no
         approval is needed).
Reports: command.goals, command.brief, command.calendar
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import Field, ValidationError
from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import get_settings
from app.db import Base
from app.departments import ical
from app.departments._kit import In, _ts, _ws, out_of, patch_of
from app.kernel import records
from app.kernel.agents.builtin_agents import status_report
from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import Effect, Tool, ToolContext, register_tool
from app.kernel.channels import whatsapp
from app.kernel.departments import (
    BRIEF_SECTIONS,
    Department,
    Job,
    Report,
    SettingSpec,
    register_department,
    register_job,
    register_report,
    register_setting,
    table,
)
from app.kernel.models import ChannelMessage, Membership, Role, User, Workspace
from app.kernel.notifications import notify
from app.kernel.schemas import DecisionIn
from app.kernel.tenancy import Principal, scoped
from app.kernel.workspaces import department_enabled

logger = logging.getLogger("dept.command")
DEPT = "command"


class Goal(Base):
    __tablename__ = "cmd_goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    metric: Mapped[str | None] = mapped_column(String(200))
    unit: Mapped[str | None] = mapped_column(String(40))
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    due_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="on_track")
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Meeting(Base):
    __tablename__ = "cmd_meetings"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attendees: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


GoalStatus = Literal["on_track", "at_risk", "off_track", "done", "dropped"]


class GoalIn(In):
    title: str = Field(min_length=1, max_length=300)
    metric: Optional[str] = Field(default=None, max_length=200)
    unit: Optional[str] = Field(default=None, max_length=40)
    baseline_value: Optional[Decimal] = None
    target_value: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    due_on: Optional[date] = None
    status: GoalStatus = "on_track"
    owner_user_id: Optional[int] = None
    notes: Optional[str] = None


class MeetingIn(In):
    title: str = Field(min_length=1, max_length=300)
    held_at: Optional[datetime] = None
    attendees: Optional[str] = None
    notes: Optional[str] = None


def progress_pct(g: Goal) -> float | None:
    """Share of the way from baseline (default 0) to target. None when undefined."""
    if g.target_value is None or g.current_value is None:
        return None
    base = g.baseline_value or Decimal(0)
    span = g.target_value - base
    if span == 0:
        return None
    return round(float((g.current_value - base) / span * 100), 1)


# ── Calendar & brief ─────────────────────────────────────────────────────────

def _today(db: Session, workspace_id: int) -> tuple[date, str]:
    ws = db.get(Workspace, workspace_id)
    tz = ws.timezone if ws else "Africa/Nairobi"
    return datetime.now(ZoneInfo(tz)).date(), tz


def calendar_lines(db: Session, workspace_id: int, fetcher=ical.fetch) -> list[str]:
    ws = db.get(Workspace, workspace_id)
    url = (ws.settings or {}).get("calendar_ical_url")
    if not url:
        return ["(no calendar connected — set calendar_ical_url in Settings)"]
    day, tz = _today(db, workspace_id)
    try:
        events, skipped = ical.events_on(ical.parse_events(fetcher(url), tz), day, tz)
    except Exception as e:  # noqa: BLE001 — a calendar outage must not break the brief
        logger.warning("calendar fetch failed: %s", type(e).__name__)
        return [f"(calendar unavailable: {type(e).__name__})"]
    lines = [f"{'all day' if e.all_day else e.start.astimezone(ZoneInfo(tz)).strftime('%H:%M')}  {e.summary}"
             + (f" @ {e.location}" if e.location else "") for e in events] or ["(nothing on the calendar)"]
    if skipped:
        lines.append(f"({skipped} recurring event(s) not expanded — check your calendar app)")
    return lines


def compose_brief(db: Session, workspace_id: int, user_id: int, fetcher=ical.fetch) -> str:
    ctx = ToolContext(db=db, principal=Principal(user_id=user_id, workspace_id=workspace_id, role="founder"))
    parts = [status_report(ctx), "", "Calendar today:", *[f"  {x}" for x in calendar_lines(db, workspace_id, fetcher)]]
    at_risk = db.execute(scoped(Goal, workspace_id).where(Goal.status.in_(["at_risk", "off_track"]))).scalars().all()
    if at_risk:
        parts += ["", "Goals needing attention:", *[f"  {g.title} ({g.status})" for g in at_risk]]
    for dept, (title, fn) in BRIEF_SECTIONS.items():
        if dept == DEPT or not department_enabled(db, workspace_id, dept):
            continue
        try:
            lines = fn(db, workspace_id)
        except Exception:  # noqa: BLE001 — one department's bug must not kill the brief
            logger.exception("brief section %s failed", dept)
            lines = ["(section failed to load — see logs)"]
        if lines:
            parts += ["", f"{title}:", *[f"  {x}" for x in lines]]
    return "\n".join(parts)


def daily_brief_job(db: Session, workspace_id: int) -> str:
    founders = db.execute(select(User).join(Membership, Membership.user_id == User.id).where(
        Membership.workspace_id == workspace_id, Membership.role == Role.FOUNDER.value, User.is_active.is_(True))).scalars().all()
    sent = 0
    for u in founders:
        brief = compose_brief(db, workspace_id, u.id)
        notify(db, workspace_id, u.id, "Your daily brief", brief, link="/")
        if u.phone and get_settings().twilio_configured:
            try:
                sid = whatsapp.send(u.phone, brief)
                db.add(ChannelMessage(workspace_id=workspace_id, channel="whatsapp", direction="out",
                                      external_id=sid or None, from_addr="company", to_addr=u.phone, body=brief,
                                      user_id=u.id))
                sent += 1
            except (whatsapp.ChannelNotConfigured, whatsapp.ChannelSendError):
                logger.exception("daily brief WhatsApp failed for user %s", u.id)
    return f"brief delivered in-app to {len(founders)} founder(s), WhatsApp to {sent}"


# ── Reports ──────────────────────────────────────────────────────────────────

def goals_report(db: Session, p: Principal, params: dict) -> dict:
    goals = db.execute(scoped(Goal, p.workspace_id).where(Goal.status.not_in(["dropped"])).order_by(Goal.due_on.nulls_last())).scalars()
    rows = [[g.title, g.status, g.metric or "—", str(g.current_value or "—"), str(g.target_value or "—"),
             f"{progress_pct(g)}%" if progress_pct(g) is not None else "—", g.due_on.isoformat() if g.due_on else "—"]
            for g in goals]
    return table("Goals", f"{len(rows)} active goal(s)", ["Goal", "Status", "Metric", "Current", "Target", "Progress", "Due"], rows)


def brief_report(db: Session, p: Principal, params: dict) -> dict:
    text = compose_brief(db, p.workspace_id, p.user_id)
    return table("Daily brief", text, [], [])


def calendar_report(db: Session, p: Principal, params: dict) -> dict:
    lines = calendar_lines(db, p.workspace_id)
    return table("Calendar today", "", ["Event"], [[x] for x in lines])


# ── Agents & tools ───────────────────────────────────────────────────────────

def _record_decision(ctx: ToolContext, args: dict) -> dict:
    try:
        data = DecisionIn(**{**args, "status": "proposed"})
    except ValidationError as e:
        raise ValueError(str(e)) from None
    d = records.create_record(ctx.db, ctx.principal, "decision", data, agent_run_id=ctx.agent_run_id)
    return {"decision_id": d.id, "status": "proposed", "note": "The founder accepts it by setting status to accepted."}


def _chief_of_staff(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    return compose_brief(ctx.db, ctx.principal.workspace_id, ctx.principal.user_id), []


def register() -> None:
    register_setting(SettingSpec("calendar_ical_url", DEPT, "Private iCal URL of your calendar (Google Calendar → "
                                 "Settings → your calendar → 'Secret address in iCal format')", secret=True))
    records.register_record_type("goal", records.RecordType(
        Goal, GoalIn, patch_of(GoalIn), out_of(Goal), ("title", "metric"), label="Goals", department=DEPT,
        refs={"owner_user_id": "user"}))
    records.register_record_type("meeting", records.RecordType(
        Meeting, MeetingIn, patch_of(MeetingIn), out_of(Meeting), ("title", "attendees", "notes"),
        label="Meetings", department=DEPT))
    register_report(Report("command.brief", DEPT, "Today's brief", brief_report, "records.read"))
    register_report(Report("command.goals", DEPT, "Goals & progress", goals_report, "records.read"))
    register_report(Report("command.calendar", DEPT, "Calendar today", calendar_report, "records.read"))
    register_job(Job("daily_brief", DEPT, daily_brief_job, "daily 07:00 Africa/Nairobi"))
    register_tool(Tool(
        name="record_decision",
        description="Record a decision draft (status 'proposed') for the founder to accept.",
        effect=Effect.INTERNAL, permission="records.write",
        input_schema={"type": "object", "additionalProperties": False, "required": ["title", "decision"], "properties": {
            "title": {"type": "string", "maxLength": 300}, "decision": {"type": "string"},
            "context": {"type": "string"}, "alternatives": {"type": "string"}, "rationale": {"type": "string"},
            "revisit_on": {"type": "string", "description": "YYYY-MM-DD"}}},
        handler=_record_decision))
    register_agent(AgentSpec(name="chief_of_staff", description="Your daily brief: approvals, tasks, calendar, and every department's exceptions.",
                             handler=_chief_of_staff, input_hint="(no input needed)"))
    register_agent(AgentSpec(name="decision_recorder", description="Turns a voice note or message into decision drafts you accept.",
                             tools=("record_decision", "search_memory"), input_hint="Paste what was decided and why"))
    register_department(Department(DEPT, "Command Center", 1, "Goals, meetings, decisions and the daily brief.",
                                   "records.read", ("goal", "meeting", "task", "decision", "note"),
                                   ("chief_of_staff", "decision_recorder"), "directives/101_command_center.md"))
