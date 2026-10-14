"""Company OS Kernel API. SUPERADMIN only (the platform operator)."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from ai.company_os import kernel
from ai.company_os import agents

router = APIRouter(prefix="/company-os", tags=["company-os"])
_op = Depends(auth.require_role())  # SUPERADMIN always passes; nobody else listed


class Decision(BaseModel):
    edited_payload: dict | None = None


def _out(p: models.CompanyProposal) -> dict:
    return {"id": p.id, "department": p.agent.split(".")[0], "agent": p.agent, "tool": p.tool, "tier": p.tier, "summary": p.summary,
            "payload": json.loads(p.payload or "{}"), "restaurant_id": p.restaurant_id,
            "status": p.status, "auto_executed": p.auto_executed, "edited": p.edited,
            "result": p.result, "error": p.error, "created_at": p.created_at, "decided_at": p.decided_at}


@router.get("/status")
async def get_status(db: Session = Depends(get_db), _u: models.User = _op):
    return kernel.status(db)


@router.get("/proposals")
async def list_proposals(status: str | None = None, limit: int = 100,
                         db: Session = Depends(get_db), _u: models.User = _op):
    q = db.query(models.CompanyProposal)
    if status:
        q = q.filter(models.CompanyProposal.status == status)
    return [_out(p) for p in q.order_by(models.CompanyProposal.id.desc()).limit(min(limit, 500)).all()]


def _decide(db, pid, approve, user, body):
    try:
        return _out(kernel.decide(db, pid, approve, user, body.edited_payload if body else None))
    except LookupError:
        raise HTTPException(404, "Proposal not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/proposals/{pid}/approve")
async def approve(pid: int, body: Decision | None = None, db: Session = Depends(get_db),
                  user: models.User = _op):
    return _decide(db, pid, True, user, body)


@router.post("/proposals/{pid}/reject")
async def reject(pid: int, db: Session = Depends(get_db), user: models.User = _op):
    return _decide(db, pid, False, user, None)


@router.post("/tools/{name}/revoke-autonomy")
async def revoke(name: str, db: Session = Depends(get_db), _u: models.User = _op):
    try:
        kernel.get_tool(name)
    except KeyError:
        raise HTTPException(404, "Unknown tool")
    kernel.revoke_autonomy(db, name)
    return kernel.status(db)


@router.get("/departments")
async def departments(db: Session = Depends(get_db), _u: models.User = _op):
    from ai.company_os.departments import DEPARTMENTS
    from ai.company_os.departments.executive import founder_load
    return {"departments": [d.NAME for d in DEPARTMENTS], "founder_load": founder_load(db)}


@router.post("/run")
async def run_now(db: Session = Depends(get_db), _u: models.User = _op):
    return agents.run_company_cycle(db)
