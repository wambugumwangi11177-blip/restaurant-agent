"""Chef PIN, kitchen handover, spoilage, and the end-of-day count.

Quantities only. A chef never gets a login. Five wrong PINs lock that chef
for 15 minutes. A handover photo is checked after the stock has already moved,
and that check is not pushed. Spoilage of 5 or more, and any close that does
not match the books, waits for the owner. Smaller spoilage is only reported.
"""
import json
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy.orm import Session

import auth
import models
import storage
from database import get_db
from routers.deps import get_or_create_restaurant
from routers.store_intake import _balance, _photo_bytes, _sync_total, _zone
from schemas import StrictModel
from ai.notify import notify_users
from people import person_of
from staff_audit import record_entry
from store_access import require_module, require_store_role
from store_vision import run_handover_check_safe
from time_utils import utcnow

router = APIRouter(prefix="/store", tags=["store-control"])

PIN_ATTEMPTS = 5
PIN_LOCK_MINUTES = 15
SPOILAGE_APPROVAL_AT = 5
REASONS = ("spoiled", "broken", "expired", "spilled", "other")
# No tenant timezone column exists. Reports, the till, and this feed share Nairobi.
RESTAURANT_TIMEZONE = "Africa/Nairobi"


class CloseLineIn(StrictModel):
    item_id: int
    counted_qty: float = Field(ge=0)


class CloseIn(StrictModel):
    lines: list[CloseLineIn]
    working_alone: bool = False
    pin: str = ""


class ApprovalIn(StrictModel):
    kind: str
    id: int
    decision: str = "approve"
    note: str = ""


class PolicyIn(StrictModel):
    spoilage_approval_qty: float = Field(gt=0, le=100000)


def _owner(user: models.User) -> bool:
    return user.role in (models.Role.SUPERADMIN, models.Role.ADMIN)


def _require_owner(user: models.User) -> None:
    if not _owner(user):
        raise HTTPException(status_code=403, detail="The owner approves this.")


def tell_owners(db, user, restaurant, title: str, body: str) -> None:
    """A new item that needs the owner. The note does not include an amount."""
    owners = db.query(models.User).filter(
        models.User.tenant_id == user.tenant_id,
        models.User.role.in_((models.Role.ADMIN, models.Role.SUPERADMIN)),
        models.User.is_active.is_(True),
    ).all()
    if not owners:
        return
    notify_users(
        db,
        [owner.id for owner in owners],
        title,
        body,
        "store.approval",
        url="/eleven/approvals",
    )


def _threshold(restaurant) -> float:
    value = restaurant.spoilage_approval_qty
    return float(value if value is not None else SPOILAGE_APPROVAL_AT)


def _user(db, current) -> models.User:
    return db.query(models.User).filter(models.User.id == current.id).first()


def _when(value) -> str | None:
    return value.isoformat() if value else None


def _count_needs(count: int) -> str:
    if count == 0:
        return "Nothing needs you."
    if count == 1:
        return "1 thing needs you."
    return f"{count} things need you."


def _feed_ai(ai) -> dict | None:
    """A chip only when the check wrote a real note. A missing key stays off the owner feed."""
    if not isinstance(ai, dict):
        return None
    status = ai.get("status")
    note = str(ai.get("note") or "").strip()
    if status not in ("match", "mismatch") or not note or note.lower() == "ai check unavailable":
        return None
    return {"label": "AI", "status": status, "note": note}


def _action_label(item: dict) -> str:
    kind = item.get("kind")
    if kind == "waste":
        name = str(item.get("item_name") or "stock").strip().lower()
        quantity = item.get("quantity")
        unit = str(item.get("unit") or "").strip()
        if quantity is None:
            return "Approve a write-off"
        return f"Approve {quantity:g} {unit} {name} waste".replace("  ", " ").strip()
    if kind == "cost":
        label = str(item.get("label") or "bill").strip().lower()
        if not label.endswith("bill"):
            label = f"{label} bill"
        return f"Approve {label}"
    if kind == "close":
        return "Approve the day close"
    return "Approve this"


def _pin_ok(pin: str) -> bool:
    return pin.isdigit() and len(pin) == 4


