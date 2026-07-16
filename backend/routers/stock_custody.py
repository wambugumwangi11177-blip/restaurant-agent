"""
backend/routers/stock_custody.py
───────────────────────────────────
Store→kitchen chain-of-custody + variance reporting (directive 016).

Two-party transfer flow, deliberately not a single StockMovement row:

  1. POST /stock/transfers          — sender (Stockkeeper/Manager/Owner)
     declares what they're sending.
  2. POST /stock/transfers/{id}/confirm — receiver (Kitchen/Manager/Owner)
     independently reports what actually arrived. A mismatch is the signal
     (see ai/stock_custody.py's docstring) — it can't be self-certified by
     the sender alone.

On a matching confirm, the underlying StockMovement OUT/IN pair is written
so depletion-prediction code (which reads StockMovement, not this table)
keeps working unmodified.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from ai import stock_custody as variance_engine

router = APIRouter(prefix="/stock", tags=["stock-custody"])

# Directive 015's matrix: inventory write access is Owner/Manager/Stockkeeper;
# Kitchen has read + the ability to confirm what arrives at their own station.
_CAN_INITIATE = (models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER)
_CAN_CONFIRM = (models.StaffRole.MANAGER, models.StaffRole.KITCHEN, models.StaffRole.STOCKKEEPER)
_CAN_READ_VARIANCE = (models.StaffRole.MANAGER, models.StaffRole.CONTROLLER)
# Directive 017: the kitchen is the one asking (a "pull"), the storekeeper is
# the one fulfilling — distinct from _CAN_INITIATE's push-side roles.
_CAN_REQUEST = (models.StaffRole.MANAGER, models.StaffRole.KITCHEN)
_CAN_FULFILL = (models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER)
# A count is specifically valuable as an independent check when the counter
# isn't only ever the same person moving the stock — Controller included
# deliberately (a surprise count is a standard internal-audit practice).
_CAN_COUNT = (models.StaffRole.MANAGER, models.StaffRole.STOCKKEEPER, models.StaffRole.CONTROLLER)


@router.post("/transfers", response_model=schemas.StockTransferOut)
async def initiate_transfer(
    body: schemas.StockTransferCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_INITIATE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == body.inventory_item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    transfer = models.StockTransfer(
        restaurant_id=restaurant.id,
        inventory_item_id=item.id,
        quantity=body.quantity,
        unit=body.unit or item.unit,
        from_location=body.from_location,
        to_location=body.to_location,
        status=models.StockTransferStatus.PENDING,
        initiated_by_user_id=current_user.id,
        notes=body.notes,
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)

    # Outbound notification to whoever's on the receiving end is handled by
    # the frontend polling /stock/transfers?status=pending today — a
    # Twilio nudge to a specific receiving StaffMember requires knowing WHO
    # is meant to receive it, which this endpoint doesn't currently capture
    # (to_location is a place, not a person). Left for a follow-up once
    # there's a real "who's on kitchen duty right now" signal to route to;
    # see directive 016's webhook section for the inbound half, which is
    # wired regardless of how the receiver learns a transfer exists.

    return transfer


@router.post("/transfers/{transfer_id}/confirm", response_model=schemas.StockTransferOut)
async def confirm_transfer(
    transfer_id: int,
    body: schemas.StockTransferConfirm,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_CONFIRM)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    try:
        return variance_engine.confirm_transfer(
            db, transfer_id, restaurant.id, current_user.id,
            body.confirmed_quantity, body.notes,
        )
    except variance_engine.TransferConfirmError as exc:
        status_code = 404 if str(exc) == "Transfer not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc))


@router.post("/transfers/request", response_model=schemas.StockTransferOut)
async def request_transfer(
    body: schemas.StockTransferRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_REQUEST)),
):
    """Kitchen asks for an ingredient — directive 017's "pull" starting
    point. No quantity yet; see /transfers/{id}/fulfil."""
    restaurant = get_or_create_restaurant(db, current_user)
    try:
        return variance_engine.request_transfer(
            db, restaurant.id, body.inventory_item_id, current_user.id,
            body.from_location, body.to_location, body.notes,
        )
    except variance_engine.TransferRequestError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/transfers/{transfer_id}/fulfil", response_model=schemas.StockTransferOut)
async def fulfil_transfer(
    transfer_id: int,
    body: schemas.StockTransferFulfill,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_FULFILL)),
):
    """Storekeeper commits a quantity against a REQUESTED transfer —
    moves it to PENDING, same state the push flow starts at, so the
    receiver still confirms independently either way."""
    restaurant = get_or_create_restaurant(db, current_user)
    try:
        return variance_engine.fulfill_transfer(
            db, transfer_id, restaurant.id, current_user.id,
            body.quantity, body.notes,
        )
    except variance_engine.TransferRequestError as exc:
        status_code = 404 if str(exc) == "Transfer not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc))


@router.get("/transfers", response_model=List[schemas.StockTransferOut])
async def list_transfers(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_CONFIRM)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    q = db.query(models.StockTransfer).filter(
        models.StockTransfer.restaurant_id == restaurant.id
    )
    if status:
        try:
            q = q.filter(models.StockTransfer.status == models.StockTransferStatus[status.upper()])
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}")
    # id, not initiated_at: a REQUESTED transfer has no initiated_at yet
    # (nothing's been fulfilled), which would sort unpredictably relative
    # to rows that do. id is always populated and monotonic.
    return q.order_by(models.StockTransfer.id.desc()).limit(200).all()


@router.post("/counts", response_model=schemas.StockCountOut)
async def submit_stock_count(
    body: schemas.StockCountCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_COUNT)),
):
    """Record a physical count — directive 017's independent check, and
    the mechanism that reconciles InventoryItem.quantity to reality."""
    restaurant = get_or_create_restaurant(db, current_user)
    try:
        return variance_engine.submit_count(
            db, restaurant.id, body.inventory_item_id, current_user.id,
            body.counted_quantity, body.notes,
        )
    except variance_engine.StockCountError as exc:
        status_code = 404 if str(exc) == "Inventory item not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc))


@router.get("/counts", response_model=List[schemas.StockCountOut])
async def list_stock_counts(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_READ_VARIANCE)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    return db.query(models.StockCount).filter(
        models.StockCount.restaurant_id == restaurant.id
    ).order_by(models.StockCount.id.desc()).limit(200).all()


@router.get("/variance-report")
async def variance_report(
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_staff_role(*_CAN_READ_VARIANCE)),
):
    """Theoretical-vs-actual usage per item over the trailing `hours` window.
    Gated to Controller/Manager/Owner per directive 015 — a Controller reads
    this, doesn't cause it (separation of duties)."""
    restaurant = get_or_create_restaurant(db, current_user)
    report = variance_engine.compute_variance_report(db, restaurant.id, hours=hours)
    return {
        "restaurant_id": restaurant.id,
        "window_hours": hours,
        "threshold": variance_engine.VARIANCE_THRESHOLD,
        "items": [
            {
                "inventory_item_id": r.inventory_item_id,
                "item_name": r.item_name,
                "unit": r.unit,
                "theoretical_usage": r.theoretical_usage,
                "actual_usage": r.actual_usage,
                "variance_pct": r.variance_pct,
                "flagged": r.flagged,
            }
            for r in report
        ],
    }
