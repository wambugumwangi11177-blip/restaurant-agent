"""
backend/routers/settings.py
───────────────────────────
Restaurant settings: hours, service periods, VAT %, service charge %,
tenders, stations, and printer routing.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=schemas.RestaurantSettingOut)
async def get_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    setting = db.query(models.RestaurantSetting).filter(
        models.RestaurantSetting.restaurant_id == restaurant.id
    ).first()

    if not setting:
        setting = models.RestaurantSetting(
            restaurant_id=restaurant.id,
            tax_rate_percent=16.0,
            service_charge_percent=0.0,
            receipt_header=restaurant.name or "",
            receipt_footer="Thank you for dining with us!",
            currency="KES",
            timezone="Africa/Nairobi",
            opening_time="07:00",
            closing_time="23:00",
            lunch_start="11:30",
            lunch_end="15:00",
            dinner_start="18:00",
            dinner_end="22:30",
            stations_json='["grill","fryer","salad","drinks","main","expo"]',
            tenders_json='["cash","mpesa","card"]',
            kitchen_printer_url="",
            receipt_printer_url="",
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)

    return setting


@router.put("/", response_model=schemas.RestaurantSettingOut)
async def update_settings(
    body: schemas.RestaurantSettingUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    setting = db.query(models.RestaurantSetting).filter(
        models.RestaurantSetting.restaurant_id == restaurant.id
    ).first()

    if not setting:
        setting = models.RestaurantSetting(restaurant_id=restaurant.id)
        db.add(setting)

    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(setting, field, value)

    db.commit()
    db.refresh(setting)
    return setting
