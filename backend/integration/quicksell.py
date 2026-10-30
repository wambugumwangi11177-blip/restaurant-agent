"""QuickSell POS webhook: parse payloads and map mirrored sales to orders (Eleven)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

import models

_ID_KEYS = (
    "source_id", "id", "transaction_id", "txn_id", "invoice_no", "invoice_number",
    "receipt_no", "receipt_number", "sale_id", "order_id", "doc_no", "reference", "ref",
)
_TIME_KEYS = (
    "occurred_at", "sold_at", "timestamp", "created_at", "transaction_time", "date_time",
)
_VERSION_KEYS = ("source_version", "version", "rowversion", "revision", "updated_at")
_TOTAL_KEYS = ("total_cents", "total", "amount_cents", "amount", "grand_total")

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


def require_source_id(record: dict) -> str:
    sid = first_present(record, _ID_KEYS)
    if not sid:
        raise ValueError("Each record must include a unique id (e.g. source_id, receipt_no, transaction_id).")
    return sid


def parse_timestamp(record: dict) -> datetime:
    raw = first_present(record, _TIME_KEYS)
    if not raw:
        raise ValueError("Each record must include a timestamp with timezone offset (e.g. occurred_at).")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Timestamp must be ISO-8601 with timezone offset.") from exc
    if dt.tzinfo is None:
        raise ValueError("Timestamp must include a timezone offset, not naive local time.")
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def nairobi_business_day(utc_naive: datetime) -> str:
    """Calendar date in Africa/Nairobi for the instant stored on the order."""
    aware = utc_naive.replace(tzinfo=timezone.utc)
    return aware.astimezone(EAT).date().isoformat()


def source_version_for(record: dict, utc_naive: datetime) -> str:
    explicit = first_present(record, _VERSION_KEYS)
    if explicit:
        return explicit
    return utc_naive.isoformat(timespec="seconds")


def total_cents(record: dict) -> int:
    for k in _TOTAL_KEYS:
        if k not in record:
            continue
        v = record[k]
        if v is None:
            continue
        if k.endswith("_cents") or k in ("amount_cents",):
            return int(v)
        # Major currency units → cents
        return int(round(float(v) * 100))
    raise ValueError("Each record must include a total (total_cents or total).")


def _find_order(db: Session, restaurant_id: int, source_id: str) -> models.Order | None:
    note = f"{NOTES_PREFIX}{source_id}"
    return (
        db.query(models.Order)
        .filter(models.Order.restaurant_id == restaurant_id, models.Order.notes == note)
        .order_by(models.Order.id.desc())
        .first()
    )


def apply_sale(
    db: Session,
    *,
    restaurant_id: int,
    source_id: str,
    ingest_action: str,
    record: dict,
    occurred_at: datetime,
) -> str:
    """Create or update an order row when mirror ingest accepted the sale."""
    if ingest_action == "skipped":
        return "order_unchanged"

    cents = total_cents(record)
    existing = _find_order(db, restaurant_id, source_id)

    if ingest_action == "inserted" and existing is None:
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

    if existing is not None:
        existing.total = cents
        existing.created_at = occurred_at
        existing.is_paid = True
        return "order_updated"

    if ingest_action == "inserted":
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
