"""
app/kernel/tenancy.py
─────────────────────
The only sanctioned way to read or write workspace data. Every helper takes a
Principal and filters by its workspace_id, so a route cannot forget the tenant
filter: a record from another workspace is indistinguishable from a missing one
(404, never 403 — no existence oracle across tenants).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.kernel.models import User

T = TypeVar("T")


@dataclass(frozen=True)
class Principal:
    user_id: int
    workspace_id: int
    role: str
    user: User | None = None


def scoped(model: type[T], workspace_id: int) -> Select:
    return select(model).where(model.workspace_id == workspace_id)  # type: ignore[attr-defined]


def get_scoped(db: Session, model: type[T], record_id: int, workspace_id: int) -> T | None:
    return db.execute(
        scoped(model, workspace_id).where(model.id == record_id)  # type: ignore[attr-defined]
    ).scalar_one_or_none()


def get_or_404(db: Session, model: type[T], record_id: int, workspace_id: int) -> T:
    obj = get_scoped(db, model, record_id, workspace_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {record_id} not found")
    return obj
