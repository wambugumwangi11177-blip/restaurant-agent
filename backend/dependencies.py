"""
Dependencies for the Restaurant Agent API.
Centralizes commonly used dependency functions to avoid duplication.
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import models
import auth


def get_restaurant(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """
    Get the restaurant for the current user's tenant.
    Creates one if it doesn't exist (for MVP onboarding).

    Args:
        db: Database session
        current_user: Current authenticated user

    Returns:
        models.Restaurant: The restaurant associated with the user's tenant
    """
    restaurant = db.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == current_user.tenant_id
    ).first()

    if not restaurant:
        # Auto-create restaurant for tenant if none exists (MVP behavior)
        restaurant = models.Restaurant(
            name=f"{current_user.tenant.name}'s Restaurant",
            tenant_id=current_user.tenant_id,
        )
        db.add(restaurant)
        db.commit()
        db.refresh(restaurant)

    return restaurant


def get_restaurant_id(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)) -> int:
    """
    Get the restaurant ID for the current user's tenant.

    Args:
        db: Database session
        current_user: Current authenticated user

    Returns:
        int: The restaurant ID, or 0 if no restaurant found
    """
    restaurant = db.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == current_user.tenant_id
    ).first()

    return restaurant.id if restaurant else 0


def get_restaurant_required(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)) -> models.Restaurant:
    """
    Get the restaurant for the current user's tenant.
    Raises 404 if no restaurant found.

    Args:
        db: Database session
        current_user: Current authenticated user

    Returns:
        models.Restaurant: The restaurant associated with the user's tenant

    Raises:
        HTTPException: If no restaurant is found for the user's tenant
    """
    restaurant = db.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == current_user.tenant_id
    ).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="No restaurant found for this account")
    return restaurant