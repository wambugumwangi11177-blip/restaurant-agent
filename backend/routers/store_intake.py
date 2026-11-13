"""Suppliers, deliveries, zones, opening counts, issues, waste, and bills.

Quantities only on the storekeeper paths. Prices are confirmed later by the
owner or the controller, from the invoice photo. Delivery rows are created
once: lines and photos are not edited.
"""
import hashlib
import json
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy.orm import Session

import auth
import models
import storage
from database import get_db
from phone_utils import normalize_phone
from routers.deps import get_or_create_restaurant
from schemas import StrictModel
from staff_audit import record_entry
from store_access import can_see_prices, require_module, require_store_role
from store_vision import run_check_safe
from time_utils import utcnow

router = APIRouter(prefix="/store", tags=["store"])

_ZONES = (
    ("Main store", "store"),
    ("Cold room", "cold"),
    ("Bar", "bar"),
    ("Kitchen", "kitchen"),
)
_MAX_PHOTO = 4 * 1024 * 1024


_ARRIVAL_LABELS = {
    "phone": "Phone order",
    "scheduled": "Scheduled delivery",
    "pickup": "Pickup",
    "other": "Other",
}


class SupplierIn(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = ""
    brings: str = Field(min_length=1, max_length=80)
    arrival: str = ""


class OpeningIn(StrictModel):
    item_name: str = Field(min_length=1, max_length=120)
    quantity: float = Field(ge=0)
    unit: str = Field(min_length=1, max_length=40)
    zone: str = "Main store"
    buying_unit: str | None = None
    units_per_buy: float | None = Field(default=None, gt=0)
    yield_fraction: float = Field(default=1, gt=0, le=1)


class MoveIn(StrictModel):
    item_id: int
    quantity: float = Field(gt=0)
    from_zone: str = "Main store"
    to_zone: str = "Kitchen"
    note: str = ""


COST_KINDS = {
    "rent": "Rent",
    "gas": "Gas",
    "electricity": "Electricity",
    "water": "Water",
    "salaries": "Salaries",
    "other": "Other regular bills",
}
CADENCES = ("weekly", "monthly", "yearly")


class PriceLine(StrictModel):
    line_id: int
    cost_per_unit_kes: float = Field(ge=0)


class PriceIn(StrictModel):
    lines: list[PriceLine]


def ensure_zones(db: Session, restaurant_id: int) -> list[models.StockZone]:
    rows = (
        db.query(models.StockZone)
        .filter(models.StockZone.restaurant_id == restaurant_id)
        .order_by(models.StockZone.id.asc())
        .all()
    )
    if rows:
        return rows
    for name, kind in _ZONES:
        db.add(models.StockZone(restaurant_id=restaurant_id, name=name, kind=kind))
    db.flush()
    return (
        db.query(models.StockZone)
        .filter(models.StockZone.restaurant_id == restaurant_id)
        .order_by(models.StockZone.id.asc())
        .all()
    )


def _zone(db: Session, restaurant_id: int, name: str) -> models.StockZone:
    zones = ensure_zones(db, restaurant_id)
    found = next((zone for zone in zones if zone.name.lower() == name.strip().lower()), None)
    if found is None:
        raise HTTPException(status_code=400, detail=f"Unknown place: {name}")
    return found


def _balance(db, restaurant_id, item_id, zone_id) -> models.StockBalance:
    row = (
        db.query(models.StockBalance)
        .filter(
            models.StockBalance.inventory_item_id == item_id,
            models.StockBalance.zone_id == zone_id,
        )
        .first()
    )
    if row is None:
        row = models.StockBalance(
            restaurant_id=restaurant_id,
            inventory_item_id=item_id,
            zone_id=zone_id,
            quantity=0,
        )
        db.add(row)
        db.flush()
    return row


def _sync_total(db, item: models.InventoryItem) -> None:
    rows = db.query(models.StockBalance).filter(models.StockBalance.inventory_item_id == item.id).all()
    item.quantity = sum(row.quantity for row in rows)


def _photo_bytes(upload: UploadFile) -> tuple[bytes, str]:
    data = upload.file.read()
    if not data or len(data) > _MAX_PHOTO:
        raise HTTPException(status_code=400, detail="Each photo must be a file under 4 MB.")
    if data.startswith(b"\xff\xd8\xff"):
        return data, "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data, "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return data, "image/webp"
    raise HTTPException(status_code=400, detail="Use a JPEG, PNG, or WEBP photo.")


def _item_by_name(db, restaurant_id, name, unit) -> models.InventoryItem:
    found = (
        db.query(models.InventoryItem)
        .filter(
            models.InventoryItem.restaurant_id == restaurant_id,
            models.InventoryItem.item_name.ilike(name.strip()),
        )
        .first()
    )
    if found:
        return found
    found = models.InventoryItem(
        restaurant_id=restaurant_id,
        item_name=name.strip(),
        quantity=0,
        unit=unit,
        cost_per_unit=0,
        low_stock_threshold=0,
        expiry_days=30,
        yield_fraction=1,
    )
    db.add(found)
    db.flush()
    return found


def _supplier_out(row: models.Supplier) -> dict:
    arrival = row.arrival or ""
    return {
        "id": row.id,
        "name": row.name,
        "phone": row.contact_phone or "",
        "brings": row.brings or "",
        "arrival": arrival,
        "arrival_label": _ARRIVAL_LABELS.get(arrival, arrival),
    }


def _public_delivery(db, receipt: models.DeliveryReceipt, viewer: models.User) -> dict:
    supplier = db.query(models.Supplier).filter(models.Supplier.id == receipt.supplier_id).first()
    lines = (
        db.query(models.DeliveryReceiptLine)
        .filter(models.DeliveryReceiptLine.receipt_id == receipt.id)
        .order_by(models.DeliveryReceiptLine.id.asc())
        .all()
    )
    photos = (
        db.query(models.DeliveryEvidencePhoto)
        .filter(models.DeliveryEvidencePhoto.receipt_id == receipt.id)
        .order_by(models.DeliveryEvidencePhoto.id.asc())
        .all()
    )
    check = (
        db.query(models.DeliveryVisionCheck)
        .filter(models.DeliveryVisionCheck.receipt_id == receipt.id)
        .order_by(models.DeliveryVisionCheck.id.desc())
        .first()
    )
    payload = {
        "id": receipt.id,
        "supplier": supplier.name if supplier else None,
        "received_at": receipt.received_at.isoformat() if receipt.received_at else None,
        "status": receipt.status,
        "lines": [
            {"id": line.id, "item_name": line.item_name, "quantity": line.quantity, "unit": line.unit}
            for line in lines
        ],
        "photos": [{"id": photo.id, "kind": photo.kind} for photo in photos],
    }
    result = {}
    if check and check.result_json:
        try:
            result = json.loads(check.result_json)
        except json.JSONDecodeError:
            result = {}
    status = check.status if check else "pending"
    if can_see_prices(viewer):
        payload["ai"] = status
        payload["ai_label"] = "AI"
        if status == "unavailable":
            payload["ai_note"] = "AI check unavailable"
        elif result.get("note"):
            payload["ai_note"] = result["note"]
        if result.get("compare_fallback") and payload.get("ai_note"):
            payload["ai_note"] = f"{payload['ai_note']} Qwen wrote this after DeepSeek failed."
        if status == "mismatch":
            payload["mismatches"] = result.get("mismatches") or []
    else:
        payload["ai_label"] = "AI check unavailable" if status == "unavailable" else "AI"
        payload["ai"] = "unavailable" if status == "unavailable" else ("pending" if status == "pending" else "checked")
    return payload


@router.get("/suppliers")
async def list_store_suppliers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "suppliers")
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.Supplier)
        .filter(models.Supplier.restaurant_id == restaurant.id, models.Supplier.is_active.is_(True))
        .order_by(models.Supplier.name.asc())
        .all()
    )
    return [_supplier_out(row) for row in rows]