def _minutes_left(until, now) -> int:
    seconds = (until - now).total_seconds()
    if seconds <= 0:
        return 0
    return max(1, int((seconds + 59) // 60))


def _chef(db, restaurant_id: int, chef_id: int) -> models.StoreChef:
    chef = db.query(models.StoreChef).filter(
        models.StoreChef.id == chef_id,
        models.StoreChef.restaurant_id == restaurant_id,
    ).first()
    if chef is None:
        raise HTTPException(status_code=404, detail="Chef not found")
    return chef


def _confirm_pin(db, restaurant, user, chef: models.StoreChef, pin: str) -> None:
    """Wrong attempts are saved immediately. The PIN itself is never written down."""
    now = utcnow()
    if chef.pin_locked_until and chef.pin_locked_until > now:
        record_entry(
            db, restaurant.id, user, "chef_pin_locked", "store_chef",
            f"{user.email} tried {chef.name}'s PIN while it was locked.",
            entity_id=chef.id,
            detail={"chef_id": chef.id, "chef_name": chef.name},
        )
        db.commit()
        minutes = _minutes_left(chef.pin_locked_until, now)
        raise HTTPException(status_code=423, detail=f"This PIN is locked. Try again in {minutes} minutes.")
    if not auth.verify_pin(pin, chef.hashed_pin):
        chef.failed_pin_attempts = (chef.failed_pin_attempts or 0) + 1
        locked = chef.failed_pin_attempts >= PIN_ATTEMPTS
        if locked:
            chef.pin_locked_until = now + timedelta(minutes=PIN_LOCK_MINUTES)
        record_entry(
            db, restaurant.id, user, "chef_pin_locked" if locked else "chef_pin_failed", "store_chef",
            f"{user.email} entered the wrong PIN for {chef.name}."
            + (" It is locked for 15 minutes." if locked else ""),
            entity_id=chef.id,
            detail={"chef_id": chef.id, "chef_name": chef.name, "attempts": chef.failed_pin_attempts},
        )
        db.commit()
        if locked:
            raise HTTPException(status_code=423, detail="This PIN is locked. Try again in 15 minutes.")
        raise HTTPException(status_code=400, detail="That PIN is wrong.")
    chef.failed_pin_attempts = 0
    chef.pin_locked_until = None


def _confirm_manager(db, restaurant, user, pin: str) -> models.User:
    """The other manager types their own PIN. Chefs are not accepted."""
    if user.staff_role not in (models.StaffRole.STOCKKEEPER, models.StaffRole.CONTROLLER):
        raise HTTPException(status_code=403, detail="The storekeeper and the accountant close the day.")
    now = utcnow()
    if user.pin_locked_until and user.pin_locked_until > now:
        record_entry(
            db, restaurant.id, user, "close_pin_locked", "day_close",
            f"{user.email} tried a close PIN while it was locked.",
        )
        db.commit()
        minutes = _minutes_left(user.pin_locked_until, now)
        raise HTTPException(status_code=423, detail=f"This PIN is locked. Try again in {minutes} minutes.")
    other = (
        models.StaffRole.CONTROLLER
        if user.staff_role == models.StaffRole.STOCKKEEPER
        else models.StaffRole.STOCKKEEPER
    )
    candidates = db.query(models.User).filter(
        models.User.tenant_id == user.tenant_id,
        models.User.staff_role == other,
        models.User.is_active.is_(True),
        models.User.hashed_pin.isnot(None),
    ).all()
    if not candidates:
        raise HTTPException(status_code=400, detail="The other manager needs a PIN before they can confirm.")
    match = next((person for person in candidates if _pin_ok(pin) and auth.verify_pin(pin, person.hashed_pin)), None)
    if match is None:
        user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
        locked = user.pin_failed_attempts >= PIN_ATTEMPTS
        if locked:
            user.pin_locked_until = now + timedelta(minutes=PIN_LOCK_MINUTES)
        record_entry(
            db, restaurant.id, user, "close_pin_locked" if locked else "close_pin_failed", "day_close",
            f"{user.email} entered the wrong PIN for the day close."
            + (" It is locked for 15 minutes." if locked else ""),
            detail={"attempts": user.pin_failed_attempts},
        )
        db.commit()
        if locked:
            raise HTTPException(status_code=423, detail="This PIN is locked. Try again in 15 minutes.")
        raise HTTPException(status_code=400, detail="That PIN is wrong.")
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    return match


def _item(db, restaurant_id: int, item_id: int) -> models.InventoryItem:
    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == item_id,
        models.InventoryItem.restaurant_id == restaurant_id,
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def _parse_lines(raw: str) -> list[dict]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Lines must be a JSON list.")
    if not isinstance(parsed, list) or not parsed:
        raise HTTPException(status_code=400, detail="Pick at least one item.")
    for row in parsed:
        if not isinstance(row, dict):
            raise HTTPException(status_code=400, detail="Each line needs an item and a quantity.")
        if any(key in row for key in ("cost", "price", "amount", "amount_cents")):
            raise HTTPException(status_code=422, detail="Prices are not entered by this role.")
    return parsed


def _move(db, restaurant, item, quantity: float, source_name: str, dest_name: str | None, user, reason: str):
    source = _zone(db, restaurant.id, source_name)
    origin = _balance(db, restaurant.id, item.id, source.id)
    if origin.quantity < quantity:
        raise HTTPException(status_code=400, detail=f"Only {origin.quantity} {item.unit} is in {source.name}.")
    origin.quantity -= quantity
    if dest_name:
        dest = _zone(db, restaurant.id, dest_name)
        _balance(db, restaurant.id, item.id, dest.id).quantity += quantity
    _sync_total(db, item)
    db.add(models.StockMovement(
        inventory_item_id=item.id,
        movement_type=models.StockMovementType.OUT,
        quantity=quantity,
        reason=reason,
        created_at=utcnow(),
        performed_by_user_id=user.id,
    ))
    return source


def _optional_photo(upload: UploadFile | None) -> tuple[bytes, str] | None:
    if upload is None or not upload.filename:
        return None
    return _photo_bytes(upload)


def _chef_public(db, chef: models.StoreChef) -> dict:
    creator = db.query(models.User).filter(models.User.id == chef.created_by_user_id).first()
    return {
        "id": chef.id,
        "name": chef.name,
        "has_photo": bool(chef.photo_storage_key),
        "created_by": creator.email if creator else None,
        "created_at": _when(chef.created_at),
    }


def _handover_public(db, handover: models.KitchenHandover, viewer: models.User) -> dict:
    chef = db.query(models.StoreChef).filter(models.StoreChef.id == handover.chef_id).first()
    creator = db.query(models.User).filter(models.User.id == handover.created_by_user_id).first()
    lines = (
        db.query(models.KitchenHandoverLine)
        .filter(models.KitchenHandoverLine.handover_id == handover.id)
        .order_by(models.KitchenHandoverLine.id.asc())
        .all()
    )
    check = (
        db.query(models.HandoverVisionCheck)
        .filter(models.HandoverVisionCheck.handover_id == handover.id)
        .order_by(models.HandoverVisionCheck.id.desc())
        .first()
    )
    who = person_of(db, creator)
    body = {
        "id": handover.id,
        "chef_name": chef.name if chef else None,
        "created_by": creator.email if creator else None,
        "person_name": who["person_name"],
        "person_email": who["person_email"],
        "initial": who["initial"],
        "created_at": _when(handover.created_at),
        "photo_path": f"/api/v1/store/handovers/{handover.id}/photo" if handover.photo_storage_key else None,
        "has_photo": bool(handover.photo_storage_key),
        "lines": [
            {
                "item_name": line.item_name,
                "quantity": line.quantity,
                "unit": line.unit,
                "from_zone": line.from_zone,
            }
            for line in lines
        ],
    }
    if check is None:
        body["ai"] = None
    elif _owner(viewer):
        payload = json.loads(check.result_json or "{}")
        body["ai"] = {
            "label": "AI",
            "status": check.status,
            "note": payload.get("note") or payload.get("message"),
            "mismatches": payload.get("mismatches") or [],
        }
    else:
        body["ai"] = {"label": "AI", "status": check.status}
    return body


def _spoilage_public(db, row: models.SpoilageRecord) -> dict:
    chef = db.query(models.StoreChef).filter(models.StoreChef.id == row.chef_id).first()
    creator = db.query(models.User).filter(models.User.id == row.user_id).first()
    who = person_of(db, creator)
    return {
        "id": row.id,
        "item_name": row.item_name,
        "quantity": row.quantity,
        "unit": row.unit,
        "zone": row.zone_name,
        "reason_code": row.reason_code,
        "reason_text": row.reason_text,
        "chef_name": chef.name if chef else None,
        "status": row.status,
        "created_by": creator.email if creator else None,
        "person_name": who["person_name"],
        "person_email": who["person_email"],
        "initial": who["initial"],
        "created_at": _when(row.created_at),
        "approved_at": _when(row.approved_at),
        "owner_note": row.owner_note or "",
        "photo_path": f"/api/v1/store/spoilage/{row.id}/photo",
    }


def _close_public(db, row: models.DayClose) -> dict:
    creator = db.query(models.User).filter(models.User.id == row.user_id).first()
    confirmer = db.query(models.User).filter(models.User.id == row.confirmer_user_id).first() if row.confirmer_user_id else None
    lines = (
        db.query(models.DayCloseLine)
        .filter(models.DayCloseLine.close_id == row.id)
        .order_by(models.DayCloseLine.id.asc())
        .all()
    )
    who = person_of(db, creator)
    return {
        "id": row.id,
        "working_alone": bool(row.working_alone),
        "confirmer_name": person_of(db, confirmer)["person_name"] if confirmer else None,
        "status": row.status,
        "created_by": creator.email if creator else None,
        "person_name": who["person_name"],
        "person_email": who["person_email"],
        "initial": who["initial"],
        "created_at": _when(row.created_at),
        "approved_at": _when(row.approved_at),
        "owner_note": row.owner_note or "",
        "lines": [
            {
                "item_name": line.item_name,
                "unit": line.unit,
                "expected_qty": line.expected_qty,
                "counted_qty": line.counted_qty,
                "difference": line.counted_qty - line.expected_qty,
            }
            for line in lines
        ],
    }


@router.post("/chefs", status_code=201)
async def add_chef(
    name: str = Form(),
    pin: str = Form(),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    user = _user(db, current_user)
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="The chef needs a name.")
    if not _pin_ok(pin):
        raise HTTPException(status_code=400, detail="A chef PIN is 4 digits.")
    picture = _optional_photo(photo)
    photo_key = None
    photo_type = None
    if picture:
        data, photo_type = picture
        photo_key = storage.save(data, content_type=photo_type)
    try:
        chef = models.StoreChef(
            restaurant_id=restaurant.id,
            name=cleaned,
            photo_storage_key=photo_key,
            photo_content_type=photo_type,
            hashed_pin=auth.get_pin_hash(pin),
            failed_pin_attempts=0,
            created_by_user_id=user.id,
            created_at=utcnow(),
        )
        db.add(chef)
        db.flush()
        record_entry(
            db, restaurant.id, user, "chef_added", "store_chef",
            f"{user.email} added chef {cleaned}.",
            entity_id=chef.id,
            detail={"name": cleaned, "has_photo": photo_key is not None},
        )
        db.commit()
    except Exception:
        db.rollback()
        if photo_key:
            storage.delete(photo_key)
        raise
    return _chef_public(db, chef)


@router.get("/chefs")
async def list_chefs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.StoreChef)
        .filter(models.StoreChef.restaurant_id == restaurant.id)
        .order_by(models.StoreChef.id.asc())
        .all()
    )
    return {"chefs": [_chef_public(db, row) for row in rows]}


