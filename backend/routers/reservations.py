from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/reservations", tags=["reservations"])


def _get_restaurant(db: Session, user: models.User):
    rest = db.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == user.tenant_id
    ).first()
    if not rest:
        rest = models.Restaurant(
            name=f"{user.tenant.name}'s Restaurant",
            tenant_id=user.tenant_id,
        )
        db.add(rest)
        db.commit()
        db.refresh(rest)
    return rest


@router.get("/", response_model=List[schemas.ReservationOut])
async def get_reservations(
    date_filter: Optional[date] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = _get_restaurant(db, current_user)
    q = db.query(models.Reservation).filter(
        models.Reservation.restaurant_id == restaurant.id
    )
    if date_filter:
        q = q.filter(models.Reservation.reservation_date == date_filter)

    reservations = q.order_by(
        models.Reservation.reservation_date.desc(),
        models.Reservation.reservation_time.asc(),
    ).limit(200).all()

    return [_res_to_dict(r) for r in reservations]


@router.post("/", response_model=schemas.ReservationOut)
async def create_reservation(
    reservation: schemas.ReservationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = _get_restaurant(db, current_user)

    db_res = models.Reservation(
        restaurant_id=restaurant.id,
        customer_name=reservation.customer_name,
        customer_phone=reservation.customer_phone,
        customer_email=reservation.customer_email,
        party_size=reservation.party_size,
        reservation_date=reservation.reservation_date,
        reservation_time=reservation.reservation_time,
        duration_minutes=reservation.duration_minutes,
        table_id=reservation.table_id,
        deposit_paid=reservation.deposit_paid,
        notes=reservation.notes,
    )
    db.add(db_res)
    db.commit()
    db.refresh(db_res)
    return _res_to_dict(db_res)


@router.patch("/{reservation_id}/status", response_model=schemas.ReservationOut)
async def update_reservation_status(
    reservation_id: int,
    update: schemas.ReservationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    reservation = db.query(models.Reservation).filter(
        models.Reservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    try:
        reservation.status = models.ReservationStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

    db.commit()
    db.refresh(reservation)
    return _res_to_dict(reservation)


@router.delete("/{reservation_id}")
async def delete_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    reservation = db.query(models.Reservation).filter(
        models.Reservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    db.delete(reservation)
    db.commit()
    return {"message": "Reservation deleted"}


def _res_to_dict(r: models.Reservation) -> dict:
    return {
        "id": r.id,
        "customer_name": r.customer_name or "",
        "customer_phone": r.customer_phone or "",
        "customer_email": r.customer_email or "",
        "party_size": r.party_size or 2,
        "reservation_date": r.reservation_date,
        "reservation_time": r.reservation_time,
        "duration_minutes": r.duration_minutes or 90,
        "status": r.status.value if r.status else "confirmed",
        "deposit_paid": r.deposit_paid or False,
        "notes": r.notes or "",
        "table_id": r.table_id,
        "created_at": r.created_at,
    }
