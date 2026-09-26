"""
app/kernel/schemas.py
─────────────────────
Request/response models for Kernel records. Input models reject unknown fields
(extra="forbid") so a client typo fails loudly instead of being silently dropped.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def normalize_phone(raw: str | None) -> str | None:
    """Digits-only E.164 without '+'. Kenyan local 07…/01… becomes 2547…/2541….
    Ported from restaurant-agent/backend/phone_utils.py (same reasoning: Twilio
    delivers E.164, people type local format)."""
    if raw is None:
        return None
    raw = raw.strip()
    if raw.lower().startswith("whatsapp:"):
        raw = raw[len("whatsapp:"):]
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if len(digits) == 10 and digits.startswith("0"):
        digits = "254" + digits[1:]
    if not 8 <= len(digits) <= 15:
        raise ValueError("phone number must have 8-15 digits in international format")
    return digits


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Person ───────────────────────────────────────────────────────────────────

class PersonIn(In):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = None

    @field_validator("phone")
    @classmethod
    def norm_phone(cls, v: str | None) -> str | None:
        return normalize_phone(v)


class PersonPatch(In):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = None

    @field_validator("phone")
    @classmethod
    def norm_phone(cls, v: str | None) -> str | None:
        return normalize_phone(v)


class PersonOut(Out):
    id: int
    full_name: str
    email: str | None
    phone: str | None
    title: str | None
    notes: str | None
    erased_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ── Organization ─────────────────────────────────────────────────────────────

class OrganizationIn(In):
    name: str = Field(min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class OrganizationPatch(In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class OrganizationOut(Out):
    id: int
    name: str
    website: str | None
    industry: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ── Task ─────────────────────────────────────────────────────────────────────

TaskStatus = Literal["open", "in_progress", "done", "cancelled"]
Priority = Literal["low", "normal", "high", "urgent"]


class TaskIn(In):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    status: TaskStatus = "open"
    priority: Priority = "normal"
    due_date: date | None = None
    assignee_user_id: int | None = None


class TaskPatch(In):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    due_date: date | None = None
    assignee_user_id: int | None = None


class TaskOut(Out):
    id: int
    title: str
    description: str | None
    status: str
    priority: str
    due_date: date | None
    assignee_user_id: int | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ── Decision ─────────────────────────────────────────────────────────────────

DecisionStatus = Literal["proposed", "accepted", "superseded"]


class DecisionIn(In):
    title: str = Field(min_length=1, max_length=300)
    decision: str = Field(min_length=1)
    context: str | None = None
    alternatives: str | None = None
    rationale: str | None = None
    status: DecisionStatus = "accepted"
    revisit_on: date | None = None


class DecisionPatch(In):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    decision: str | None = Field(default=None, min_length=1)
    context: str | None = None
    alternatives: str | None = None
    rationale: str | None = None
    status: DecisionStatus | None = None
    revisit_on: date | None = None


class DecisionOut(Out):
    id: int
    title: str
    decision: str
    context: str | None
    alternatives: str | None
    rationale: str | None
    status: str
    revisit_on: date | None
    decided_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


# ── Note ─────────────────────────────────────────────────────────────────────

class NoteIn(In):
    title: str = Field(min_length=1, max_length=300)
    body: str = ""


class NotePatch(In):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = None


class NoteOut(Out):
    id: int
    title: str
    body: str
    created_at: datetime
    updated_at: datetime


# ── Links ────────────────────────────────────────────────────────────────────

# Any registered record type or "document"; validated against the registry in records.create_link.
LinkableType = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[a-z_]+$")]


class LinkIn(In):
    from_type: LinkableType
    from_id: int
    to_type: LinkableType
    to_id: int
    relation: str = Field(default="related", min_length=1, max_length=40, pattern=r"^[a-z_]+$")


class LinkOut(Out):
    id: int
    from_type: str
    from_id: int
    to_type: str
    to_id: int
    relation: str
    created_at: datetime