@router.get("/chefs/{chef_id}/photo")
async def chef_photo(
    chef_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    chef = _chef(db, restaurant.id, chef_id)
    if not chef.photo_storage_key or chef.photo_storage_key.startswith("http"):
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(content=storage.load(chef.photo_storage_key), media_type=chef.photo_content_type or "image/jpeg")


@router.post("/handover", status_code=201)
async def hand_to_kitchen(
    background: BackgroundTasks,
    lines: str = Form(),
    chef_id: int = Form(),
    pin: str = Form(),
    from_zone: str = Form("Main store"),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "store-issue")
    restaurant = get_or_create_restaurant(db, current_user)
    user = _user(db, current_user)
    parsed = _parse_lines(lines)
    chef = _chef(db, restaurant.id, chef_id)
    _confirm_pin(db, restaurant, user, chef, pin)
    picture = _optional_photo(photo)
    if picture is None:
        raise HTTPException(status_code=422, detail="Photograph what the kitchen received.")
    saved_keys = []
    photo_key = None
    photo_type = None
    if picture:
        data, photo_type = picture
        photo_key = storage.save(data, content_type=photo_type)
        saved_keys.append(photo_key)
    try:
        handover = models.KitchenHandover(
            restaurant_id=restaurant.id,
            created_by_user_id=user.id,
            chef_id=chef.id,
            photo_storage_key=photo_key,
            photo_content_type=photo_type,
            created_at=utcnow(),
        )
        db.add(handover)
        db.flush()
        if photo_key:
            db.add(models.HandoverVisionCheck(
                handover_id=handover.id,
                status="pending",
                created_at=utcnow(),
            ))
        described = []
        for raw in parsed:
            try:
                quantity = float(raw.get("quantity"))
            except (TypeError, ValueError):
                quantity = 0
            if quantity <= 0:
                raise HTTPException(status_code=400, detail="Each line needs a quantity.")
            item = _item(db, restaurant.id, int(raw.get("item_id") or 0))
            source = _move(db, restaurant, item, quantity, from_zone, "Kitchen", user, "handover")
            db.add(models.KitchenHandoverLine(
                handover_id=handover.id,
                inventory_item_id=item.id,
                item_name=item.item_name,
                quantity=quantity,
                unit=item.unit or "",
                from_zone=source.name,
            ))
            described.append(f"{quantity} {item.unit} {item.item_name}")
        record_entry(
            db, restaurant.id, user, "kitchen_handover", "kitchen_handover",
            f"{user.email} handed {', '.join(described)} to the kitchen. {chef.name} confirmed.",
            entity_id=handover.id,
            detail={"chef_id": chef.id, "chef_name": chef.name, "lines": len(parsed), "photo": picture is not None},
        )
        db.commit()
    except Exception:
        db.rollback()
        for key in saved_keys:
            storage.delete(key)
        raise
    if picture:
        background.add_task(run_handover_check_safe, handover.id)
    body = _handover_public(db, handover, user)
    if picture:
        body["ai"] = {"label": "AI", "status": "pending"}
    return body


@router.get("/handovers")
async def list_handovers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.KitchenHandover)
        .filter(models.KitchenHandover.restaurant_id == restaurant.id)
        .order_by(models.KitchenHandover.id.desc())
        .limit(40)
        .all()
    )
    return {"handovers": [_handover_public(db, row, current_user) for row in rows]}


