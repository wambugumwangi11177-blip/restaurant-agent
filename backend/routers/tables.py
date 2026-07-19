"""
backend/routers/tables.py
──────────────────────────
Floor management: the physical tables reservations get assigned to and the
manual front-of-house actions around them (open/seat, close/clear, mark
needing cleaning, mark cleaned). The Table model and its TableStatus enum
already existed (required by the reservation-overlap check in
ai/reservation_optimizer.py) but had no router — nothing could create, list,
or update one.

Not a standalone entry in directive 015's permission matrix: table/floor
management is a sub-concern of the `reservations` domain (the two are edited
from the same bookings screen), so this reuses that row's RW tuple —
Owner, Manager, Supervisor, Waiter — rather than introducing a new domain.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant

router = APIRouter(prefix="/tables", tags=["tables"])

_CAN_WRITE = (models.StaffRole.MANAGER, models.StaffRole.SUPERVISOR, models.StaffRole.WAITER)


@router.get("/", response_model=List[schemas.TableOut])
async def list_tables(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    return db.query(models.Table).filter(
        models.Table.restaurant_id == restaurant.id
    ).order_by(models.Table.table_number).all()


@router.post("/", response_model=schemas.TableOut)
async def create_table(
    body: schemas.TableCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    table = models.Table(
        restaurant_id=restaurant.id,
        table_number=body.table_number,
        capacity=body.capacity,
    )
    db.add(table)
    try:
        db.commit()
    except IntegrityError:
        # uq_tables_restaurant_number
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Table {body.table_number} already exists.")
    db.refresh(table)
    return table


@router.put("/{table_id}", response_model=schemas.TableOut)
async def update_table(
    table_id: int,
    body: schemas.TableUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    table = db.query(models.Table).filter(
        models.Table.id == table_id,
        models.Table.restaurant_id == restaurant.id,
    ).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    for key, value in body.dict(exclude_unset=True).items():
        setattr(table, key, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Another table already has that number.")
    db.refresh(table)
    return table


@router.patch("/{table_id}/status", response_model=schemas.TableOut)
async def update_table_status(
    table_id: int,
    body: schemas.TableStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    """Open a table for a walk-in (available -> occupied), close it out
    (occupied -> available), or flag it for housekeeping (-> cleaning ->
    available once cleaned)."""
    restaurant = get_or_create_restaurant(db, current_user)
    table = db.query(models.Table).filter(
        models.Table.id == table_id,
        models.Table.restaurant_id == restaurant.id,
    ).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    try:
        table.status = models.TableStatus(body.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")

    db.commit()
    db.refresh(table)
    return table


@router.delete("/{table_id}")
async def delete_table(
    table_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    table = db.query(models.Table).filter(
        models.Table.id == table_id,
        models.Table.restaurant_id == restaurant.id,
    ).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")

    db.delete(table)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This table has reservation history and can't be deleted.",
        )
    return {"message": "Table deleted"}
