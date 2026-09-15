"""Honest source state while the vendor adapter is awaiting discovery."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
import models
from auth import get_current_user
from reporting import period_for
from integration.source_contract import SourceRegistry

router = APIRouter(prefix="/observer", tags=["observer"])
source_registry = SourceRegistry()


@router.get("/source-status")
async def source_status(current_user: models.User = Depends(get_current_user)):
    health = await source_registry.resolve(current_user.active_restaurant_id).health(current_user.active_restaurant_id or 0)
    return {
        "source": health.source, "state": health.state, "as_of": health.as_of,
        "checked_at": health.checked_at, "capabilities": health.capabilities,
        "reason": health.reason,
    }


@router.get("/reports/{kind}")
async def report_preview(kind: str, anchor: date | None = None, current_user: models.User = Depends(get_current_user)):
    try:
        period = period_for(kind, anchor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    health = await source_registry.resolve(current_user.active_restaurant_id).health(current_user.active_restaurant_id or 0)
    return {
        "status": "unavailable" if health.state == "unavailable" else "partial",
        "period": {"kind": period.kind, "start": period.start, "end": period.end, "timezone": period.timezone},
        "source": {"name": health.source, "state": health.state, "reason": health.reason},
        "metrics": [],
        "warnings": [health.reason] if health.reason else [],
    }
