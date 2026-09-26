"""
app/api/platform.py
───────────────────
Phase 10 — productizing the OS for other businesses.

- Platform admins (PLATFORM_ADMIN_EMAILS, and MFA must be on) create workspaces and
  set each workspace's plan, seat limit, monthly agent-run limit and enabled
  departments. A workspace's own founder can see usage but cannot raise limits.
- Self-serve signup exists but is OFF unless ALLOW_SIGNUP=true; signups get the
  "trial" plan with SIGNUP_* limits.
- Billing is NOT implemented: charging needs a payment-provider and pricing
  decision by the founder (directive 110). Limits are enforced regardless.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_principal, require
from app.config import get_settings
from app.db import get_db
from app.kernel.agents import spend
from app.kernel.audit import write_audit
from app.kernel.bootstrap import BootstrapError, create_workspace_with_founder
from app.kernel.departments import DEPARTMENTS
from app.kernel.models import AgentRun, Workspace
from app.kernel.tenancy import Principal
from app.kernel.workspaces import agent_runs_this_month, month_start, seats_used
from app.security import WeakPasswordError

router = APIRouter()
public_router = APIRouter()


def require_platform_admin(principal: Principal = Depends(get_principal)) -> Principal:
    user = principal.user
    if user is None or user.email.lower() not in get_settings().platform_admin_emails:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admin only")
    if not user.mfa_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform admins must enable two-factor authentication first")
    return principal


def _usage(db: Session, ws: Workspace) -> dict:
    spent = db.execute(select(func.coalesce(func.sum(AgentRun.cost_usd), 0)).where(
        AgentRun.workspace_id == ws.id, AgentRun.created_at >= month_start())).scalar_one()
    return {
        "id": ws.id, "slug": ws.slug, "name": ws.name, "plan": ws.plan,
        "seats_used": seats_used(db, ws.id), "seat_limit": ws.seat_limit,
        "agent_runs_this_month": agent_runs_this_month(db, ws.id), "monthly_agent_run_limit": ws.monthly_agent_run_limit,
        "llm_spend_this_month_usd": str(spent), "llm_spend_today_usd": str(spend.today_spend_usd(db, ws.id)),
        "enabled_departments": ws.enabled_departments,
    }


def _check_departments(keys: list[str] | None) -> None:
    if keys is None:
        return
    unknown = sorted(set(keys) - set(DEPARTMENTS))
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown departments: {unknown}")


@router.get("/workspace/usage")
def workspace_usage(principal: Principal = Depends(require("ops.read")), db: Session = Depends(get_db)) -> dict:
    return _usage(db, db.get(Workspace, principal.workspace_id))


@router.get("/platform/workspaces")
def list_workspaces(principal: Principal = Depends(require_platform_admin), db: Session = Depends(get_db)) -> list[dict]:
    return [_usage(db, ws) for ws in db.execute(select(Workspace).order_by(Workspace.id)).scalars()]


class NewWorkspaceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str
    name: str = Field(min_length=1, max_length=200)
    founder_email: EmailStr
    founder_name: str = Field(min_length=1, max_length=200)
    founder_password: str = Field(max_length=256)
    plan: str = Field(default="standard", pattern=r"^[a-z0-9_-]{1,20}$")
    seat_limit: int | None = Field(default=None, ge=1)
    monthly_agent_run_limit: int | None = Field(default=None, ge=0)
    enabled_departments: list[str] | None = None
    currency: str = Field(default="KES", pattern=r"^[A-Z]{3}$")
    timezone: str = "Africa/Nairobi"


def _create(db: Session, body: NewWorkspaceIn, actor_user_id: int | None, action: str,
            allow_existing_user: bool = True) -> Workspace:
    _check_departments(body.enabled_departments)
    try:
        ws, user = create_workspace_with_founder(db, slug=body.slug, name=body.name, email=body.founder_email,
                                                 full_name=body.founder_name, password=body.founder_password,
                                                 timezone=body.timezone, currency=body.currency,
                                                 allow_existing_user=allow_existing_user)
    except (BootstrapError, WeakPasswordError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    ws.plan, ws.seat_limit, ws.monthly_agent_run_limit = body.plan, body.seat_limit, body.monthly_agent_run_limit
    ws.enabled_departments = body.enabled_departments
    write_audit(db, action=action, workspace_id=ws.id, entity_type="workspace", entity_id=ws.id,
                changes={"plan": ws.plan, "seat_limit": ws.seat_limit, "monthly_agent_run_limit": ws.monthly_agent_run_limit,
                         "enabled_departments": ws.enabled_departments}, actor_user_id=actor_user_id)
    return ws


@router.post("/platform/workspaces", status_code=201)
def create_workspace(body: NewWorkspaceIn, principal: Principal = Depends(require_platform_admin),
                     db: Session = Depends(get_db)) -> dict:
    ws = _create(db, body, principal.user_id, "platform.workspace_create")
    db.commit()
    return _usage(db, ws)


class PlanPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,20}$")
    seat_limit: int | None = Field(default=None, ge=1)
    monthly_agent_run_limit: int | None = Field(default=None, ge=0)
    enabled_departments: list[str] | None = None


@router.patch("/platform/workspaces/{workspace_id}")
def update_plan(workspace_id: int, body: PlanPatch, principal: Principal = Depends(require_platform_admin),
                db: Session = Depends(get_db)) -> dict:
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    changes = body.model_dump(exclude_unset=True)
    _check_departments(changes.get("enabled_departments"))
    before = {k: getattr(ws, k) for k in changes}
    for k, v in changes.items():
        setattr(ws, k, v)
    write_audit(db, action="platform.plan_change", workspace_id=ws.id, entity_type="workspace", entity_id=ws.id,
                changes={"from": before, "to": changes}, actor_user_id=principal.user_id)
    db.commit()
    return _usage(db, ws)


# ── Self-serve signup (off by default) ───────────────────────────────────────

_signup_hits: dict[str, deque] = defaultdict(deque)
SIGNUPS_PER_IP_PER_HOUR = 5


class SignupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(max_length=256)


@public_router.post("/api/v1/signup", status_code=201)
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    if not s.allow_signup:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    ip = request.client.host if request.client else "unknown"
    hits = _signup_hits[ip]
    now = time.monotonic()
    while hits and now - hits[0] > 3600:
        hits.popleft()
    if len(hits) >= SIGNUPS_PER_IP_PER_HOUR:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many signups from this address; try later")
    hits.append(now)
    ws = _create(db, NewWorkspaceIn(slug=body.slug, name=body.name, founder_email=body.email, founder_name=body.full_name,
                                    founder_password=body.password, plan="trial", seat_limit=s.signup_seat_limit,
                                    monthly_agent_run_limit=s.signup_monthly_agent_run_limit,
                                    enabled_departments=s.signup_departments or None), None, "signup",
                 allow_existing_user=False)
    db.commit()
    return {"workspace": ws.slug, "plan": ws.plan, "next": "Sign in with the email and password you chose."}
