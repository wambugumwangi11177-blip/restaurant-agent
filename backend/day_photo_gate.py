"""Day open and close photos are required once per zone."""

from __future__ import annotations

from sqlalchemy.orm import Session

import models
from bill_schedule import business_today
from routers.store_intake import ensure_zones


def _zones_missing(db: Session, restaurant_id: int, phase: str, day=None) -> list[str]:
    day = day or business_today()
    zones = ensure_zones(db, restaurant_id)
    done = {
        row.zone_id
        for row in db.query(models.StoreZoneDayPhoto).filter(
            models.StoreZoneDayPhoto.restaurant_id == restaurant_id,
            models.StoreZoneDayPhoto.business_date == day,
            models.StoreZoneDayPhoto.phase == phase,
        ).all()
    }
    return [zone.name for zone in zones if zone.id not in done]


def require_open_photos(db: Session, restaurant_id: int) -> None:
    missing = _zones_missing(db, restaurant_id, "open")
    if missing:
        from fastapi import HTTPException
        names = ", ".join(missing)
        raise HTTPException(
            status_code=428,
            detail=f"Take an opening photo for {names} before the day starts.",
        )


def require_close_photos(db: Session, restaurant_id: int) -> None:
    missing = _zones_missing(db, restaurant_id, "close")
    if missing:
        from fastapi import HTTPException
        names = ", ".join(missing)
        raise HTTPException(
            status_code=428,
            detail=f"Take a closing photo for {names} before you close the day.",
        )


def day_photo_status(db: Session, restaurant_id: int) -> dict:
    day = business_today()
    zones = ensure_zones(db, restaurant_id)
    by_phase = {"open": set(), "close": set()}
    for row in db.query(models.StoreZoneDayPhoto).filter(
        models.StoreZoneDayPhoto.restaurant_id == restaurant_id,
        models.StoreZoneDayPhoto.business_date == day,
    ).all():
        by_phase[row.phase].add(row.zone_id)
    return {
        "business_date": day.isoformat(),
        "zones": [
            {
                "id": zone.id,
                "name": zone.name,
                "open_done": zone.id in by_phase["open"],
                "close_done": zone.id in by_phase["close"],
            }
            for zone in zones
        ],
        "open_complete": all(zone.id in by_phase["open"] for zone in zones),
        "close_complete": all(zone.id in by_phase["close"] for zone in zones),
    }