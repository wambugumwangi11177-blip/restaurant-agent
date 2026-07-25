"""
backend/routers/restaurants.py
─────────────────────────────────
Multi-restaurant switcher (audit remediation, Tier 5 item 11 / tech-debt D4).

Every router resolves "the" restaurant for a tenant via
routers/deps.py::get_or_create_restaurant, which always returned the tenant's
first restaurant — correct for the overwhelming single-restaurant case, a
real gap for a chain (Organization/Region already existed from Phase 10, just
never wired into restaurant selection). This router is the two endpoints that
close it: list what's available, and let an Owner pick one. Every other
router is unchanged — they all still call the same deps.py functions, which
now consult User.active_restaurant_id internally.

Scoped deliberately narrow: this is an Owner-level "which location am I
looking at" toggle, not a per-staff-member restaurant assignment system (a
distinct, larger feature — today every staff account at a tenant can see
whichever restaurant the tenant's Owner has selected, same as every other
tenant-scoped resource in this app).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from auth import require_role
import models
import schemas
from routers.deps import get_restaurant_or_none, list_restaurants_for_tenant

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("/", response_model=List[schemas.RestaurantOut])
async def list_restaurants(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
):
    """
    Every restaurant belonging to the current user's tenant, with `is_active`
    marking whichever one requests are currently scoped to (what
    get_or_create_restaurant would resolve to right now). Frontend only shows
    a switcher when this list has more than one entry.
    """
    restaurants = list_restaurants_for_tenant(db, current_user)
    active = get_restaurant_or_none(db, current_user)
    active_id = active.id if active else None
    return [
        {"id": r.id, "name": r.name, "address": r.address, "is_active": r.id == active_id}
        for r in restaurants
    ]


@router.post("/select", response_model=schemas.RestaurantOut)
async def select_restaurant(
    body: schemas.RestaurantSelectBody,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
):
    """
    Switch which restaurant this user's requests resolve to. Validates the
    target belongs to the caller's own tenant — the same tenant_id filter
    every other endpoint in this app enforces, so this can't be used to hop
    into another tenant's data.
    """
    target = db.query(models.Restaurant).filter(
        models.Restaurant.id == body.restaurant_id,
        models.Restaurant.tenant_id == current_user.tenant_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    # Re-query rather than mutate current_user directly and commit — the
    # established pattern in routers/auth.py (see e.g. its MFA/password
    # routes) for a self-mutation, since current_user was loaded by a
    # dependency the ORM doesn't guarantee shares this exact session.
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    user.active_restaurant_id = target.id
    db.commit()
    return {"id": target.id, "name": target.name, "address": target.address, "is_active": True}
