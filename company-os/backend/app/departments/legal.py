"""
Department 6 — Legal & Compliance (directive 106). Founder writes; advisors read.

Records: contract, obligation, legal_template, processing_activity (the data-processing register).
NOT LEGAL ADVICE. Nothing here decides what the law requires:
  - the OS contains no statute text, lawful-basis list, registration threshold or deadline;
  - obligations extracted by the contract_reader agent are `verified = false` and
    must quote the clause they came from; a human verifies them;
  - template_filler refuses templates that have no recorded lawyer review.
Kenya Data Protection Act 2019 / ODPC duties: record YOUR lawyer's conclusions in
the register; the OS keeps them organised and reminds you.
Job:     obligations_check — notice deadlines within 30 days, obligations due within 7.
Reports: legal.renewals, legal.obligations, legal.register
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.departments._kit import Currency, In, Money, _ts, _ws, chain, default_currency, out_of, patch_of
from app.kernel import records
from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import Effect, Tool, ToolContext, register_tool
from app.kernel.agents.untrusted import wrap
from app.kernel.departments import (
    Department,
    Job,
    Report,
    register_brief_section,
    register_department,
    register_job,
    register_report,
    table,
)
from app.kernel.models import Document, Workspace
from app.kernel.notifications import founders, notify
from app.kernel.rbac import A, F, register_permissions
from app.kernel.tenancy import Principal, get_scoped, scoped

DEPT = "legal"
PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


class Contract(Base):
    __tablename__ = "legal_contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="other")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    signed_on: Mapped[date | None] = mapped_column(Date)
    start_on: Mapped[date | None] = mapped_column(Date)
    end_on: Mapped[date | None] = mapped_column(Date)
    auto_renews: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notice_days: Mapped[int | None] = mapped_column(Integer)
    value_minor: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Obligation(Base):
    __tablename__ = "legal_obligations"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("legal_contracts.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date)
    recurrence: Mapped[str] = mapped_column(String(20), nullable=False, server_default="none")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    source_clause: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class LegalTemplate(Base):
    __tablename__ = "legal_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="other")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    reviewed_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ProcessingActivity(Base):
    __tablename__ = "legal_processing_activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="controller")
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    data_categories: Mapped[str | None] = mapped_column(Text)
    data_subjects: Mapped[str | None] = mapped_column(Text)
    lawful_basis: Mapped[str | None] = mapped_column(Text)
    recipients: Mapped[str | None] = mapped_column(Text)
    cross_border: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    retention: Mapped[str | None] = mapped_column(Text)
    security_measures: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    reviewed_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


Kind = Literal["msa", "sow", "nda", "dpa", "employment", "contractor", "vendor", "lease", "other"]


class ContractIn(In):
    title: str = Field(min_length=1, max_length=300)
    organization_id: Optional[int] = None
    kind: Kind = "other"
    status: Literal["draft", "negotiating", "signed", "expired", "terminated"] = "draft"
    signed_on: Optional[date] = None
    start_on: Optional[date] = None
    end_on: Optional[date] = None
    auto_renews: bool = False
    notice_days: Optional[int] = Field(default=None, ge=0, le=3650)
    value_minor: Optional[Money] = None
    currency: Currency = None
    document_id: Optional[int] = None
    notes: Optional[str] = None


class ObligationIn(In):
    title: str = Field(min_length=1, max_length=500, description="What must be done")
    contract_id: Optional[int] = None
    due_on: Optional[date] = None
    recurrence: Literal["none", "monthly", "quarterly", "yearly"] = "none"
    status: Literal["open", "done", "not_applicable"] = "open"
    source_clause: Optional[str] = None
    verified: bool = False


class LegalTemplateIn(In):
    title: str = Field(min_length=1, max_length=300)
    kind: Kind = "other"
    body: str = Field(min_length=1, description="Use {{placeholders}} for values")
    reviewed_by: Optional[str] = Field(default=None, max_length=200, description="Lawyer who reviewed it")
    reviewed_on: Optional[date] = None


class ProcessingActivityIn(In):
    title: str = Field(min_length=1, max_length=300)
    role: Literal["controller", "processor"] = "controller"
    purpose: str = Field(min_length=1)
    data_categories: Optional[str] = None
    data_subjects: Optional[str] = None
    lawful_basis: Optional[str] = Field(default=None, description="As advised by your lawyer")
    recipients: Optional[str] = None
    cross_border: bool = False
    retention: Optional[str] = None
    security_measures: Optional[str] = None
    reviewed_by: Optional[str] = Field(default=None, max_length=200)
    reviewed_on: Optional[date] = None


def _contract_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    start = values.get("start_on", obj.start_on if obj else None)
    end = values.get("end_on", obj.end_on if obj else None)
    if start and end and end < start:
        raise HTTPException(422, "end_on is before start_on")
    return values


def _template_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    # Editing the body of a reviewed template voids the review: the lawyer approved different text.
    if obj is not None and "body" in values and values["body"] != obj.body and "reviewed_on" not in values:
        values["reviewed_on"] = None
        values["reviewed_by"] = None
    if values.get("reviewed_on") and not (values.get("reviewed_by") or (obj is not None and obj.reviewed_by)):
        raise HTTPException(422, "reviewed_by (the lawyer's name) is required with reviewed_on")
    return values


# ── Logic & reports ──────────────────────────────────────────────────────────

def _today(db: Session, ws_id: int) -> date:
    ws = db.get(Workspace, ws_id)
    return datetime.now(ZoneInfo(ws.timezone if ws else "Africa/Nairobi")).date()


def notice_deadline(c: Contract) -> date | None:
    if c.end_on is None:
        return None
    return c.end_on - timedelta(days=c.notice_days or 0)


def upcoming_deadlines(db: Session, ws_id: int, days: int) -> list[tuple[Contract, date]]:
    today = _today(db, ws_id)
    out = []
    for c in db.execute(scoped(Contract, ws_id).where(Contract.status == "signed")).scalars():
        nd = notice_deadline(c)
        if nd and today <= nd <= today + timedelta(days=days):
            out.append((c, nd))
    return sorted(out, key=lambda x: x[1])


def due_obligations(db: Session, ws_id: int, days: int) -> list[Obligation]:
    until = _today(db, ws_id) + timedelta(days=days)
    return list(db.execute(scoped(Obligation, ws_id).where(Obligation.status == "open", Obligation.due_on <= until)
                           .order_by(Obligation.due_on)).scalars())


def renewals_report(db: Session, p: Principal, params: dict) -> dict:
    days = int(params.get("days") or 90)
    rows = [[c.id, c.title, c.kind, c.end_on.isoformat(), "yes" if c.auto_renews else "no", nd.isoformat()]
            for c, nd in upcoming_deadlines(db, p.workspace_id, days)]
    return table("Renewal / notice deadlines", f"Signed contracts whose notice deadline falls in the next {days} days",
                 ["#", "Contract", "Kind", "Ends", "Auto-renews", "Give notice by"], rows)


def obligations_report(db: Session, p: Principal, params: dict) -> dict:
    rows = []
    for o in db.execute(scoped(Obligation, p.workspace_id).where(Obligation.status == "open")
                        .order_by(Obligation.due_on.nulls_last())).scalars():
        rows.append([o.id, o.title, o.due_on.isoformat() if o.due_on else "—", o.recurrence,
                     "verified" if o.verified else "UNVERIFIED"])
    unverified = sum(1 for r in rows if r[4] == "UNVERIFIED")
    return table("Open obligations", f"{len(rows)} open, {unverified} not yet verified by a person",
                 ["#", "Obligation", "Due", "Repeats", "Verification"], rows)


def register_report_(db: Session, p: Principal, params: dict) -> dict:
    rows = [[a.title, a.role, a.lawful_basis or "— (ask your lawyer)", "yes" if a.cross_border else "no",
             a.retention or "—", f"{a.reviewed_by} {a.reviewed_on}" if a.reviewed_on else "not reviewed"]
            for a in db.execute(scoped(ProcessingActivity, p.workspace_id).order_by(ProcessingActivity.id)).scalars()]
    return table("Data-processing register", "Your record of processing. Legal conclusions must come from your lawyer.",
                 ["Activity", "Role", "Lawful basis", "Cross-border", "Retention", "Review"], rows)


def brief(db: Session, ws_id: int) -> list[str]:
    out = [f"give notice by {nd}: {c.title}" for c, nd in upcoming_deadlines(db, ws_id, 30)]
    out += [f"obligation due {o.due_on}: {o.title}" + ("" if o.verified else " (unverified)") for o in due_obligations(db, ws_id, 7)]
    return out


def obligations_check(db: Session, ws_id: int) -> str:
    deadlines = upcoming_deadlines(db, ws_id, 30)
    due = due_obligations(db, ws_id, 7)
    if deadlines or due:
        body = "\n".join(brief(db, ws_id))
        for uid in founders(db, ws_id):
            notify(db, ws_id, uid, "Legal dates coming up", body, link="/d/legal")
    return f"{len(deadlines)} notice deadline(s) ≤30d, {len(due)} obligation(s) ≤7d"


# ── Agents & tools ───────────────────────────────────────────────────────────

def _read_contract(ctx: ToolContext, args: dict) -> dict:
    c = get_scoped(ctx.db, Contract, int(args["contract_id"]), ctx.principal.workspace_id)
    if c is None:
        raise ValueError("contract not found")
    if not c.document_id:
        return {"error": "This contract has no document attached. Attach the signed text in Memory and set document_id."}
    doc = get_scoped(ctx.db, Document, c.document_id, ctx.principal.workspace_id)
    return {"contract": {"id": c.id, "title": c.title, "kind": c.kind}, "text": wrap(f"contract:{c.id}", doc.content[:60000]),
            "truncated": len(doc.content) > 60000}


def _add_obligation(ctx: ToolContext, args: dict) -> dict:
    c = get_scoped(ctx.db, Contract, int(args["contract_id"]), ctx.principal.workspace_id)
    if c is None:
        raise ValueError("contract not found")
    doc = get_scoped(ctx.db, Document, c.document_id, ctx.principal.workspace_id) if c.document_id else None
    quote = " ".join(args["source_clause"].split())
    if doc is None or quote.lower() not in " ".join(doc.content.split()).lower():
        # The quote must exist verbatim in the contract: an obligation nobody can trace is not recorded.
        raise ValueError("source_clause is not an exact quote from the contract text")
    data = ObligationIn(title=args["title"], contract_id=c.id, due_on=args.get("due_on"),
                        recurrence=args.get("recurrence", "none"), source_clause=args["source_clause"], verified=False)
    o = records.create_record(ctx.db, ctx.principal, "obligation", data, agent_run_id=ctx.agent_run_id)
    return {"obligation_id": o.id, "verified": False}


def fill_template(body: str, values: dict[str, str]) -> tuple[str, list[str]]:
    missing = sorted({m for m in PLACEHOLDER.findall(body) if not str(values.get(m, "")).strip()})
    return PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), body), missing


def _template_filler(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    """Input: first line = template number; following lines = key: value."""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if not lines or not lines[0].strip().lstrip("#").isdigit():
        return "First line: template number. Then one 'placeholder: value' per line.", []
    t = get_scoped(ctx.db, LegalTemplate, int(lines[0].strip().lstrip("#")), ctx.principal.workspace_id)
    if t is None:
        return "No such template.", []
    if not (t.reviewed_on and t.reviewed_by):
        return (f"Refused: '{t.title}' has no recorded lawyer review. Record reviewed_by and reviewed_on first — "
                "the OS only fills templates a lawyer approved."), []
    values = {k.strip(): v.strip() for k, _, v in (ln.partition(":") for ln in lines[1:]) if k.strip()}
    filled, missing = fill_template(t.body, values)
    head = f"Filled from '{t.title}' (reviewed by {t.reviewed_by} on {t.reviewed_on})."
    if missing:
        head += f" MISSING values: {', '.join(missing)} — left as {{{{placeholders}}}}."
    return f"{head}\n\n{filled}", []


def register() -> None:
    register_permissions({"legal.read": {F, A}, "legal.write": {F}})
    perms = dict(read_perm="legal.read", write_perm="legal.write", delete_perm="legal.write", department=DEPT)
    rr = records.register_record_type
    rr("contract", records.RecordType(Contract, ContractIn, patch_of(ContractIn), out_of(Contract), ("title", "notes"),
                                      label="Contracts", refs={"organization_id": "organization", "document_id": "document"},
                                      prepare=chain(default_currency, _contract_hook), **perms))
    rr("obligation", records.RecordType(Obligation, ObligationIn, patch_of(ObligationIn), out_of(Obligation),
                                        ("title", "source_clause"), label="Obligations", refs={"contract_id": "contract"}, **perms))
    rr("legal_template", records.RecordType(LegalTemplate, LegalTemplateIn, patch_of(LegalTemplateIn), out_of(LegalTemplate),
                                            ("title", "body"), label="Templates", prepare=_template_hook, **perms))
    rr("processing_activity", records.RecordType(ProcessingActivity, ProcessingActivityIn, patch_of(ProcessingActivityIn),
                                                 out_of(ProcessingActivity), ("title", "purpose"),
                                                 label="Processing register", **perms))
    register_report(Report("legal.renewals", DEPT, "Renewal & notice deadlines", renewals_report, "legal.read", params=("days",)))
    register_report(Report("legal.obligations", DEPT, "Open obligations", obligations_report, "legal.read"))
    register_report(Report("legal.register", DEPT, "Data-processing register", register_report_, "legal.read"))
    register_job(Job("obligations_check", DEPT, obligations_check, "daily 08:00 Africa/Nairobi"))
    register_brief_section(DEPT, "Legal", brief)
    register_tool(Tool(name="read_contract", description="Read a contract's attached document text.", effect=Effect.READ,
                       permission="legal.read", handler=_read_contract,
                       input_schema={"type": "object", "additionalProperties": False, "required": ["contract_id"],
                                     "properties": {"contract_id": {"type": "integer"}}}))
    register_tool(Tool(name="add_obligation", effect=Effect.INTERNAL, permission="legal.write", handler=_add_obligation,
                       description="Record an UNVERIFIED obligation. source_clause must be an exact quote from the contract.",
                       input_schema={"type": "object", "additionalProperties": False,
                                     "required": ["contract_id", "title", "source_clause"],
                                     "properties": {"contract_id": {"type": "integer"}, "title": {"type": "string", "maxLength": 500},
                                                    "source_clause": {"type": "string"},
                                                    "due_on": {"type": "string", "description": "YYYY-MM-DD, only if the text states it"},
                                                    "recurrence": {"type": "string", "enum": ["none", "monthly", "quarterly", "yearly"]}}}))
    register_agent(AgentSpec(name="contract_reader", description="Extracts dates and obligations from a contract, quoting each clause.",
                             tools=("read_contract", "add_obligation"), permission="legal.write", input_hint="Contract number"))
    register_agent(AgentSpec(name="template_filler", description="Fills a lawyer-reviewed template; refuses unreviewed ones.",
                             handler=_template_filler, permission="legal.write",
                             input_hint="Line 1: template number. Then 'placeholder: value' lines."))
    register_department(Department(DEPT, "Legal", 6, "Contracts, obligations, templates and the data-processing register. Not legal advice.",
                                   "legal.read", ("contract", "obligation", "legal_template", "processing_activity"),
                                   ("contract_reader", "template_filler"), "directives/106_legal.md"))
