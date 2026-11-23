"""Required zone photos at day open and close."""

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

import auth
import models
import storage
from database import get_db
from day_photo_gate import day_photo_status
from people import person_of
from routers.deps import get_or_create_restaurant
from routers.store_intake import _photo_bytes, ensure_zones
from staff_audit import record_entry
from store_access import require_store_role
from store_vision import run_zone_photo_check_safe
from time_utils import utcnow

router = APIRouter(prefix="/store/day-photos", tags=["store"])
_MAX = 4 * 1024 * 1024


@router.get("/status")
async def status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    return day_photo_status(db, restaurant.id)


@router.post("", status_code=201)
async def upload_zone_photo(
    background_tasks: BackgroundTasks,
    zone_id: int = Form(),
    phase: str = Form(),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    if phase not in ("open", "close"):
        raise HTTPException(status_code=400, detail="Say open or close.")
    restaurant = get_or_create_restaurant(db, current_user)
    ensure_zones(db, restaurant.id)
    zone = db.query(models.StockZone).filter(
        models.StockZone.id == zone_id,
        models.StockZone.restaurant_id == restaurant.id,
    ).first()
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found.")
    from bill_schedule import business_today

    day = business_today()
    exists = db.query(models.StoreZoneDayPhoto).filter(
        models.StoreZoneDayPhoto.restaurant_id == restaurant.id,
        models.StoreZoneDayPhoto.zone_id == zone.id,
        models.StoreZoneDayPhoto.business_date == day,
        models.StoreZoneDayPhoto.phase == phase,
    ).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="This zone already has a photo for today.")
    data, content_type = _photo_bytes(photo)
    if len(data) > _MAX:
        raise HTTPException(status_code=413, detail="That photo is too large.")
    key = storage.save(data, content_type=content_type)
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    row = models.StoreZoneDayPhoto(
        restaurant_id=restaurant.id,
        zone_id=zone.id,
        business_date=day,
        phase=phase,
        user_id=user.id,
        photo_storage_key=key,
        photo_content_type=content_type,
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    record_entry(
        db,
        restaurant.id,
        user,
        f"zone_{phase}_photo",
        "store_zone_day_photo",
        f"{user.email} photographed {zone.name} at {phase}.",
        entity_id=row.id,
        detail={"zone": zone.name, "phase": phase, "day": day.isoformat()},
    )
    db.commit()
    if phase == "open":
        from services.labor_schedule import touch_login_staff_shift

        touch_login_staff_shift(db, restaurant.id, user.id)
    background_tasks.add_task(run_zone_photo_check_safe, row.id)
    return {"id": row.id, "zone": zone.name, "phase": phase, "photo_path": f"/api/v1/store/day-photos/{row.id}/photo"}


@router.get("/{photo_id}/photo")
async def photo_bytes(
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    row = db.query(models.StoreZoneDayPhoto).filter(
        models.StoreZoneDayPhoto.id == photo_id,
        models.StoreZoneDayPhoto.restaurant_id == restaurant.id,
    ).first()
    if row is None or row.photo_storage_key.startswith("http"):
        raise HTTPException(status_code=404, detail="Photo not found")
    if current_user.role in (models.Role.ADMIN, models.Role.SUPERADMIN):
        pass
    else:
        require_store_role(current_user)
    return Response(content=storage.load(row.photo_storage_key), media_type=row.photo_content_type)