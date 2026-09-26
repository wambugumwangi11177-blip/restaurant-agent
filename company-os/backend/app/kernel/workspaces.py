"""
app/kernel/workspaces.py
────────────────────────
Workspace-level switches the Kernel enforces: which departments are enabled,
seat and agent-run limits (used when the OS is sold to other businesses), and
free-form settings that departments read.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.kernel.models import AgentRun, Membership, Workspace


def get_workspace(db: Session, workspace_id: int) -> Workspace:
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return ws


def department_enabled(db: Session, workspace_id: int, department: str) -> bool:
    ws = db.get(Workspace, workspace_id)
    return ws is not None and (ws.enabled_departments is None or department in ws.enabled_departments)


def require_department(db: Session, workspace_id: int, department: str) -> None:
    if not department_enabled(db, workspace_id, department):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Department {department!r} is not enabled for this workspace")


def setting(db: Session, workspace_id: int, key: str, default=None):
    return (get_workspace(db, workspace_id).settings or {}).get(key, default)


def seats_used(db: Session, workspace_id: int) -> int:
    return int(db.execute(select(func.count()).select_from(Membership).where(
        Membership.workspace_id == workspace_id)).scalar_one())


def check_seat_available(db: Session, workspace_id: int) -> None:
    ws = get_workspace(db, workspace_id)
    if ws.seat_limit is not None and seats_used(db, workspace_id) >= ws.seat_limit:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, f"Seat limit reached ({ws.seat_limit}) for plan {ws.plan!r}")


def month_start() -> datetime:
    return datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def agent_runs_this_month(db: Session, workspace_id: int) -> int:
    return int(db.execute(select(func.count()).select_from(AgentRun).where(
        AgentRun.workspace_id == workspace_id, AgentRun.created_at >= month_start())).scalar_one())


def check_agent_run_allowed(db: Session, workspace_id: int) -> None:
    ws = get_workspace(db, workspace_id)
    if ws.monthly_agent_run_limit is not None and agent_runs_this_month(db, workspace_id) >= ws.monthly_agent_run_limit:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            f"Monthly agent-run limit reached ({ws.monthly_agent_run_limit}) for plan {ws.plan!r}")