@router.post("/suppliers", status_code=201)
async def add_supplier(
    body: SupplierIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "suppliers")
    restaurant = get_or_create_restaurant(db, current_user)
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    arrival = body.arrival.strip()
    if arrival and arrival not in _ARRIVAL_LABELS:
        raise HTTPException(status_code=400, detail="Say how the supplies arrive: phone order, scheduled delivery, pickup, or other.")
    supplier = models.Supplier(
        restaurant_id=restaurant.id,
        name=body.name.strip(),
        contact_phone=normalize_phone(body.phone) if body.phone else "",
        brings=body.brings.strip(),
        arrival=arrival,
        notes="",
    )
    db.add(supplier)
    db.flush()
    record_entry(
        db, restaurant.id, user, "supplier_added", "supplier",
        f"{user.email} added supplier {supplier.name} ({supplier.brings}).",
        entity_id=supplier.id,
        detail={"brings": supplier.brings, "arrival": supplier.arrival},
    )
    db.commit()
    db.refresh(supplier)
    return _supplier_out(supplier)


@router.get("/zones")
async def list_zones(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    zones = ensure_zones(db, restaurant.id)
    db.commit()
    return [{"id": zone.id, "name": zone.name, "kind": zone.kind} for zone in zones]


@router.get("/items")
async def list_items(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_store_role(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    zones = ensure_zones(db, restaurant.id)
    db.commit()
    items = (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.restaurant_id == restaurant.id)
        .order_by(models.InventoryItem.item_name.asc())
        .all()
    )
    balances = db.query(models.StockBalance).filter(models.StockBalance.restaurant_id == restaurant.id).all()
    zone_name = {zone.id: zone.name for zone in zones}
    by_item: dict[int, list] = {}
    for row in balances:
        by_item.setdefault(row.inventory_item_id, []).append({
            "zone": zone_name.get(row.zone_id, ""),
            "quantity": row.quantity,
        })
    return {
        "zones": [{"id": zone.id, "name": zone.name, "kind": zone.kind} for zone in zones],
        "items": [
            {
                "id": item.id,
                "item_name": item.item_name,
                "quantity": item.quantity,
                "unit": item.unit,
                "buying_unit": item.buying_unit,
                "units_per_buy": item.units_per_buy,
                "yield_fraction": item.yield_fraction if item.yield_fraction is not None else 1,
                "zone": zone_name.get(item.zone_id),
                "balances": by_item.get(item.id, []),
            }
            for item in items
        ],
    }


@router.post("/items/opening", status_code=201)
async def opening_count(
    body: OpeningIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "opening-count")
    restaurant = get_or_create_restaurant(db, current_user)
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    zone = _zone(db, restaurant.id, body.zone)
    item = _item_by_name(db, restaurant.id, body.item_name, body.unit)
    already = (
        db.query(models.StockMovement)
        .filter(
            models.StockMovement.inventory_item_id == item.id,
            models.StockMovement.reason == "opening",
        )
        .first()
    )
    if already:
        raise HTTPException(status_code=409, detail="This item already has an opening count.")
    item.unit = body.unit
    item.buying_unit = body.buying_unit
    item.units_per_buy = body.units_per_buy
    item.yield_fraction = body.yield_fraction
    item.zone_id = zone.id
    bal = _balance(db, restaurant.id, item.id, zone.id)
    bal.quantity = body.quantity
    _sync_total(db, item)
    db.add(models.StockMovement(
        inventory_item_id=item.id,
        movement_type=models.StockMovementType.ADJUST,
        quantity=body.quantity,
        reason="opening",
        created_at=utcnow(),
        performed_by_user_id=user.id,
    ))
    record_entry(
        db, restaurant.id, user, "opening_count", "inventory_item",
        f"{user.email} counted {body.quantity} {body.unit} of {item.item_name} in {zone.name}.",
        entity_id=item.id,
        detail={"zone": zone.name, "buying_unit": body.buying_unit, "yield_fraction": body.yield_fraction},
    )
    db.commit()
    return {"id": item.id, "item_name": item.item_name, "quantity": item.quantity, "unit": item.unit, "zone": zone.name}


@router.post("/issue", status_code=201)
async def issue_to_kitchen(
    body: MoveIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "store-issue")
    restaurant = get_or_create_restaurant(db, current_user)
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    item = db.query(models.InventoryItem).filter(
        models.InventoryItem.id == body.item_id,
        models.InventoryItem.restaurant_id == restaurant.id,
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    source = _zone(db, restaurant.id, body.from_zone)
    dest = _zone(db, restaurant.id, body.to_zone)
    if dest.kind == "kitchen":
        raise HTTPException(status_code=400, detail="The chef confirms a handover.")
    origin = _balance(db, restaurant.id, item.id, source.id)
    if origin.quantity < body.quantity:
        raise HTTPException(status_code=400, detail=f"Only {origin.quantity} {item.unit} is in {source.name}.")
    origin.quantity -= body.quantity
    _balance(db, restaurant.id, item.id, dest.id).quantity += body.quantity
    _sync_total(db, item)
    db.add(models.StockMovement(
        inventory_item_id=item.id,
        movement_type=models.StockMovementType.OUT,
        quantity=body.quantity,
        reason="moved",
        created_at=utcnow(),
        performed_by_user_id=user.id,
    ))
    record_entry(
        db, restaurant.id, user, "stock_issued", "inventory_item",
        f"{user.email} issued {body.quantity} {item.unit} of {item.item_name} from {source.name} to {dest.name}.",
        entity_id=item.id,
    )
    db.commit()
    return {"item_name": item.item_name, "quantity": body.quantity, "unit": item.unit, "to_zone": dest.name}


def _sees_cost_amounts(user: models.User) -> bool:
    return user.role in (models.Role.SUPERADMIN, models.Role.ADMIN)


def _cost_public(row: models.RunningCost, viewer: models.User) -> dict:
    body = {
        "id": row.id,
        "kind": row.kind,
        "label": row.label,
        "cadence": row.cadence,
        "due_day": row.due_day,
        "status": row.status,
        "delegated_to": row.delegated_to,
        "has_receipt": bool(row.receipt_storage_key),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if _sees_cost_amounts(viewer) and row.status != "unknown":
        body["amount_cents"] = row.amount_cents
    elif row.status == "needs_approval":
        body["message"] = "Sent to the owner."
    elif row.status == "unknown":
        body["message"] = "Marked unknown."
    else:
        body["message"] = "With the owner."
    return body


@router.get("/costs")
async def list_costs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "running-costs")
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.RunningCost)
        .filter(models.RunningCost.restaurant_id == restaurant.id)
        .order_by(models.RunningCost.id.asc())
        .all()
    )
    payload = {"costs": [_cost_public(row, current_user) for row in rows]}
    if _sees_cost_amounts(current_user):
        payload["total_cents"] = sum(row.amount_cents for row in rows if row.status == "approved")
    return payload


@router.post("/costs", status_code=201)
async def add_cost(
    kind: str = Form(),
    label: str = Form(""),
    known: str = Form("yes"),
    amount_kes: float = Form(0),
    cadence: str = Form("monthly"),
    due_day: int | None = Form(None),
    delegate_to: str = Form(""),
    receipt: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "running-costs")
    if kind not in COST_KINDS:
        raise HTTPException(status_code=400, detail="Pick rent, gas, electricity, water, salaries, or other.")
    if cadence not in CADENCES:
        raise HTTPException(status_code=400, detail="Say how often: weekly, monthly, or yearly.")
    if due_day is not None and not 1 <= due_day <= 31:
        raise HTTPException(status_code=400, detail="The due day is from 1 to 31.")
    restaurant = get_or_create_restaurant(db, current_user)
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    cleaned = label.strip() or COST_KINDS[kind]
    is_known = known.strip().lower() in ("yes", "true", "1", "know")
    picture = None
    if receipt is not None and receipt.filename:
        picture = _photo_bytes(receipt)
    if is_known:
        if amount_kes <= 0:
            raise HTTPException(status_code=400, detail="Enter the amount.")
        status = "needs_approval"
        amount_cents = int(round(amount_kes * 100))
        delegated = None
    else:
        if delegate_to not in ("owner", "accountant", "storekeeper"):
            raise HTTPException(status_code=400, detail="Send the unknown bill to the owner or the other manager.")
        if user.staff_role == models.StaffRole.STOCKKEEPER and delegate_to == "storekeeper":
            raise HTTPException(status_code=400, detail="Send it to the accountant or the owner.")
        if user.staff_role == models.StaffRole.CONTROLLER and delegate_to == "accountant":
            raise HTTPException(status_code=400, detail="Send it to the storekeeper or the owner.")
        status = "unknown"
        amount_cents = 0
        delegated = delegate_to
    photo_key = None
    photo_type = None
    if picture:
        data, photo_type = picture
        photo_key = storage.save(data, content_type=photo_type)
    try:
        row = models.RunningCost(
            restaurant_id=restaurant.id,
            user_id=user.id,
            kind=kind,
            label=cleaned,
            amount_cents=amount_cents,
            cadence=cadence,
            due_day=due_day,
            receipt_storage_key=photo_key,
            receipt_content_type=photo_type,
            status=status,
            delegated_to=delegated,
            created_at=utcnow(),
        )
        db.add(row)
        db.flush()
        record_entry(
            db, restaurant.id, user, "running_cost_added", "running_cost",
            f"{user.email} answered {cleaned}."
            + (" The amount is with the owner." if is_known else f" They do not know it. Sent to the {delegated}."),
            entity_id=row.id,
            detail={"kind": kind, "status": status, "cadence": cadence},
        )
        db.commit()
    except Exception:
        db.rollback()
        if photo_key:
            storage.delete(photo_key)
        raise
    if status == "needs_approval":
        from routers.store_control import tell_owners
        tell_owners(db, user, restaurant, f"{cleaned} needs you", f"{cleaned} was sent for approval.")
    body = _cost_public(row, user)
    body["message"] = "Sent to the owner. You will not see the total." if is_known else "Marked unknown. The owner can see that."
    return body


@router.get("/deliveries")
async def list_deliveries(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "deliveries")
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.DeliveryReceipt)
        .filter(models.DeliveryReceipt.restaurant_id == restaurant.id)
        .order_by(models.DeliveryReceipt.id.desc())
        .limit(50)
        .all()
    )
    return [_public_delivery(db, row, current_user) for row in rows]