@router.get("/handovers/{handover_id}/photo")
async def handover_photo(
    handover_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    row = db.query(models.KitchenHandover).filter(
        models.KitchenHandover.id == handover_id,
        models.KitchenHandover.restaurant_id == restaurant.id,
    ).first()
    if row is None or not row.photo_storage_key or row.photo_storage_key.startswith("http"):
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(content=storage.load(row.photo_storage_key), media_type=row.photo_content_type or "image/jpeg")


@router.post("/spoilage", status_code=201)
async def record_spoilage(
    item_id: int = Form(),
    quantity: float = Form(),
    zone: str = Form("Main store"),
    reason_code: str = Form(),
    reason_text: str = Form(""),
    chef_id: int = Form(),
    pin: str = Form(),
    photo: UploadFile = File(),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "waste")
    restaurant = get_or_create_restaurant(db, current_user)
    user = _user(db, current_user)
    if reason_code not in REASONS:
        raise HTTPException(status_code=400, detail="Pick a reason.")
    note = reason_text.strip()
    if reason_code == "other" and not note:
        raise HTTPException(status_code=400, detail="Write what happened.")
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Each line needs a quantity.")
    chef = _chef(db, restaurant.id, chef_id)
    _confirm_pin(db, restaurant, user, chef, pin)
    data, content_type = _photo_bytes(photo)
    item = _item(db, restaurant.id, item_id)
    key = storage.save(data, content_type=content_type)
    try:
        place = _move(db, restaurant, item, quantity, zone, None, user, "spoilage")
        status = "needs_approval" if quantity >= _threshold(restaurant) else "reported"
        row = models.SpoilageRecord(
            restaurant_id=restaurant.id,
            user_id=user.id,
            chef_id=chef.id,
            inventory_item_id=item.id,
            item_name=item.item_name,
            quantity=quantity,
            unit=item.unit or "",
            zone_name=place.name,
            reason_code=reason_code,
            reason_text=note,
            photo_storage_key=key,
            photo_content_type=content_type,
            status=status,
            created_at=utcnow(),
        )
        db.add(row)
        db.flush()
        record_entry(
            db, restaurant.id, user, "spoilage_recorded", "spoilage_record",
            f"{user.email} wrote off {quantity} {item.unit} of {item.item_name} ({reason_code}). {chef.name} confirmed.",
            entity_id=row.id,
            detail={"reason_code": reason_code, "status": status, "chef_name": chef.name},
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    body = _spoilage_public(db, row)
    body["message"] = "The owner will look at this." if status == "needs_approval" else "Saved."
    if status == "needs_approval":
        tell_owners(db, user, restaurant, "Waste needs you", f"{quantity:g} {item.unit} of {item.item_name} was written off.")
    return body


@router.get("/spoilage")
async def list_spoilage(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.SpoilageRecord)
        .filter(models.SpoilageRecord.restaurant_id == restaurant.id)
        .order_by(models.SpoilageRecord.id.desc())
        .limit(40)
        .all()
    )
    return {"spoilage": [_spoilage_public(db, row) for row in rows]}


@router.get("/spoilage/{spoilage_id}/photo")
async def spoilage_photo(
    spoilage_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    row = db.query(models.SpoilageRecord).filter(
        models.SpoilageRecord.id == spoilage_id,
        models.SpoilageRecord.restaurant_id == restaurant.id,
    ).first()
    if row is None or row.photo_storage_key.startswith("http"):
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(content=storage.load(row.photo_storage_key), media_type=row.photo_content_type)


@router.get("/close/expected")
async def expected_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "day-close")
    restaurant = get_or_create_restaurant(db, current_user)
    items = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.restaurant_id == restaurant.id, models.InventoryItem.quantity > 0)
        .order_by(models.InventoryItem.item_name.asc())
        .all()
    )
    return {
        "items": [
            {"item_id": item.id, "item_name": item.item_name, "unit": item.unit, "expected_qty": item.quantity}
            for item in items
        ]
    }


