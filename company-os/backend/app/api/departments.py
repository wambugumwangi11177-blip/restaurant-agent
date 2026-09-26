"""
app/api/departments.py
──────────────────────
Discovery and execution for department capabilities: which departments this
caller can see, their reports (read-only), their scheduled jobs (founder can
trigger manually; cron runs them via execution/run_jobs.py), and workspace
settings.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_principal, require
from app.db import get_db
from app.kernel.agents.registry import AGENTS
from app.kernel.audit import write_audit
from app.kernel.departments import DEPARTMENTS, JOBS, REPORTS, SETTINGS
from app.kernel.rbac import role_has
from app.kernel.records import RECORD_TYPES
from app.kernel.tenancy import Principal
from app.kernel.workspaces import department_enabled, get_workspace

router = APIRouter()


@router.get("/departments")
def list_departments(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)) -> list[dict]:
    out = []
    for d in sorted(DEPARTMENTS.values(), key=lambda d: d.order):
        if not department_enabled(db, principal.workspace_id, d.key) or not role_has(principal.role, d.permission):
            continue
        out.append({
            "key": d.key, "label": d.label, "description": d.description, "directive": d.directive,
            "record_types": [t for t in d.record_types if role_has(principal.role, RECORD_TYPES[t].read_perm)],
            "reports": [{"key": r.key, "label": r.label, "description": r.description, "params": list(r.params)}
                        for r in REPORTS.values() if r.department == d.key and role_has(principal.role, r.permission)],
            "agents": [a for a in d.agents if a in AGENTS and role_has(principal.role, AGENTS[a].permission)],
            "jobs": [{"name": j.name, "schedule": j.schedule_hint} for j in JOBS.values() if j.department == d.key],
        })
    return out


@router.get("/reports/{key}")
def run_report(key: str, request: Request, principal: Principal = Depends(get_principal),
               db: Session = Depends(get_db)) -> dict:
    r = REPORTS.get(key)
    if r is None or not department_enabled(db, principal.workspace_id, r.department):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No report {key!r}")
    if not role_has(principal.role, r.permission):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role lacks '{r.permission}'")
    params = {p: request.query_params.get(p) for p in r.params if request.query_params.get(p) is not None}
    return r.fn(db, principal, params)


@router.post("/jobs/{name}/run")
def run_job(name: str, principal: Principal = Depends(require("jobs.run")), db: Session = Depends(get_db)) -> dict:
    j = JOBS.get(name)
    if j is None or not department_enabled(db, principal.workspace_id, j.department):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job {name!r}")
    summary = j.fn(db, principal.workspace_id)
    write_audit(db, action="job.run", workspace_id=principal.workspace_id, entity_type="job",
                changes={"job": name, "summary": summary[:500], "manual": True}, actor_user_id=principal.user_id)
    db.commit()
    return {"job": name, "summary": summary}


@router.get("/workspace/settings")
def get_settings_(principal: Principal = Depends(require("workspace.settings")), db: Session = Depends(get_db)) -> list[dict]:
    values = get_workspace(db, principal.workspace_id).settings or {}
    return [{"key": s.key, "department": s.department, "description": s.description, "secret": s.secret,
             "kind": s.kind, "is_set": s.key in values,
             "value": ("••••••" if s.secret and s.key in values else values.get(s.key))}
            for s in SETTINGS.values()]


@router.put("/workspace/settings")
def put_settings(body: dict = Body(...), principal: Principal = Depends(require("workspace.settings")),
                 db: Session = Depends(get_db)) -> dict:
    unknown = sorted(set(body) - set(SETTINGS))
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown settings: {unknown}")
    ws = get_workspace(db, principal.workspace_id)
    new = dict(ws.settings or {})
    for k, v in body.items():
        spec = SETTINGS[k]
        if v is None or v == "":
            new.pop(k, None)
            continue
        if spec.kind == "integer":
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{k} must be an integer") from None
        elif not isinstance(v, str) or len(v) > 2000:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{k} must be a string up to 2000 characters")
        new[k] = v
    ws.settings = new
    # Keys only — values may be secrets (e.g. a private calendar URL).
    write_audit(db, action="workspace.settings", workspace_id=ws.id, entity_type="workspace", entity_id=ws.id,
                changes={"keys": sorted(body)}, actor_user_id=principal.user_id)
    db.commit()
    return {"updated": sorted(body)}
