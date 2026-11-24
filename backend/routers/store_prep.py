"""Prep suggestions for today's kitchen handover."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from routers.deps import get_or_create_restaurant
from services.prep_suggest import prep_for_today

router = APIRouter(prefix="/store/prep", tags=["store-prep"])

_FLOOR = (
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.CONTROLLER,
    models.StaffRole.MANAGER,
)


@router.get("/list")
async def dated_prep_list(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_FLOOR)),
):
    """Dated prep list: usual plates × recipe yield."""
    restaurant = get_or_create_restaurant(db, current_user)
    from services.prep_suggest import prep_list_dated

    return prep_list_dated(db, restaurant.id)


@router.get("")
async def today_prep(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_FLOOR)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    return {"items": prep_for_today(db, restaurant.id)}