@router.post("/close", status_code=201)
async def close_day(
    body: CloseIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "day-close")
    restaurant = get_or_create_restaurant(db, current_user)
    user = _user(db, current_user)
    confirmer = None
    if user.staff_role == models.StaffRole.KITCHEN:
        raise HTTPException(status_code=403, detail="Chefs do not close the day.")
    if body.working_alone:
        if body.pin:
            raise HTTPException(status_code=400, detail="Working alone does not use a second PIN.")
    else:
        if not body.pin:
            raise HTTPException(status_code=400, detail="The other manager confirms the close with their PIN.")
        confirmer = _confirm_manager(db, restaurant, user, body.pin)
    expected = {
        item.id: item
        for item in db.query(models.InventoryItem).filter(
            models.InventoryItem.restaurant_id == restaurant.id,
            models.InventoryItem.quantity > 0,
        ).all()
    }
    seen = [line.item_id for line in body.lines]
    if len(seen) != len(set(seen)):
        raise HTTPException(status_code=400, detail="Count each item once.")
    if set(seen) != set(expected):
        raise HTTPException(status_code=400, detail="Count every item that is in stock.")
    differs = False
    close = models.DayClose(
        restaurant_id=restaurant.id,
        user_id=user.id,
        confirmer_user_id=confirmer.id if confirmer else None,
        working_alone=body.working_alone,
        status="reported",
        created_at=utcnow(),
    )
    db.add(close)
    db.flush()
    for line in body.lines:
        item = expected[line.item_id]
        if abs(line.counted_qty - item.quantity) >= _threshold(restaurant):
            differs = True
        db.add(models.DayCloseLine(
            close_id=close.id,
            inventory_item_id=item.id,
            item_name=item.item_name,
            unit=item.unit or "",
            expected_qty=item.quantity,
            counted_qty=line.counted_qty,
        ))
    close.status = "needs_approval" if differs else "reported"
    who = " Working alone." if body.working_alone else f" {person_of(db, confirmer)['person_name']} confirmed."
    record_entry(
        db, restaurant.id, user, "day_closed", "day_close",
        f"{user.email} closed the day.{who}"
        + (" The count differs from the books." if differs else " The count matches."),
        entity_id=close.id,
        detail={"working_alone": body.working_alone, "status": close.status, "lines": len(body.lines)},
    )
    db.commit()
    payload = _close_public(db, close)
    payload["message"] = "The owner will look at the difference." if differs else "Saved."
    if differs:
        tell_owners(db, user, restaurant, "The day close needs you", "The count differs from the books.")
    return payload


