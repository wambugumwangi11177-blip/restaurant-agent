"""Server-side restaurant context — data wall for Eleven / Test Restaurant / super-admin."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models


def restaurant_for_superadmin(db: Session, user: models.User) -> models.Restaurant | None:
    if user.role != models.Role.SUPERADMIN:
        return None
    if user.active_restaurant_id is None:
        return None
    return db.query(models.Restaurant).filter(models.Restaurant.id == user.active_restaurant_id).first()


def get_restaurant_or_none(db: Session, user: models.User) -> models.Restaurant | None:
    """Read-only restaurant for the authenticated user (never auto-creates)."""
    if user.role == models.Role.SUPERADMIN:
        return restaurant_for_superadmin(db, user)

    if user.active_restaurant_id is not None:
        selected = (
            db.query(models.Restaurant)
            .filter(
                models.Restaurant.id == user.active_restaurant_id,
                models.Restaurant.tenant_id == user.tenant_id,
            )
            .first()
        )
        if selected:
            return selected
    return (
        db.query(models.Restaurant)
        .filter(models.Restaurant.tenant_id == user.tenant_id)
        .order_by(models.Restaurant.id)
        .first()
    )


def get_or_create_restaurant(db: Session, user: models.User) -> models.Restaurant:
    restaurant = get_restaurant_or_none(db, user)
    if restaurant:
        return restaurant
    if user.role == models.Role.SUPERADMIN:
        raise HTTPException(
            status_code=409,
            detail="Open a client first from the super-admin screen.",
        )
    restaurant = models.Restaurant(
        name=f"{user.tenant.name}'s Restaurant",
        tenant_id=user.tenant_id,
    )
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    return restaurant


def assert_row_in_restaurant(restaurant_id: int, user: models.User, db: Session) -> None:
    """Reject cross-tenant or cross-client access for non-super-admins."""
    if user.role == models.Role.SUPERADMIN:
        active = restaurant_for_superadmin(db, user)
        if active is None or active.id != restaurant_id:
            raise HTTPException(status_code=403, detail="Outside the opened client.")
        return
    row = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Restaurant not found")


def require_owner_tenant(user: models.User) -> None:
    if user.role in (models.Role.SUPERADMIN,):
        return
    tenant = (user.tenant.name or "").strip().lower()
    if user.role == models.Role.ADMIN and user.staff_role == models.StaffRole.OWNER:
        return
    raise HTTPException(status_code=403, detail="Owner access only.")