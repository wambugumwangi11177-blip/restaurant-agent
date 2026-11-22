"""Server-side restaurant context — per-tenant data wall (no in-app multi-client UI)."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models


def get_restaurant_or_none(db: Session, user: models.User) -> models.Restaurant | None:
    """Read-only restaurant for the signed-in user's tenant only."""
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
    restaurant = models.Restaurant(
        name=f"{user.tenant.name}'s Restaurant",
        tenant_id=user.tenant_id,
    )
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    return restaurant


def assert_row_in_restaurant(restaurant_id: int, user: models.User, db: Session) -> None:
    row = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if row is None or row.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Restaurant not found")


def get_restaurant_by_id(db: Session, restaurant_id: int) -> models.Restaurant:
    row = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return row