@router.post("/deliveries", status_code=201)
async def receive_delivery(
    background: BackgroundTasks,
    supplier_id: int = Form(),
    lines: str = Form(),
    invoice: UploadFile = File(),
    goods: list[UploadFile] = File(),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    require_module(db, current_user, "deliveries")
    restaurant = get_or_create_restaurant(db, current_user)
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    supplier = db.query(models.Supplier).filter(
        models.Supplier.id == supplier_id,
        models.Supplier.restaurant_id == restaurant.id,
    ).first()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    try:
        parsed = json.loads(lines)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Lines must be a JSON list.")
    if not isinstance(parsed, list) or not parsed:
        raise HTTPException(status_code=400, detail="Key at least one quantity.")
    if not goods:
        raise HTTPException(status_code=400, detail="Add a photo of the goods.")
    invoice_bytes, invoice_type = _photo_bytes(invoice)
    goods_photos = [_photo_bytes(upload) for upload in goods]
    zone = _zone(db, restaurant.id, "Main store")
    receipt = models.DeliveryReceipt(
        restaurant_id=restaurant.id,
        supplier_id=supplier.id,
        received_by_user_id=user.id,
        received_at=utcnow(),
        notes="",
        status="keyed",
    )
    db.add(receipt)
    db.flush()
    saved_keys = []
    try:
        for kind, data, content_type in [("invoice", invoice_bytes, invoice_type), *[("goods", data, content_type) for data, content_type in goods_photos]]:
            key = storage.save(data, content_type=content_type)
            saved_keys.append(key)
            db.add(models.DeliveryEvidencePhoto(
                receipt_id=receipt.id,
                kind=kind,
                storage_key=key,
                content_type=content_type,
                byte_size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                uploaded_by_user_id=user.id,
                uploaded_at=utcnow(),
            ))
        for raw in parsed:
            name = str(raw.get("item_name") or "").strip()
            unit = str(raw.get("unit") or "").strip()
            try:
                quantity = float(raw.get("quantity"))
            except (TypeError, ValueError):
                quantity = 0
            if not name or not unit or quantity <= 0:
                raise HTTPException(status_code=400, detail="Each line needs a name, a unit, and a quantity.")
            if "cost" in raw or "price" in raw:
                raise HTTPException(status_code=422, detail="Prices are not entered by this role.")
            item = _item_by_name(db, restaurant.id, name, unit)
            item.zone_id = item.zone_id or zone.id
            bal = _balance(db, restaurant.id, item.id, zone.id)
            bal.quantity += quantity
            _sync_total(db, item)
            db.add(models.StockMovement(
                inventory_item_id=item.id,
                movement_type=models.StockMovementType.IN,
                quantity=quantity,
                reason="delivery",
                created_at=utcnow(),
                performed_by_user_id=user.id,
            ))
            db.add(models.DeliveryReceiptLine(
                receipt_id=receipt.id,
                inventory_item_id=item.id,
                item_name=item.item_name,
                quantity=quantity,
                unit=unit,
                keyed_by_user_id=user.id,
                keyed_at=utcnow(),
            ))
        db.add(models.DeliveryVisionCheck(receipt_id=receipt.id, status="pending", created_at=utcnow()))
        record_entry(
            db, restaurant.id, user, "delivery_received", "delivery_receipt",
            f"{user.email} received a delivery from {supplier.name}.",
            entity_id=receipt.id,
            detail={"lines": len(parsed), "photos": 1 + len(goods_photos)},
        )
        db.commit()
    except Exception:
        db.rollback()
        for key in saved_keys:
            storage.delete(key)
        raise
    background.add_task(run_check_safe, receipt.id)
    from ai.notify import notify_users
    owners = db.query(models.User).filter(
        models.User.tenant_id == user.tenant_id,
        models.User.role.in_((models.Role.ADMIN, models.Role.SUPERADMIN)),
        models.User.is_active.is_(True),
    ).all()
    if owners:
        notify_users(
            db, [owner.id for owner in owners],
            "Delivery received",
            f"{user.email} keyed a delivery from {supplier.name}.",
            "staff.delivery",
            url="/eleven/deliveries",
        )
    return _public_delivery(db, receipt, user)


@router.get("/deliveries/{receipt_id}/photos/{photo_id}")
async def delivery_photo(
    receipt_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    photo = (
        db.query(models.DeliveryEvidencePhoto)
        .join(models.DeliveryReceipt, models.DeliveryReceipt.id == models.DeliveryEvidencePhoto.receipt_id)
        .filter(
            models.DeliveryEvidencePhoto.id == photo_id,
            models.DeliveryEvidencePhoto.receipt_id == receipt_id,
            models.DeliveryReceipt.restaurant_id == restaurant.id,
        )
        .first()
    )
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    allowed = can_see_prices(current_user) or photo.uploaded_by_user_id == current_user.id
    if not allowed:
        raise HTTPException(status_code=403, detail="Insufficient permissions for this action")
    if photo.storage_key.startswith("http"):
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(content=storage.load(photo.storage_key), media_type=photo.content_type)


@router.post("/deliveries/{receipt_id}/prices")
async def confirm_prices(
    receipt_id: int,
    body: PriceIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not can_see_prices(current_user):
        raise HTTPException(status_code=403, detail="Prices are confirmed by the owner.")
    restaurant = get_or_create_restaurant(db, current_user)
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    receipt = db.query(models.DeliveryReceipt).filter(
        models.DeliveryReceipt.id == receipt_id,
        models.DeliveryReceipt.restaurant_id == restaurant.id,
    ).first()
    if receipt is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    updated = 0
    for entry in body.lines:
        line = db.query(models.DeliveryReceiptLine).filter(
            models.DeliveryReceiptLine.id == entry.line_id,
            models.DeliveryReceiptLine.receipt_id == receipt.id,
        ).first()
        if line is None or line.inventory_item_id is None:
            raise HTTPException(status_code=404, detail="Line not found")
        item = db.query(models.InventoryItem).filter(models.InventoryItem.id == line.inventory_item_id).first()
        item.cost_per_unit = entry.cost_per_unit_kes
        updated += 1
    record_entry(
        db, restaurant.id, user, "delivery_price_confirmed", "delivery_receipt",
        f"{user.email} confirmed prices on delivery {receipt.id} from the invoice.",
        entity_id=receipt.id,
        detail={"lines": updated},
    )
    db.commit()
    return {"updated": updated}
