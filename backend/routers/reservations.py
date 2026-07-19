from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, time

from database import get_db
import models
import schemas
import auth
from ai.reservation_optimizer import is_table_available, find_available_tables
from routers.deps import get_or_create_restaurant

router = APIRouter(prefix="/reservations", tags=["reservations"])

# Directive 015's permission matrix for `reservations`: RW = Owner, Manager,
# Supervisor, Waiter; nothing for Controller/Stockkeeper/Kitchen — there's no
# read-only tier for this route, it's RW or hidden entirely. Owner passes
# through every require_staff_role() call automatically (Role.ADMIN bypass),
# so it isn't listed explicitly below.
_CAN_WRITE = (models.StaffRole.MANAGER, models.StaffRole.SUPERVISOR, models.StaffRole.WAITER)


@router.get("/", response_model=List[schemas.ReservationOut])
async def get_reservations(
    date_filter: Optional[date] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
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


@router.get("/available-tables", response_model=List[schemas.AvailableTableOut])
async def get_available_tables(
    party_size: int = Query(..., gt=0),
    reservation_date: date = Query(...),
    reservation_time: time = Query(...),
    duration_minutes: int = Query(90, gt=0),
    exclude_reservation_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    """Best-fit-first table suggestions for a host — reuses the exact same
    availability/capacity logic create_reservation() already runs to reject
    a conflicting table_id, just exposed ahead of time so a host isn't
    guessing which table to assign. exclude_reservation_id lets the edit
    form suggest tables for a booking being rescheduled without that
    booking's own row shadowing its already-assigned table."""
    restaurant = get_or_create_restaurant(db, current_user)
    tables = find_available_tables(
        db,
        restaurant_id=restaurant.id,
        party_size=party_size,
        reservation_date=reservation_date,
        reservation_time=reservation_time,
        duration_minutes=duration_minutes,
        exclude_reservation_id=exclude_reservation_id,
    )
    return tables


@router.post("/", response_model=schemas.ReservationOut)
async def create_reservation(
    reservation: schemas.ReservationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)

    # Both checks below were entirely absent until 2026-07-08: `table_id` was
    # taken from the request body and written straight to the row. That allowed
    # (a) booking a table belonging to *another restaurant* by guessing its id,
    # and (b) double-booking one table — not merely under concurrency, but with
    # two plain sequential requests, since nothing ever consulted existing
    # reservations. `find_available_tables()` existed and was correct, but no
    # write path had ever called it.
    if reservation.table_id is not None:
        table = (
            db.query(models.Table)
            .filter(
                models.Table.id == reservation.table_id,
                models.Table.restaurant_id == restaurant.id,
            )
            .first()
        )
        # 404, not 403: a table belonging to another tenant must be
        # indistinguishable from one that does not exist, or the response
        # becomes an id-enumeration oracle for other restaurants' floor plans.
        if not table:
            raise HTTPException(status_code=404, detail="Table not found")

        if table.capacity < reservation.party_size:
            raise HTTPException(
                status_code=400,
                detail=f"Table seats {table.capacity}, party size is {reservation.party_size}",
            )

        if not is_table_available(
            db,
            restaurant_id=restaurant.id,
            table_id=reservation.table_id,
            reservation_date=reservation.reservation_date,
            reservation_time=reservation.reservation_time,
            duration_minutes=reservation.duration_minutes,
        ):
            raise HTTPException(
                status_code=409,
                detail="Table is already booked for an overlapping time slot",
            )

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
    try:
        db.commit()
    except IntegrityError:
        # The check above lost a race: a concurrent writer committed an
        # overlapping booking between our SELECT and our INSERT. The Postgres
        # EXCLUDE constraint (migration 009) is what actually caught it. Present
        # it as the same 409 the uncontended path returns.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Table is already booked for an overlapping time slot",
        )
    db.refresh(db_res)

    # 2026-07-18 event-map pass: front-of-house shouldn't have to keep
    # re-opening the bookings list to notice a new one. Actor excluded (the
    # staff member who took the booking already knows). Push-only, role-scoped.
    from events.bus import emit_async, EventType
    emit_async(EventType.RESERVATION_CREATED, {
        "restaurant_id": restaurant.id,
        "reservation_id": db_res.id,
        "customer_name": db_res.customer_name or "",
        "party_size": db_res.party_size or 0,
        "reservation_date": str(db_res.reservation_date) if db_res.reservation_date else "",
        "reservation_time": str(db_res.reservation_time) if db_res.reservation_time else "",
        "actor_user_id": current_user.id,
    })
    return _res_to_dict(db_res)


@router.put("/{reservation_id}", response_model=schemas.ReservationOut)
async def update_reservation(
    reservation_id: int,
    update: schemas.ReservationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    """General edit — party size grew, the customer called to move the time,
    or front-of-house is assigning/moving which table it's seated at.
    Distinct from update_reservation_status, which only ever flips `status`.
    Re-runs the same table/overlap validation create_reservation() does
    whenever the edit touches table_id, date, time, or duration — otherwise
    an edit could quietly create the double-booking creation already guards
    against."""
    restaurant = get_or_create_restaurant(db, current_user)
    reservation = db.query(models.Reservation).filter(
        models.Reservation.id == reservation_id,
        models.Reservation.restaurant_id == restaurant.id,
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    updates = update.dict(exclude_unset=True)

    new_table_id = updates.get("table_id", reservation.table_id)
    new_date = updates.get("reservation_date", reservation.reservation_date)
    new_time = updates.get("reservation_time", reservation.reservation_time)
    new_duration = updates.get("duration_minutes", reservation.duration_minutes)
    new_party_size = updates.get("party_size", reservation.party_size)

    touches_scheduling = any(
        k in updates for k in ("table_id", "reservation_date", "reservation_time", "duration_minutes")
    )

    if new_table_id is not None and touches_scheduling:
        table = db.query(models.Table).filter(
            models.Table.id == new_table_id,
            models.Table.restaurant_id == restaurant.id,
        ).first()
        # 404, not 403 — same id-enumeration reasoning as create_reservation().
        if not table:
            raise HTTPException(status_code=404, detail="Table not found")
        if table.capacity < new_party_size:
            raise HTTPException(
                status_code=400,
                detail=f"Table seats {table.capacity}, party size is {new_party_size}",
            )
        if not is_table_available(
            db,
            restaurant_id=restaurant.id,
            table_id=new_table_id,
            reservation_date=new_date,
            reservation_time=new_time,
            duration_minutes=new_duration,
            exclude_reservation_id=reservation.id,
        ):
            raise HTTPException(
                status_code=409,
                detail="Table is already booked for an overlapping time slot",
            )

    for key, value in updates.items():
        setattr(reservation, key, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Table is already booked for an overlapping time slot",
        )
    db.refresh(reservation)
    return _res_to_dict(reservation)


@router.patch("/{reservation_id}/status", response_model=schemas.ReservationOut)
async def update_reservation_status(
    reservation_id: int,
    update: schemas.ReservationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    reservation = db.query(models.Reservation).filter(
        models.Reservation.id == reservation_id,
        models.Reservation.restaurant_id == restaurant.id,
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    try:
        new_status = models.ReservationStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

    was_no_show = reservation.status == models.ReservationStatus.NO_SHOW
    was_cancelled = reservation.status == models.ReservationStatus.CANCELLED

    # Re-confirming a reservation (e.g. undoing a NO_SHOW/CANCELLED) re-occupies
    # its table/slot, so it must pass the same overlap check create_reservation()
    # runs — otherwise the slot freed by the cancel could already hold another
    # CONFIRMED booking, and flipping this one back produces two overlapping
    # confirmed reservations on one table. Only relevant when the target status
    # is CONFIRMED and a table is assigned; other transitions (cancel, complete,
    # no-show) only ever free a slot.
    if (
        new_status == models.ReservationStatus.CONFIRMED
        and reservation.status != models.ReservationStatus.CONFIRMED
        and reservation.table_id is not None
    ):
        if not is_table_available(
            db,
            restaurant_id=restaurant.id,
            table_id=reservation.table_id,
            reservation_date=reservation.reservation_date,
            reservation_time=reservation.reservation_time,
            duration_minutes=reservation.duration_minutes,
            exclude_reservation_id=reservation.id,
        ):
            raise HTTPException(
                status_code=409,
                detail="Table is already booked for an overlapping time slot",
            )

    reservation.status = new_status
    try:
        db.commit()
    except IntegrityError:
        # Lost the race to a concurrent writer, or the Postgres EXCLUDE
        # constraint (migration 009) caught an overlap the app-level check
        # above could not see under concurrency. Present it as the same 409
        # create_reservation() returns rather than a raw 500.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Table is already booked for an overlapping time slot",
        )
    db.refresh(reservation)

    # RESERVATION_NO_SHOW was subscribed to by executive.py (records into
    # ai/memory/store.py, triggers winback logic) but nothing ever emitted
    # it — found 2026-07-07 auditing the event orchestration end to end.
    # Only fire on the actual transition into NO_SHOW, not every PATCH.
    if new_status == models.ReservationStatus.NO_SHOW and not was_no_show:
        from events.bus import emit_async, EventType
        emit_async(EventType.RESERVATION_NO_SHOW, {
            "restaurant_id": restaurant.id,
            "customer_name": reservation.customer_name or "",
            "customer_phone": reservation.customer_phone or "",
            "party_size": reservation.party_size or 0,
        })

    # A booking freed by cancellation (2026-07-18 event-map pass) — the table/
    # slot is back, front-of-house should know without polling. Only on the
    # real transition into CANCELLED; actor excluded.
    if new_status == models.ReservationStatus.CANCELLED and not was_cancelled:
        from events.bus import emit_async, EventType
        emit_async(EventType.RESERVATION_CANCELLED, {
            "restaurant_id": restaurant.id,
            "reservation_id": reservation.id,
            "customer_name": reservation.customer_name or "",
            "party_size": reservation.party_size or 0,
            "reservation_date": str(reservation.reservation_date) if reservation.reservation_date else "",
            "reservation_time": str(reservation.reservation_time) if reservation.reservation_time else "",
            "actor_user_id": current_user.id,
        })

    return _res_to_dict(reservation)


@router.delete("/{reservation_id}")
async def delete_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_WRITE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    reservation = db.query(models.Reservation).filter(
        models.Reservation.id == reservation_id,
        models.Reservation.restaurant_id == restaurant.id,
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    # Capture before delete — the row is gone after commit but the booking is
    # just as cancelled as one flipped to CANCELLED via the status endpoint, so
    # it emits the same event. Skip it for an already-cancelled booking being
    # hard-deleted (a cleanup, not a new cancellation).
    was_cancelled = reservation.status == models.ReservationStatus.CANCELLED
    cancelled_payload = {
        "restaurant_id": restaurant.id,
        "reservation_id": reservation.id,
        "customer_name": reservation.customer_name or "",
        "party_size": reservation.party_size or 0,
        "reservation_date": str(reservation.reservation_date) if reservation.reservation_date else "",
        "reservation_time": str(reservation.reservation_time) if reservation.reservation_time else "",
        "actor_user_id": current_user.id,
    }

    db.delete(reservation)
    db.commit()

    if not was_cancelled:
        from events.bus import emit_async, EventType
        emit_async(EventType.RESERVATION_CANCELLED, cancelled_payload)

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
