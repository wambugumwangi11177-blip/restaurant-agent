"""QuickSell POS webhook: mirror anything; map only recognised sales to orders."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
        if k.endswith("_cents") or k in ("amount_cents",):
            return int(v)
        return int(round(float(v) * 100))
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
        return "order_inserted"

    return "order_unchanged"


def normalize_payload(payload: Any) -> tuple[str, list[dict]]:
    """Turn any JSON value into (entity, list of dict records) for mirroring."""
    from integration.payload_parse import records_from

    entity, records = records_from(payload if isinstance(payload, (dict, list)) else {"_value": payload})
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
