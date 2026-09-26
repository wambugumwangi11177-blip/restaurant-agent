"""
Department 8 — Product & Roadmap (directive 108)

Records: feature_request, roadmap_item, release_note.
Agent:   signal_aggregator (deterministic). Ranks roadmap candidates by
         (distinct requesting clients, open-deal value of those clients per
         currency, request count). Deal data is read through the Kernel record
         registry only when Sales is enabled — never by importing Sales.
Reports: product.signals, product.roadmap
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import Field
from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.departments._kit import In, _ts, _ws, money, out_of, patch_of
from app.kernel import records
from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import ToolContext
from app.kernel.departments import Department, Report, register_brief_section, register_department, register_report, table
from app.kernel.models import Organization
from app.kernel.rbac import A, C, F, S, register_permissions
from app.kernel.tenancy import Principal, scoped
from app.kernel.workspaces import department_enabled

DEPT = "product"


class FeatureRequest(Base):
    __tablename__ = "prd_feature_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="other")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="new")
    roadmap_item_id: Mapped[int | None] = mapped_column(ForeignKey("prd_roadmap_items.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class RoadmapItem(Base):
    __tablename__ = "prd_roadmap_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="idea")
    target_quarter: Mapped[str | None] = mapped_column(String(7))
    shipped_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ReleaseNote(Base):
    __tablename__ = "prd_release_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    version: Mapped[str | None] = mapped_column(String(40))
    released_on: Mapped[date | None] = mapped_column(Date)
    roadmap_item_id: Mapped[int | None] = mapped_column(ForeignKey("prd_roadmap_items.id", ondelete="SET NULL"))
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class FeatureRequestIn(In):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    organization_id: Optional[int] = None
    source: Literal["ticket", "deal", "meeting", "internal", "other"] = "other"
    status: Literal["new", "planned", "shipped", "declined"] = "new"
    roadmap_item_id: Optional[int] = None


class RoadmapItemIn(In):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    status: Literal["idea", "planned", "in_progress", "shipped", "dropped"] = "idea"
    target_quarter: Optional[str] = Field(default=None, pattern=r"^\d{4}-Q[1-4]$", description="e.g. 2026-Q4")
    shipped_on: Optional[date] = None


class ReleaseNoteIn(In):
    title: str = Field(min_length=1, max_length=300)
    version: Optional[str] = Field(default=None, max_length=40)
    released_on: Optional[date] = None
    roadmap_item_id: Optional[int] = None
    body: Optional[str] = None


def _roadmap_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    if values.get("status") == "shipped" and not values.get("shipped_on") and (obj is None or not obj.shipped_on):
        values["shipped_on"] = datetime.now(timezone.utc).date()
    return values


def _open_deal_value_by_org(db: Session, ws_id: int) -> dict[int, dict[str, int]] | None:
    if not department_enabled(db, ws_id, "sales") or "deal" not in records.RECORD_TYPES:
        return None
    deal = records.RECORD_TYPES["deal"].model
    out: dict[int, dict[str, int]] = defaultdict(dict)
    for d in db.execute(scoped(deal, ws_id).where(deal.stage.in_(["lead", "qualified", "proposal", "negotiation"]),
                                                  deal.organization_id.is_not(None))).scalars():
        out[d.organization_id][d.currency] = out[d.organization_id].get(d.currency, 0) + d.value_minor
    return out


def signals(db: Session, ws_id: int) -> list[dict]:
    deal_value = _open_deal_value_by_org(db, ws_id)
    groups: dict[str, dict] = {}
    for fr in db.execute(scoped(FeatureRequest, ws_id).where(FeatureRequest.status.in_(["new", "planned"]))).scalars():
        key = f"roadmap:{fr.roadmap_item_id}" if fr.roadmap_item_id else f"request:{fr.id}"
        g = groups.setdefault(key, {"title": None, "requests": 0, "orgs": set(), "value": defaultdict(int)})
        if fr.roadmap_item_id:
            ri = db.get(RoadmapItem, fr.roadmap_item_id)
            g["title"] = f"[roadmap] {ri.title}" if ri else fr.title
        else:
            g["title"] = fr.title
        g["requests"] += 1
        if fr.organization_id:
            g["orgs"].add(fr.organization_id)
    for g in groups.values():
        for org_id in g["orgs"]:
            for cur, v in (deal_value or {}).get(org_id, {}).items():
                g["value"][cur] += v
    ranked = sorted(groups.values(), key=lambda g: (len(g["orgs"]), sum(g["value"].values()), g["requests"]), reverse=True)
    return [{"title": g["title"], "clients": len(g["orgs"]), "requests": g["requests"],
             "open_deal_value": ", ".join(money(v, c) for c, v in sorted(g["value"].items())) or ("—" if deal_value is not None else "sales not enabled"),
             "client_names": sorted(db.get(Organization, o).name for o in g["orgs"] if db.get(Organization, o))}
            for g in ranked]


def signals_report(db: Session, p: Principal, params: dict) -> dict:
    rows = [[s["title"], s["clients"], s["requests"], s["open_deal_value"], ", ".join(s["client_names"])] for s in signals(db, p.workspace_id)]
    return table("Product signals", "Ranked by distinct clients, then open deal value, then request count. "
                 "Deal value is summed per currency (no FX).", ["Candidate", "Clients", "Requests", "Open deal value", "Who"], rows)


def roadmap_report(db: Session, p: Principal, params: dict) -> dict:
    rows = []
    for ri in db.execute(scoped(RoadmapItem, p.workspace_id).where(RoadmapItem.status != "dropped")
                         .order_by(RoadmapItem.target_quarter.nulls_last(), RoadmapItem.id)).scalars():
        n = sum(1 for _ in db.execute(scoped(FeatureRequest, p.workspace_id).where(FeatureRequest.roadmap_item_id == ri.id)).scalars())
        rows.append([ri.target_quarter or "—", ri.title, ri.status, n])
    return table("Roadmap", "", ["Quarter", "Item", "Status", "Linked requests"], rows)


def brief(db: Session, ws_id: int) -> list[str]:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    new = db.execute(scoped(FeatureRequest, ws_id).where(FeatureRequest.created_at >= since)).scalars().all()
    return [f"{len(new)} new feature request(s) this week"] if new else []


def _signal_aggregator(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    s = signals(ctx.db, ctx.principal.workspace_id)
    if not s:
        return "No open feature requests.", []
    return "\n".join(f"{i}. {x['title']} — {x['clients']} client(s), {x['requests']} request(s), open deals {x['open_deal_value']}"
                     for i, x in enumerate(s[:15], 1)), []


def register() -> None:
    register_permissions({"product.read": {F, S, C, A}, "product.write": {F, S}})
    perms = dict(read_perm="product.read", write_perm="product.write", delete_perm="product.write", department=DEPT)
    rr = records.register_record_type
    rr("roadmap_item", records.RecordType(RoadmapItem, RoadmapItemIn, patch_of(RoadmapItemIn), out_of(RoadmapItem),
                                          ("title", "description"), label="Roadmap", prepare=_roadmap_hook, **perms))
    rr("feature_request", records.RecordType(FeatureRequest, FeatureRequestIn, patch_of(FeatureRequestIn), out_of(FeatureRequest),
                                             ("title", "description"), label="Feature requests",
                                             refs={"organization_id": "organization", "roadmap_item_id": "roadmap_item"}, **perms))
    rr("release_note", records.RecordType(ReleaseNote, ReleaseNoteIn, patch_of(ReleaseNoteIn), out_of(ReleaseNote),
                                          ("title", "body"), label="Release notes", refs={"roadmap_item_id": "roadmap_item"}, **perms))
    register_report(Report("product.signals", DEPT, "Product signals", signals_report, "product.read"))
    register_report(Report("product.roadmap", DEPT, "Roadmap", roadmap_report, "product.read"))
    register_brief_section(DEPT, "Product", brief)
    register_agent(AgentSpec(name="signal_aggregator", description="Ranks roadmap candidates by clients and open deal value.",
                             handler=_signal_aggregator, permission="product.read", input_hint="(no input needed)"))
    register_department(Department(DEPT, "Product", 8, "Feature requests, roadmap and releases.", "product.read",
                                   ("feature_request", "roadmap_item", "release_note"), ("signal_aggregator",),
                                   "directives/108_product.md"))
