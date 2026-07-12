"""
backend/routers/flags.py
─────────────────────────
Read-only feature-flag state, so the frontend can gate UI on the same flags the
backend enforces (single source of truth = feature_flags.py). Flags are global
rollout/kill switches, not per-tenant, so this is tenant-agnostic.
"""

from fastapi import APIRouter, Depends

from auth import get_current_user, require_role
import models
import feature_flags

router = APIRouter(prefix="/flags", tags=["flags"])


@router.get("/")
async def get_flags(current_user: models.User = Depends(get_current_user)):
    """Current on/off state of every feature flag — for UI gating. Any signed-in
    user (the flags themselves carry no sensitive data)."""
    return {"flags": feature_flags.all_flags()}


@router.get("/details")
async def get_flag_details(
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
):
    """Flags with descriptions — an admin/ops view of what each switch does."""
    return {"flags": feature_flags.flag_details()}
