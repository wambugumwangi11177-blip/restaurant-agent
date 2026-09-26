"""
app/kernel/models.py
────────────────────
Every Kernel table. Rules that hold for all of them:

- Every business row carries `workspace_id` (multi-tenant from day one; your
  company is workspace #1). Queries go through app.kernel.tenancy, never raw.
- Timestamps are timezone-aware UTC. Display converts to the workspace's zone.
- Money, when departments add it, is integer minor units + ISO currency code.
- `audit_log` is append-only: a DB trigger (migration 0001) rejects UPDATE and
  DELETE, so not even a bug in this codebase can rewrite history.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _ts(nullable: bool = False, default_now: bool = True):
    return mapped_column(
        DateTime(timezone=True),
        nullable=nullable,
        server_default=func.now() if default_now else None,
    )


def _ws():
    return mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False)


class Role(str, enum.Enum):
    FOUNDER = "founder"
    STAFF = "staff"
    CONTRACTOR = "contractor"
    ADVISOR = "advisor"


# ── Identity & tenancy ───────────────────────────────────────────────────────

class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Africa/Nairobi")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="KES")
    # Productization (directive 000, phase 10). "internal" = the founder's own company.
    plan: Mapped[str] = mapped_column(String(20), nullable=False, server_default="internal")
    seat_limit: Mapped[int | None] = mapped_column(Integer)
    monthly_agent_run_limit: Mapped[int | None] = mapped_column(Integer)
    # None = every department enabled; otherwise the list of department keys enabled.
    enabled_departments: Mapped[list | None] = mapped_column(JSONB)
    # Workspace-level settings departments read (e.g. finance opening balance, iCal URL).
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = _ts()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Digits only, E.164 without '+', e.g. 254712345678. Used to recognise the
    # sender of inbound WhatsApp commands.
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = _ts(nullable=True, default_now=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = _ts()


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = _ts()


# ── Core records ─────────────────────────────────────────────────────────────

class Person(Base):
    __tablename__ = "people"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    erased_at: Mapped[datetime | None] = _ts(nullable=True, default_now=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500))
    industry: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default="normal")
    due_date: Mapped[date | None] = mapped_column(Date)
    assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = _ts(nullable=True, default_now=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    context: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="accepted")
    revisit_on: Mapped[date | None] = mapped_column(Date)
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Link(Base):
    """Polymorphic edge between any two records in the same workspace."""
    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint("workspace_id", "from_type", "from_id", "to_type", "to_id", "relation"),
        Index("ix_links_to", "workspace_id", "to_type", "to_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    from_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_id: Mapped[int] = mapped_column(Integer, nullable=False)
    to_type: Mapped[str] = mapped_column(String(40), nullable=False)
    to_id: Mapped[int] = mapped_column(Integer, nullable=False)
    relation: Mapped[str] = mapped_column(String(40), nullable=False, server_default="related")
    created_at: Mapped[datetime] = _ts()


# ── Company memory ───────────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("workspace_id", "content_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str | None] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _ts()


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    # Heading words weigh more than body words when ranking.
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(heading, '')), 'A') || "
            "setweight(to_tsvector('english', content), 'B')",
            persisted=True,
        ),
    )


# ── Events & audit ───────────────────────────────────────────────────────────

class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_ws_created", "workspace_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = _ts()


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_ws_created", "workspace_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: a failed login for an unknown email has no workspace.
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="SET NULL"))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _ts()


# ── Agent runtime & approvals ────────────────────────────────────────────────

class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_ws_created", "workspace_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="running")
    input: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    output: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, server_default="0")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default="api")
    triggered_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _ts()
    finished_at: Mapped[datetime | None] = _ts(nullable=True, default_now=False)


class Proposal(Base):
    """An outward-facing action an agent (or person) wants taken. Nothing with an
    EXTERNAL effect executes without an approved proposal — enforced in
    app.kernel.agents.tools.execute_tool, not by prompts."""
    __tablename__ = "proposals"
    __table_args__ = (Index("ix_proposals_ws_status", "workspace_id", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"))
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    args: Mapped[dict] = mapped_column(JSONB, nullable=False)
    final_args: Mapped[dict | None] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = _ts(nullable=True, default_now=False)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    auto_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    executed_at: Mapped[datetime | None] = _ts(nullable=True, default_now=False)
    created_at: Mapped[datetime] = _ts()


class ToolCall(Base):
    __tablename__ = "tool_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    effect: Mapped[str] = mapped_column(String(20), nullable=False)
    args: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    result: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("proposals.id", ondelete="SET NULL"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _ts()


class ToolPolicy(Base):
    """Per-workspace autonomy setting for one EXTERNAL tool. Auto-approval is off
    by default and only ever activates when the founder enables it AND the
    tool's streak of un-edited approvals has reached `streak_threshold`."""
    __tablename__ = "tool_policies"
    __table_args__ = (UniqueConstraint("workspace_id", "tool_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    auto_approve_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    streak_threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default="20")
    updated_at: Mapped[datetime] = _ts()


class Feedback(Base):
    """Every human verdict on an agent output. This table is the raw material of
    'learning': corrections here become eval cases (execution/export_feedback_evals.py)."""
    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_target", "workspace_id", "target_type", "target_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # proposal | agent_run
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    correction: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _ts()


# ── Channels & notifications ─────────────────────────────────────────────────

class ChannelMessage(Base):
    __tablename__ = "channel_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # whatsapp | email
    direction: Mapped[str] = mapped_column(String(3), nullable=False)  # in | out
    # Provider message id (Twilio MessageSid). Unique => a retried webhook is a no-op.
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    from_addr: Mapped[str] = mapped_column(String(320), nullable=False)
    to_addr: Mapped[str] = mapped_column(String(320), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _ts()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    link: Mapped[str | None] = mapped_column(String(500))
    read_at: Mapped[datetime | None] = _ts(nullable=True, default_now=False)
    created_at: Mapped[datetime] = _ts()
