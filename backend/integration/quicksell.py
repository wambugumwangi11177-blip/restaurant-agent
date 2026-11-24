"""QuickSell POS webhook: mirror anything; map only recognised sales to orders."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

import models
from integration.ingest import payload_sha256

_ID_KEYS = (
    "source_id", "id", "transaction_id", "txn_id", "invoice_no", "invoice_number",
    "receipt_no", "receipt_number", "sale_id", "order_id", "doc_no", "reference", "ref",
)
_TIME_KEYS = (
    "occurred_at", "sold_at", "timestamp", "created_at", "transaction_time", "date_time",
)
_VERSION_KEYS = ("source_version", "version", "rowversion", "revision", "updated_at")
_TOTAL_KEYS = ("total_cents", "total", "amount_cents", "amount", "grand_total")

_SALE_ENTITIES = frozenset({
    "sale", "sales", "order", "orders", "transaction", "transactions", "receipt", "receipts",
})
_NON_SALE_ENTITIES = frozenset({
    "stock", "inventory", "item", "items", "staff", "employee", "menu", "product", "payment",
})

EAT = timezone(timedelta(hours=3))
NOTES_PREFIX = "quicksell:"

_LINE_KEYS = ("lines", "items", "line_items", "products", "order_lines")
_QTY_KEYS = ("quantity", "qty", "count")
_PRICE_KEYS = ("unit_price_cents", "price_cents", "unit_price", "price")
_ID_KEYS_LINE = ("menu_item_id", "product_id", "dish_id", "item_id", "sku")
_NAME_KEYS = ("name", "dish_name", "product_name", "item_name", "title")


def first_present(record: dict, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = record.get(k)
        if v is None:
            continue
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
    return None


def source_id_for(record: dict) -> tuple[str, bool]:
    """(source_id, derived_from_hash)."""
    sid = first_present(record, _ID_KEYS)
    if sid:
        return sid, False
    digest = payload_sha256(record)
    return f"sha256:{digest}", True


def parse_timestamp(record: dict, received_at: datetime) -> datetime:
    """UTC-naive instant for storage. Naive strings → Africa/Nairobi; missing → received_at."""
    raw = first_present(record, _TIME_KEYS)
    if not raw:
        return received_at
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return received_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EAT)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def nairobi_business_day(utc_naive: datetime) -> str:
    aware = utc_naive.replace(tzinfo=timezone.utc)
    return aware.astimezone(EAT).date().isoformat()


def source_version_for(record: dict, utc_naive: datetime) -> str:
    explicit = first_present(record, _VERSION_KEYS)
    if explicit:
        return explicit
    return payload_sha256(record)


def total_cents_optional(record: dict) -> int | None:
    for k in _TOTAL_KEYS:
        if k not in record:
            continue
        v = record[k]
        if v is None:
            continue
        if isinstance(v, bool):
            raise ValueError("Invalid sale total")
        try:
            amount = Decimal(str(v))
            if not amount.is_finite():
                raise ValueError("Invalid sale total")
            cents = amount if k.endswith("_cents") else amount * 100
            if k.endswith("_cents") and cents != cents.to_integral_value():
                raise ValueError("Fractional cents are not supported")
            result = int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if result < 0 or result > 2_147_483_647:
                raise ValueError("Sale total needs review")
            return result
        except (InvalidOperation, OverflowError):
            raise ValueError("Invalid sale total")
    return None


def is_mappable_sale(record: dict, entity: str) -> bool:
    if total_cents_optional(record) is None:
        return False
    ent = (entity or "unknown").lower()
    if ent in _NON_SALE_ENTITIES:
        return False
    if ent in _SALE_ENTITIES:
        return True
    return ent in ("unknown", "envelope")


def _actor_user_id(db: Session, restaurant_id: int) -> int:
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    if not restaurant:
        return 1
    owner = (
        db.query(models.User)
        .filter(
            models.User.tenant_id == restaurant.tenant_id,
            models.User.role == models.Role.ADMIN,
        )
        .order_by(models.User.id.asc())
        .first()
    )
    return owner.id if owner else 1


def _lines_raw(record: dict) -> list[dict] | None:
    for key in _LINE_KEYS:
        value = record.get(key)
        if isinstance(value, list) and value:
            return [row for row in value if isinstance(row, dict)]
    return None


def _quantity_of(line: dict) -> float | None:
    for key in _QTY_KEYS:
        if key not in line:
            continue
        try:
            qty = float(line[key])
            if qty > 0:
                return qty
        except (TypeError, ValueError):
            continue
    return None


def _unit_price_cents(line: dict, menu_item: models.MenuItem | None) -> int:
    for key in _PRICE_KEYS:
        if key not in line or line[key] is None:
            continue
        try:
            amount = Decimal(str(line[key]))
            if key.endswith("_cents"):
                return int(amount)
            return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError):
            continue
    return int(menu_item.price) if menu_item and menu_item.price else 0


def _resolve_menu_item(db: Session, restaurant_id: int, line: dict) -> models.MenuItem | None:
    for key in _ID_KEYS_LINE:
        if key not in line or line[key] is None:
            continue
        try:
            mid = int(line[key])
        except (TypeError, ValueError):
            if key == "sku":
                name = str(line[key]).strip()
                if name:
                    return (
                        db.query(models.MenuItem)
                        .filter(
                            models.MenuItem.restaurant_id == restaurant_id,
                            models.MenuItem.name.ilike(name),
                        )
                        .first()
                    )
            continue
        hit = (
            db.query(models.MenuItem)
            .filter(models.MenuItem.restaurant_id == restaurant_id, models.MenuItem.id == mid)
            .first()
        )
        if hit:
            return hit
    for key in _NAME_KEYS:
        name = line.get(key)
        if not name or not str(name).strip():
            continue
        hit = (
            db.query(models.MenuItem)
            .filter(
                models.MenuItem.restaurant_id == restaurant_id,
                models.MenuItem.name.ilike(str(name).strip()),
            )
            .first()
        )
        if hit:
            return hit
    return None


def _parsed_order_lines(db: Session, restaurant_id: int, record: dict) -> list[tuple[models.MenuItem, float, int]]:
    raw = _lines_raw(record)
    if not raw:
        return []
    out: list[tuple[models.MenuItem, float, int]] = []
    for line in raw:
        qty = _quantity_of(line)
        if qty is None:
            continue
        menu_item = _resolve_menu_item(db, restaurant_id, line)
        if not menu_item:
            continue
        out.append((menu_item, qty, _unit_price_cents(line, menu_item)))
    return out


def _sync_order_lines(db: Session, restaurant_id: int, order: models.Order, record: dict) -> None:
    parsed = _parsed_order_lines(db, restaurant_id, record)
    if not parsed:
        return
    from ai.order_stock import deduct_ingredients_for_order, reverse_ingredients_for_order

    actor = _actor_user_id(db, restaurant_id)
    if order.id and order.items:
        reverse_ingredients_for_order(db, order, actor)
    db.query(models.OrderItem).filter(models.OrderItem.order_id == order.id).delete(synchronize_session=False)
    for menu_item, qty, unit_price in parsed:
        db.add(
            models.OrderItem(
                order_id=order.id,
                menu_item_id=menu_item.id,
                quantity=max(1, int(round(qty))),
                unit_price=unit_price,
            )
        )
    db.flush()
    db.refresh(order)
    deduct_ingredients_for_order(db, order, actor)


def _find_order(db: Session, restaurant_id: int, source_id: str) -> models.Order | None:
    note = f"{NOTES_PREFIX}{source_id}"
    return (
        db.query(models.Order)
        .filter(models.Order.restaurant_id == restaurant_id, models.Order.notes == note)
        .order_by(models.Order.id.desc())
        .first()
    )


def maybe_apply_sale(
    db: Session,
    *,
    restaurant_id: int,
    entity: str,
    source_id: str,
    ingest_action: str,
    record: dict,
    occurred_at: datetime,
) -> str:
    if ingest_action == "skipped" or not is_mappable_sale(record, entity):
        return "order_unchanged"

    cents = total_cents_optional(record)
    if cents is None:
        return "order_unchanged"

    existing = _find_order(db, restaurant_id, source_id)

    if existing is not None:
        existing.total = cents
        existing.created_at = occurred_at
        existing.is_paid = True
        if _lines_raw(record):
            _sync_order_lines(db, restaurant_id, existing, record)
        return "order_updated"

    if ingest_action in ("inserted", "superseded"):
        order = models.Order(
            restaurant_id=restaurant_id,
            status=models.OrderStatus.SERVED,
            order_type=models.OrderType.DINE_IN,
            is_paid=True,
            total=cents,
            notes=f"{NOTES_PREFIX}{source_id}",
            created_at=occurred_at,
        )
        db.add(order)
        db.flush()
        if _lines_raw(record):
            _sync_order_lines(db, restaurant_id, order, record)
        return "order_inserted"

    return "order_unchanged"


def normalize_payload(payload: Any) -> tuple[str, list[dict]]:
    """Turn any JSON value into (entity, list of dict records) for mirroring."""
    entity = "unknown"
    records = []
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        entity = str(payload.get("entity") or payload.get("type") or "unknown").strip() or "unknown"
        records = [payload]
        for key in ("records", "data", "items", "rows", "transactions", "sales"):
            if isinstance(payload.get(key), list):
                records = payload[key]
                break
    else:
        records = [{"_value": payload}]
    out: list[dict] = []
    for r in records:
        if isinstance(r, dict):
            out.append(r)
        else:
            out.append({"_value": r})
    if out:
        return entity, out

    if isinstance(payload, dict):
        ent = str(payload.get("entity") or payload.get("type") or "envelope").strip() or "envelope"
        return ent, [payload]
    if isinstance(payload, list):
        return "envelope", [{"_value": x} for x in payload] if payload else [{"_empty": True}]
    return "envelope", [{"_value": payload}]
