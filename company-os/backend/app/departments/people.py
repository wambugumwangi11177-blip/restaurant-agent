"""
Department 9 — People & HR (directive 109). Founder-only. Built now, used from
the first hire or contractor.

Records: staff_record, checklist_item, access_grant.
Agents:  onboarding (creates the onboarding checklist from YOUR list in the
         `onboarding_checklist` setting), offboarding (creates one revoke item per
         active access grant + removing Company OS membership). External systems
         (Google, GitHub, banks…) can't be revoked by the OS — they become checklist
         items a person ticks off.
Reports: people.roster, people.access_risk (people who left with access still active)
No employment-law rules (notice, leave, payroll statutory deductions) are built in.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.departments._kit import In, _ts, _ws, out_of, patch_of
from app.kernel import records
from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import ToolContext
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
from app.kernel.models import Person, Workspace
from app.kernel.rbac import F, register_permissions
from app.kernel.tenancy import Principal, get_scoped, scoped
from app.kernel.workspaces import setting

DEPT = "people"
DEFAULT_ONBOARDING = ["Signed contract stored (attach in Legal)", "Company OS account created with the right role",
                      "Accounts created for the tools they need (record each as an access grant)", "First-week plan agreed"]


class StaffRecord(Base):
    __tablename__ = "ppl_staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="contractor")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="onboarding")
    start_on: Mapped[date | None] = mapped_column(Date)
    end_on: Mapped[date | None] = mapped_column(Date)
    contract_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ChecklistItem(Base):
    __tablename__ = "ppl_checklist_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    staff_id: Mapped[int] = mapped_column(ForeignKey("ppl_staff.id", ondelete="CASCADE"), nullable=False, index=True)
    phase: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    done_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class AccessGrant(Base):
    __tablename__ = "ppl_access_grants"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    staff_id: Mapped[int] = mapped_column(ForeignKey("ppl_staff.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    account: Mapped[str | None] = mapped_column(String(200))
    granted_on: Mapped[date | None] = mapped_column(Date)
    revoked_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class StaffRecordIn(In):
    person_id: int
    title: str = Field(min_length=1, max_length=200, description="Role title")
    user_id: Optional[int] = None
    kind: Literal["employee", "contractor", "intern", "advisor"] = "contractor"
    status: Literal["onboarding", "active", "offboarding", "left"] = "onboarding"
    start_on: Optional[date] = None
    end_on: Optional[date] = None
    contract_document_id: Optional[int] = None
    notes: Optional[str] = None


class ChecklistItemIn(In):
    staff_id: int
    phase: Literal["onboarding", "offboarding"]
    title: str = Field(min_length=1, max_length=300)
    done: bool = False


class AccessGrantIn(In):
    staff_id: int
    title: str = Field(min_length=1, max_length=200, description="System, e.g. GitHub, Google Workspace, M-Pesa portal")
    account: Optional[str] = Field(default=None, max_length=200)
    granted_on: Optional[date] = None
    revoked_on: Optional[date] = None


def _today(db: Session, ws_id: int) -> date:
    ws = db.get(Workspace, ws_id)
    return datetime.now(ZoneInfo(ws.timezone if ws else "Africa/Nairobi")).date()


def _checklist_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    if values.get("done") and (obj is None or not obj.done):
        values["done_on"] = _today(db, p.workspace_id)
    elif values.get("done") is False:
        values["done_on"] = None
    return values


def _staff_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    if values.get("status") == "left" and not (values.get("end_on") or (obj is not None and obj.end_on)):
        values["end_on"] = _today(db, p.workspace_id)
    return values


def _name(db: Session, s: StaffRecord) -> str:
    person = db.get(Person, s.person_id)
    return person.full_name if person else f"staff #{s.id}"


def access_risk(db: Session, ws_id: int) -> list[tuple[StaffRecord, AccessGrant]]:
    out = []
    for s in db.execute(scoped(StaffRecord, ws_id).where(StaffRecord.status.in_(["offboarding", "left"]))).scalars():
        for g in db.execute(scoped(AccessGrant, ws_id).where(AccessGrant.staff_id == s.id, AccessGrant.revoked_on.is_(None))).scalars():
            out.append((s, g))
    return out


def roster_report(db: Session, p: Principal, params: dict) -> dict:
    rows = []
    for s in db.execute(scoped(StaffRecord, p.workspace_id).where(StaffRecord.status != "left").order_by(StaffRecord.id)).scalars():
        items = db.execute(scoped(ChecklistItem, p.workspace_id).where(ChecklistItem.staff_id == s.id,
                                                                      ChecklistItem.phase == "onboarding")).scalars().all()
        rows.append([_name(db, s), s.title, s.kind, s.status, s.start_on.isoformat() if s.start_on else "—",
                     f"{sum(i.done for i in items)}/{len(items)}"])
    return table("Team", "", ["Name", "Role", "Kind", "Status", "Started", "Onboarding"], rows)


def access_risk_report(db: Session, p: Principal, params: dict) -> dict:
    rows = [[_name(db, s), s.status, g.title, g.account or "—"] for s, g in access_risk(db, p.workspace_id)]
    return table("Access still active after departure", f"{len(rows)} grant(s) to revoke", ["Person", "Status", "System", "Account"], rows)


def brief(db: Session, ws_id: int) -> list[str]:
    return [f"revoke {g.title} for {_name(db, s)} ({s.status})" for s, g in access_risk(db, ws_id)[:5]]


def _staff_from(ctx: ToolContext, text: str) -> StaffRecord | None:
    digits = "".join(ch for ch in text if ch.isdigit())
    return get_scoped(ctx.db, StaffRecord, int(digits), ctx.principal.workspace_id) if digits else None


def _add_items(ctx: ToolContext, staff: StaffRecord, phase: str, titles: list[str]) -> list[str]:
    existing = {i.title for i in ctx.db.execute(scoped(ChecklistItem, ctx.principal.workspace_id).where(
        ChecklistItem.staff_id == staff.id, ChecklistItem.phase == phase)).scalars()}
    created = []
    for t in titles:
        if t in existing:
            continue
        records.create_record(ctx.db, ctx.principal, "checklist_item",
                              ChecklistItemIn(staff_id=staff.id, phase=phase, title=t[:300]), agent_run_id=ctx.agent_run_id)
        created.append(t)
    return created


def _onboarding(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    staff = _staff_from(ctx, text)
    if staff is None:
        return "Give the staff record number.", []
    custom = setting(ctx.db, ctx.principal.workspace_id, "onboarding_checklist")
    titles = [ln.strip() for ln in custom.splitlines() if ln.strip()] if custom else DEFAULT_ONBOARDING
    created = _add_items(ctx, staff, "onboarding", titles)
    src = "your onboarding_checklist setting" if custom else "the default list (set onboarding_checklist to use your own)"
    return f"Added {len(created)} onboarding item(s) for {_name(ctx.db, staff)} from {src}.", []


def _offboarding(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    staff = _staff_from(ctx, text)
    if staff is None:
        return "Give the staff record number.", []
    grants = ctx.db.execute(scoped(AccessGrant, ctx.principal.workspace_id).where(
        AccessGrant.staff_id == staff.id, AccessGrant.revoked_on.is_(None))).scalars().all()
    titles = [f"Revoke {g.title}" + (f" ({g.account})" if g.account else "") for g in grants]
    if staff.user_id:
        titles.append("Remove their Company OS membership (Settings → Members) — ends all their sessions")
    titles += ["Collect company devices and documents", "Final payment and contract close-out (confirm terms with your lawyer/accountant)"]
    if staff.status not in ("offboarding", "left"):
        records.update_record(ctx.db, ctx.principal, "staff_record", staff.id,
                              records.RECORD_TYPES["staff_record"].patch(status="offboarding"), agent_run_id=ctx.agent_run_id)
    created = _add_items(ctx, staff, "offboarding", titles)
    return f"Offboarding {_name(ctx.db, staff)}: {len(created)} item(s) added; {len(grants)} access grant(s) to revoke.", []


def register() -> None:
    register_permissions({"people.read": {F}, "people.write": {F}})
    register_setting(SettingSpec("onboarding_checklist", DEPT, "Your onboarding steps, one per line"))
    perms = dict(read_perm="people.read", write_perm="people.write", delete_perm="people.write", department=DEPT)
    rr = records.register_record_type
    rr("staff_record", records.RecordType(StaffRecord, StaffRecordIn, patch_of(StaffRecordIn), out_of(StaffRecord),
                                          ("title", "notes"), label="Team",
                                          refs={"person_id": "person", "user_id": "user", "contract_document_id": "document"},
                                          prepare=_staff_hook, **perms))
    rr("checklist_item", records.RecordType(ChecklistItem, ChecklistItemIn, patch_of(ChecklistItemIn), out_of(ChecklistItem),
                                            ("title",), label="Checklists", refs={"staff_id": "staff_record"},
                                            prepare=_checklist_hook, **perms))
    rr("access_grant", records.RecordType(AccessGrant, AccessGrantIn, patch_of(AccessGrantIn), out_of(AccessGrant),
                                          ("title", "account"), label="Access grants", refs={"staff_id": "staff_record"}, **perms))
    register_report(Report("people.roster", DEPT, "Team", roster_report, "people.read"))
    register_report(Report("people.access_risk", DEPT, "Access still active after departure", access_risk_report, "people.read"))
    register_brief_section(DEPT, "People", brief)
    register_agent(AgentSpec(name="onboarding", description="Creates a new team member's onboarding checklist.",
                             handler=_onboarding, permission="people.write", input_hint="Staff record number"))
    register_agent(AgentSpec(name="offboarding", description="Creates the offboarding checklist, one revoke step per access grant.",
                             handler=_offboarding, permission="people.write", input_hint="Staff record number"))
    register_department(Department(DEPT, "People", 9, "Team records, on/offboarding and access.", "people.read",
                                   ("staff_record", "checklist_item", "access_grant"), ("onboarding", "offboarding"),
                                   "directives/109_people.md"))
