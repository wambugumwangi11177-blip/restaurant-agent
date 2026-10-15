"""GET /api/v1/owner/* — the owner API (docs/v2/SPEC.md §2, §3).

S1.1 adds the settings endpoints; S1.4 adds home / area / report / ask beside them. Owner-only: the owner
(staff_role OWNER) and ADMIN/SUPERADMIN pass `require_staff_role`; every other staff role gets a 403. The
restaurant is always resolved from the caller's own tenant (routers/deps.py) — there is no restaurant_id
parameter anywhere in this API, so there is no id to forge.

Observer-mode deployments (read-only Macsoft) block this whole prefix, like /overview, /reports and /ai
(observer_mode.py): these endpoints compose figures from local tables.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ConfigDict, Field, StrictFloat, StrictInt, create_model
from sqlalchemy.orm import Session

import models
from auth import require_staff_role
from database import get_db
from owner import settings as owner_settings
from routers.deps import get_restaurant_or_none

router = APIRouter(prefix="/owner", tags=["owner"])

_owner_only = require_staff_role(models.StaffRole.OWNER)


def _restaurant(db: Session, user: models.User) -> models.Restaurant:
    restaurant = get_restaurant_or_none(db, user)
    if restaurant is None:
        raise HTTPException(404, "Restaurant not found")
    return restaurant


# The PATCH body is generated from the same FieldSpec list the service validates against, so the allowed
# range exists once (owner/settings.py) and FastAPI reports an out-of-range value as a 422 on that field.
SettingsPatch = create_model(
    "SettingsPatch",
    __config__=ConfigDict(extra="forbid"),
    **{
        spec.key: (
            Optional[StrictInt if spec.kind == "int" else StrictFloat],
            Field(None, ge=spec.minimum, le=spec.maximum, description=spec.question),
        )
        for spec in owner_settings.FIELDS
    },
)


@router.get("/settings")
def read_settings(db: Session = Depends(get_db), user: models.User = Depends(_owner_only)):
    """Every setting with its value, default, allowed range and the question in owner words."""
    restaurant = _restaurant(db, user)
    return owner_settings.describe(db, restaurant.id)


@router.put("/settings")
def write_settings(body: SettingsPatch, db: Session = Depends(get_db), user: models.User = Depends(_owner_only)):
    """Change one or more settings (send only the ones that change). Out-of-range → 422; each change is audited."""
    restaurant = _restaurant(db, user)
    changes = body.model_dump(exclude_none=True)
    try:
        owner_settings.update_settings(db, restaurant.id, user.id, changes)
    except owner_settings.SettingsError as exc:
        raise HTTPException(422, detail={"field": exc.field, "message": str(exc)}) from exc
    return owner_settings.describe(db, restaurant.id)


@router.get("/settings/history")
def settings_history(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
                     user: models.User = Depends(_owner_only)):
    restaurant = _restaurant(db, user)
    return {"history": owner_settings.history(db, restaurant.id, limit)}
