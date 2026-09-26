"""
Department 3 — Delivery / Projects (directive 103)

Records: project, milestone, change_request, time_entry.
Agents:  status_reporter (deterministic: milestones, hours, change requests and —
         when the project has a GitHub repo — commits from the GitHub REST API),
         scoper (LLM; drafts an SOW note with explicit assumptions/exclusions).
Reports: delivery.projects, delivery.status (param project_id)
The weekly client update is *drafted*; sending it goes through the approval inbox.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.departments._kit import Currency, In, Money, _ts, _ws, chain, default_currency, money, out_of, patch_of
from app.kernel import records
from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import ToolContext
from app.kernel.departments import Department, Report, register_brief_section, register_department, register_report, table
from app.kernel.models import Organization, Workspace
from app.kernel.rbac import A, C, F, S, register_permissions
from app.kernel.tenancy import Principal, get_scoped, scoped

DEPT = "delivery"


class Project(Base):
    __tablename__ = "dlv_projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="planned")
    start_on: Mapped[date | None] = mapped_column(Date)
    end_on: Mapped[date | None] = mapped_column(Date)
    budget_minor: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    github_repo: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Milestone(Base):
    __tablename__ = "dlv_milestones"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    project_id: Mapped[int] = mapped_column(ForeignKey("dlv_projects.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="planned")
    amount_minor: Mapped[int | None] = mapped_column(Integer)
    completed_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ChangeRequest(Base):
    __tablename__ = "dlv_change_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    project_id: Mapped[int] = mapped_column(ForeignKey("dlv_projects.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="requested")
    cost_minor: Mapped[int | None] = mapped_column(Integer)
    days_impact: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class TimeEntry(Base):
    __tablename__ = "dlv_time_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    project_id: Mapped[int] = mapped_column(ForeignKey("dlv_projects.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    worked_on: Mapped[date] = mapped_column(Date, nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ProjectIn(In):
    title: str = Field(min_length=1, max_length=300)
    organization_id: Optional[int] = None
    status: Literal["planned", "active", "on_hold", "done", "cancelled"] = "planned"
    start_on: Optional[date] = None
    end_on: Optional[date] = None
    budget_minor: Optional[Money] = None
    currency: Currency = None
    github_repo: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", description="owner/name")
    description: Optional[str] = None


class MilestoneIn(In):
    project_id: int
    title: str = Field(min_length=1, max_length=300)
    due_on: Optional[date] = None
    status: Literal["planned", "in_progress", "done", "cancelled"] = "planned"
    amount_minor: Optional[Money] = None


class ChangeRequestIn(In):
    project_id: int
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    status: Literal["requested", "approved", "rejected", "done"] = "requested"
    cost_minor: Optional[Money] = None
    days_impact: Optional[int] = Field(default=None, ge=0)


class TimeEntryIn(In):
    project_id: int
    worked_on: date
    minutes: int = Field(gt=0, le=24 * 60)
    billable: bool = True
    note: Optional[str] = Field(default=None, max_length=500)
    user_id: Optional[int] = None


def _milestone_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    if values.get("status") == "done" and (obj is None or obj.status != "done"):
        values["completed_on"] = _today(db, p.workspace_id)
    elif "status" in values and values["status"] != "done":
        values["completed_on"] = None
    return values


def _time_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    if obj is None and not values.get("user_id"):
        values["user_id"] = p.user_id  # log time as yourself unless stated
    return values


def _project_dates(db: Session, p: Principal, values: dict, obj) -> dict:
    start = values.get("start_on", obj.start_on if obj else None)
    end = values.get("end_on", obj.end_on if obj else None)
    if start and end and end < start:
        raise HTTPException(422, "end_on is before start_on")
    return values


def _today(db: Session, ws_id: int) -> date:
    ws = db.get(Workspace, ws_id)
    return datetime.now(ZoneInfo(ws.timezone if ws else "Africa/Nairobi")).date()


# ── Status logic ─────────────────────────────────────────────────────────────

def github_commits(repo: str, since: datetime, getter=httpx.get) -> list[dict] | str:
    """Commits since `since` via GET /repos/{repo}/commits. Returns a list, or a
    short string explaining why commits are unavailable (never raises)."""
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = getter(f"https://api.github.com/repos/{repo}/commits",
                   params={"since": since.isoformat(), "per_page": 50}, headers=headers, timeout=15)
    except httpx.HTTPError as e:
        return f"GitHub unreachable ({type(e).__name__})"
    if r.status_code != 200:
        return f"GitHub returned {r.status_code} (private repo needs GITHUB_TOKEN)"
    return [{"sha": c["sha"][:7], "message": c["commit"]["message"].splitlines()[0][:120],
             "date": c["commit"]["author"]["date"]} for c in r.json()]


def project_status(db: Session, ws_id: int, project_id: int, days: int = 7, getter=httpx.get) -> str:
    pr = get_scoped(db, Project, project_id, ws_id)
    if pr is None:
        raise HTTPException(404, "project not found")
    today = _today(db, ws_id)
    since = today - timedelta(days=days)
    ms = db.execute(scoped(Milestone, ws_id).where(Milestone.project_id == pr.id).order_by(Milestone.due_on.nulls_last())).scalars().all()
    done = [m for m in ms if m.status == "done"]
    overdue = [m for m in ms if m.status not in ("done", "cancelled") and m.due_on and m.due_on < today]
    upcoming = [m for m in ms if m.status not in ("done", "cancelled") and m.due_on and m.due_on >= today][:3]
    minutes = db.execute(select(func.coalesce(func.sum(TimeEntry.minutes), 0)).where(
        TimeEntry.workspace_id == ws_id, TimeEntry.project_id == pr.id, TimeEntry.worked_on > since)).scalar_one()
    crs = db.execute(scoped(ChangeRequest, ws_id).where(ChangeRequest.project_id == pr.id,
                                                        ChangeRequest.status.in_(["requested", "approved"]))).scalars().all()
    org = db.get(Organization, pr.organization_id) if pr.organization_id else None
    lines = [f"Status — {pr.title}" + (f" for {org.name}" if org else "") + f" ({since.isoformat()} to {today.isoformat()})",
             f"Milestones: {len(done)}/{len(ms)} done"]
    lines += [f"  ✔ {m.title} (done {m.completed_on})" for m in done if m.completed_on and m.completed_on > since]
    lines += [f"  ⚠ overdue: {m.title} (due {m.due_on})" for m in overdue]
    lines += [f"  → next: {m.title} (due {m.due_on})" for m in upcoming]
    lines.append(f"Time logged in the period: {minutes / 60:.1f} h")
    if crs:
        lines.append("Open change requests:")
        lines += [f"  • {c.title} [{c.status}]" + (f" cost {money(c.cost_minor, pr.currency)}" if c.cost_minor else "") for c in crs]
    if pr.github_repo:
        commits = github_commits(pr.github_repo, datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc), getter)
        if isinstance(commits, str):
            lines.append(f"Code: {commits}")
        else:
            lines.append(f"Code: {len(commits)} commit(s) on {pr.github_repo}")
            lines += [f"  • {c['message']} ({c['sha']})" for c in commits[:10]]
    return "\n".join(lines)


def projects_report(db: Session, p: Principal, params: dict) -> dict:
    today = _today(db, p.workspace_id)
    rows = []
    for pr in db.execute(scoped(Project, p.workspace_id).where(Project.status.in_(["planned", "active", "on_hold"]))
                         .order_by(Project.id)).scalars():
        ms = db.execute(scoped(Milestone, p.workspace_id).where(Milestone.project_id == pr.id)).scalars().all()
        overdue = sum(1 for m in ms if m.status not in ("done", "cancelled") and m.due_on and m.due_on < today)
        hours = db.execute(select(func.coalesce(func.sum(TimeEntry.minutes), 0)).where(
            TimeEntry.workspace_id == p.workspace_id, TimeEntry.project_id == pr.id)).scalar_one() / 60
        rows.append([pr.id, pr.title, pr.status, f"{sum(m.status == 'done' for m in ms)}/{len(ms)}", overdue, f"{hours:.1f}"])
    return table("Active projects", f"{len(rows)} project(s)", ["#", "Project", "Status", "Milestones", "Overdue", "Hours"], rows)


def status_report_(db: Session, p: Principal, params: dict) -> dict:
    if "project_id" not in params:
        raise HTTPException(422, "project_id is required")
    return table("Weekly status", project_status(db, p.workspace_id, int(params["project_id"])), [], [])


def brief(db: Session, ws_id: int) -> list[str]:
    today = _today(db, ws_id)
    overdue = db.execute(scoped(Milestone, ws_id).where(Milestone.status.not_in(["done", "cancelled"]),
                                                        Milestone.due_on < today)).scalars().all()
    return [f"overdue milestone: {m.title} (due {m.due_on})" for m in overdue[:5]]


def _status_reporter(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return "Give the project number, e.g. '3'. See the Delivery → Active projects report.", []
    return project_status(ctx.db, ctx.principal.workspace_id, int(digits)), []


def register() -> None:
    register_permissions({"delivery.read": {F, S, C, A}, "delivery.write": {F, S, C}, "delivery.delete": {F}})
    perms = dict(read_perm="delivery.read", write_perm="delivery.write", delete_perm="delivery.delete", department=DEPT)
    rr = records.register_record_type
    rr("project", records.RecordType(Project, ProjectIn, patch_of(ProjectIn), out_of(Project), ("title", "description"),
                                     label="Projects", refs={"organization_id": "organization"},
                                     prepare=chain(default_currency, _project_dates), **perms))
    rr("milestone", records.RecordType(Milestone, MilestoneIn, patch_of(MilestoneIn), out_of(Milestone), ("title",),
                                       label="Milestones", refs={"project_id": "project"}, prepare=_milestone_hook, **perms))
    rr("change_request", records.RecordType(ChangeRequest, ChangeRequestIn, patch_of(ChangeRequestIn), out_of(ChangeRequest),
                                            ("title", "description"), label="Change requests", refs={"project_id": "project"}, **perms))
    rr("time_entry", records.RecordType(TimeEntry, TimeEntryIn, patch_of(TimeEntryIn), out_of(TimeEntry), ("note",),
                                        label="Time entries", title_field="note",
                                        refs={"project_id": "project", "user_id": "user"}, prepare=_time_hook, **perms))
    register_report(Report("delivery.projects", DEPT, "Active projects", projects_report, "delivery.read"))
    register_report(Report("delivery.status", DEPT, "Weekly status (project)", status_report_, "delivery.read",
                           params=("project_id",)))
    register_brief_section(DEPT, "Delivery", brief)
    register_agent(AgentSpec(name="status_reporter", description="Drafts a project's weekly status from milestones, time, change requests and GitHub.",
                             handler=_status_reporter, permission="delivery.read", input_hint="Project number"))
    register_agent(AgentSpec(name="scoper", description="Drafts an SOW note from client notes, with explicit assumptions and exclusions.",
                             tools=("search_memory", "create_note"), permission="delivery.write",
                             input_hint="Paste the client's request / meeting notes"))
    register_department(Department(DEPT, "Delivery", 3, "Projects, milestones, change requests and time.", "delivery.read",
                                   ("project", "milestone", "change_request", "time_entry"),
                                   ("status_reporter", "scoper"), "directives/103_delivery.md"))