@router.get("/closes")
async def list_closes(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.DayClose)
        .filter(models.DayClose.restaurant_id == restaurant.id)
        .order_by(models.DayClose.id.desc())
        .limit(40)
        .all()
    )
    return {"closes": [_close_public(db, row) for row in rows]}


@router.get("/approvals")
async def list_approvals(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    spoilage = (
        db.query(models.SpoilageRecord)
        .filter(models.SpoilageRecord.restaurant_id == restaurant.id)
        .order_by(models.SpoilageRecord.id.desc())
        .limit(40)
        .all()
    )
    closes = (
        db.query(models.DayClose)
        .filter(models.DayClose.restaurant_id == restaurant.id)
        .order_by(models.DayClose.id.desc())
        .limit(40)
        .all()
    )
    handovers = (
        db.query(models.KitchenHandover)
        .filter(models.KitchenHandover.restaurant_id == restaurant.id)
        .order_by(models.KitchenHandover.id.desc())
        .limit(40)
        .all()
    )
    costs = (
        db.query(models.RunningCost)
        .filter(models.RunningCost.restaurant_id == restaurant.id)
        .order_by(models.RunningCost.id.desc())
        .limit(40)
        .all()
    )
    deliveries = (
        db.query(models.DeliveryReceipt)
        .filter(models.DeliveryReceipt.restaurant_id == restaurant.id)
        .order_by(models.DeliveryReceipt.id.desc())
        .limit(20)
        .all()
    )
    events = []
    for row in spoilage:
        item = _spoilage_public(db, row)
        item["kind"] = "waste"
        item["headline"] = f"{item['person_name']} wrote off {row.quantity:g} {row.unit} of {row.item_name}."
        item["emphasis"] = f"{row.quantity:g} {row.unit}"
        item["action"] = _action_label(item)
        events.append(item)
    for row in closes:
        item = _close_public(db, row)
        item["kind"] = "close"
        gap = next((line for line in item["lines"] if abs(line["difference"]) > 1e-6), None)
        if item["working_alone"]:
            item["headline"] = f"{item['person_name']} closed the day working alone."
        elif item.get("confirmer_name"):
            item["headline"] = f"{item['person_name']} closed the day with {item['confirmer_name']}."
        else:
            item["headline"] = f"{item['person_name']} closed the day."
        if gap:
            item["emphasis"] = f"{abs(gap['difference']):g} {gap['unit']}"
            item["headline"] += f" {gap['item_name']} is {item['emphasis']} off the books."
        item["action"] = _action_label(item)
        events.append(item)
    for row in handovers:
        item = _handover_public(db, row, current_user)
        item["kind"] = "handover"
        moved = ", ".join(f"{line['quantity']:g} {line['unit']} {line['item_name']}" for line in item["lines"])
        item["headline"] = f"{item['person_name']} handed {moved} to {item['chef_name']}."
        if item["lines"]:
            first = item["lines"][0]
            item["emphasis"] = f"{first['quantity']:g} {first['unit']}"
        item["ai"] = _feed_ai(item.get("ai"))
        item["action"] = _action_label(item)
        events.append(item)
    for row in costs:
        creator = db.query(models.User).filter(models.User.id == row.user_id).first()
        who = person_of(db, creator)
        if row.status == "unknown":
            headline = f"{who['person_name']} does not know {row.label}."
        elif row.status == "approved":
            headline = f"{who['person_name']} sent {row.label}. You approved it."
        elif row.status == "declined":
            headline = f"{who['person_name']} sent {row.label}. You declined it."
        else:
            headline = f"{who['person_name']} sent {row.label} for approval."
        events.append({
            "id": row.id,
            "kind": "cost",
            "status": row.status,
            "label": row.label,
            "cadence": row.cadence,
            "due_day": row.due_day,
            "amount_cents": row.amount_cents if row.status != "unknown" else None,
            "headline": headline,
            "emphasis": row.label if row.status != "unknown" else None,
            "action": _action_label({"kind": "cost", "label": row.label}),
            "created_at": _when(row.created_at),
            "owner_note": row.owner_note or "",
            "photo_path": f"/api/v1/store/costs/{row.id}/receipt" if row.receipt_storage_key else None,
            **who,
        })
    for row in deliveries:
        creator = db.query(models.User).filter(models.User.id == row.received_by_user_id).first()
        who = person_of(db, creator)
        supplier = db.query(models.Supplier).filter(models.Supplier.id == row.supplier_id).first()
        lines = db.query(models.DeliveryReceiptLine).filter(models.DeliveryReceiptLine.receipt_id == row.id).all()
        photo = db.query(models.DeliveryEvidencePhoto).filter(models.DeliveryEvidencePhoto.receipt_id == row.id).first()
        check = (
            db.query(models.DeliveryVisionCheck)
            .filter(models.DeliveryVisionCheck.receipt_id == row.id)
            .order_by(models.DeliveryVisionCheck.id.desc())
            .first()
        )
        note = None
        if check and check.result_json:
            try:
                note = json.loads(check.result_json).get("note")
            except json.JSONDecodeError:
                note = None
        goods = ", ".join(f"{line.quantity:g} {line.unit} {line.item_name}" for line in lines) or "a delivery"
        emphasis = f"{lines[0].quantity:g} {lines[0].unit}" if lines else None
        events.append({
            "id": row.id,
            "kind": "delivery",
            "headline": f"{who['person_name']} received {goods}" + (f" from {supplier.name}." if supplier else "."),
            "emphasis": emphasis,
            "created_at": _when(row.received_at),
            "photo_path": f"/api/v1/store/deliveries/{row.id}/photos/{photo.id}" if photo else None,
            "ai": _feed_ai({"status": check.status, "note": note} if check else None),
            **who,
        })
    events.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    pending = [item for item in events if item.get("status") == "needs_approval"]
    unknown = [row.label for row in costs if row.status == "unknown"]
    orders = db.query(models.Order).filter(models.Order.restaurant_id == restaurant.id).count()
    approved_bills = [row.label for row in costs if row.status == "approved"]
    if orders:
        money = "The till has sales. Approved bills sit with them on Money."
    elif approved_bills:
        money = "Waiting for the till. " + ", ".join(approved_bills) + " will be in the profit and loss."
    else:
        money = "Waiting for the till."
    stock_line = "Nothing is in stock yet."
    stock_figure = None
    stock_quiet = True
    latest_close = closes[0] if closes else None
    if latest_close is not None:
        public = next(item for item in events if item["kind"] == "close" and item["id"] == latest_close.id)
        stock_figure = public.get("emphasis")
        if stock_figure:
            who = public["person_name"]
            if public.get("working_alone"):
                stock_line = f"{who} closed the day working alone."
            elif public.get("confirmer_name"):
                stock_line = f"{who} closed the day with {public['confirmer_name']}."
            else:
                stock_line = f"{who} closed the day."
            stock_quiet = False
        else:
            stock_line = public["headline"]
    elif db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant.id,
        models.InventoryItem.quantity > 0,
    ).first():
        stock_line = "Stock is in the store. No count is waiting."
    waste_line = "No waste has been written off."
    waste_figure = None
    waste_quiet = True
    if spoilage:
        latest_waste = next(item for item in events if item["kind"] == "waste" and item["id"] == spoilage[0].id)
        waste_figure = latest_waste.get("emphasis")
        waste_line = f"{latest_waste['person_name']} wrote off {spoilage[0].item_name}."
        waste_quiet = False
    count = len(pending)
    attention = _count_needs(count)
    dishes = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == restaurant.id).all()
    missing_recipes = 0
    for dish in dishes:
        if db.query(models.MenuIngredient).filter(models.MenuIngredient.menu_item_id == dish.id).first() is None:
            missing_recipes += 1
    return {
        "pending": pending,
        "events": events,
        "timezone": RESTAURANT_TIMEZONE,
        "attention": {"count": count, "sentence": attention},
        "cards": [
            {"id": "stock", "title": "Stock", "figure": stock_figure, "sentence": stock_line, "quiet": stock_quiet},
            {"id": "waste", "title": "Missing and waste", "figure": waste_figure, "sentence": waste_line, "quiet": waste_quiet},
            {
                "id": "money",
                "title": "Money",
                "figure": "Till live" if orders else None,
                "sentence": money,
                "quiet": not orders,
            },
        ],
        "unknown_costs": unknown,
        "recipes_missing": missing_recipes,
        "approved_bills": approved_bills,
        "till_live": orders > 0,
    }


@router.post("/approvals")
async def approve(
    body: ApprovalIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    user = _user(db, current_user)
    now = utcnow()
    if body.decision not in ("approve", "decline"):
        raise HTTPException(status_code=400, detail="Approve or decline.")
    verb = "approved" if body.decision == "approve" else "declined"
    if body.kind in ("spoilage", "waste"):
        row = db.query(models.SpoilageRecord).filter(
            models.SpoilageRecord.id == body.id,
            models.SpoilageRecord.restaurant_id == restaurant.id,
        ).first()
        action = f"spoilage_{verb}"
        summary = f"{user.email} {verb} the spoilage of {row.item_name}." if row else ""
    elif body.kind == "close":
        row = db.query(models.DayClose).filter(
            models.DayClose.id == body.id,
            models.DayClose.restaurant_id == restaurant.id,
        ).first()
        action = f"day_close_{verb}"
        summary = f"{user.email} {verb} the day close." if row else ""
    elif body.kind == "cost":
        row = db.query(models.RunningCost).filter(
            models.RunningCost.id == body.id,
            models.RunningCost.restaurant_id == restaurant.id,
        ).first()
        action = f"running_cost_{verb}"
        summary = f"{user.email} {verb} {row.label}." if row else ""
    else:
        raise HTTPException(status_code=400, detail="Choose waste, a day close, or a bill.")
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    if row.status != "needs_approval":
        raise HTTPException(status_code=400, detail="This one does not need approval.")
    row.status = "approved" if body.decision == "approve" else "declined"
    row.approved_by_user_id = user.id
    row.approved_at = now
    row.owner_note = body.note.strip()
    record_entry(
        db, restaurant.id, user, action, body.kind,
        summary,
        entity_id=row.id,
        detail={"approved_at": _when(now), "decision": body.decision},
    )
    db.commit()
    return {
        "id": row.id,
        "kind": body.kind,
        "status": row.status,
        "approved_by": user.email,
        "approved_at": _when(now),
        "owner_note": row.owner_note,
    }


@router.get("/policy")
async def get_policy(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    return {"spoilage_approval_qty": _threshold(restaurant)}


@router.put("/policy")
async def save_policy(
    body: PolicyIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    restaurant.spoilage_approval_qty = body.spoilage_approval_qty
    record_entry(
        db, restaurant.id, _user(db, current_user), "approval_threshold", "restaurant",
        f"The owner set the approval line at {body.spoilage_approval_qty:g}.",
        entity_id=restaurant.id,
        detail={"spoilage_approval_qty": body.spoilage_approval_qty},
    )
    db.commit()
    return {"spoilage_approval_qty": restaurant.spoilage_approval_qty}


@router.get("/costs/{cost_id}/receipt")
async def cost_receipt(
    cost_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    row = db.query(models.RunningCost).filter(
        models.RunningCost.id == cost_id,
        models.RunningCost.restaurant_id == restaurant.id,
    ).first()
    if row is None or not row.receipt_storage_key or row.receipt_storage_key.startswith("http"):
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(content=storage.load(row.receipt_storage_key), media_type=row.receipt_content_type or "image/jpeg")
