"""Mirror → domain projection for pushed source-system data.

WHY THIS EXISTS
integration/ingest.py lands every pushed record in the mirror as a MirrorEvent
and stops. That was a deliberate deferral (see routers/webhooks.py's block
comment): MacSoft's export format had not been seen, and the owner's promise to
them was that we adapt to whatever they emit. The cost of the deferral was never
visible from outside, though — a push returned 200, the mirror row count rose,
and the owner's Home page showed the same numbers as the day before, because
every agent reads models.Order / MenuItem / InventoryItem and the mirror is a
separate declarative base. This module is the missing layer.

WHAT IT GUARANTEES
  * Idempotent. One ProjectionLink per (source_system, entity, source_id); a
    re-project updates the linked domain row rather than inserting a second.
  * Re-runnable. reproject_all() replays the whole mirror through the current
    mapping. That is the property that makes shipping before seeing a real
    payload safe: when MacSoft's field names are known, widen the key lists
    below and re-run — nothing is lost, because the mirror is the source of
    truth and it is append-only.
  * Never destructive on a bad guess. A record whose required fields do not
    resolve is recorded as `unmapped` with the reason, not forced into a row.
    Unmapped counts and reasons are surfaced by GET /webhooks/macsoft/status.
  * Never breaks ingest. project_batch() runs after the mirror is committed,
    in its own transaction. A projection bug loses a projection, not a record.

WHAT IT DOES NOT DO
  It does not guess the money unit. A 100x error in revenue is worse than no
  revenue, so the unit is read from MACSOFT_MONEY_UNIT (shillings|cents),
  defaults to shillings because Kenyan POS exports quote KES with two decimals,
  and is echoed by the status endpoint so it can be checked against a real
  invoice on day one.

CONFIGURATION IS READ AT CALL TIME, NOT IMPORT
  money_unit() and the restaurant resolution below read os.environ when they
  run. Import-time constants would force anything wanting to change them —
  a test, a future config endpoint — to reload this module, and reloading a
  module that routers/webhooks.py has already bound its handlers to leaves the
  app holding stale function objects. Found the hard way: it broke two unrelated
  M-Pesa tests.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from integration.models import MirrorEvent, ProjectionLink

logger = logging.getLogger(__name__)

DEFAULT_TENANT_NAME = "Vibanda Village"


def money_unit() -> str:
    """'shillings' or 'cents'. Explicit, never inferred — see the module note."""
    unit = (os.getenv("MACSOFT_MONEY_UNIT") or "shillings").strip().lower()
    return unit if unit in ("shillings", "cents") else "shillings"


# ── Field resolution ─────────────────────────────────────────────────────────
# Same philosophy as webhooks.py's _ID_KEYS: MacSoft renames nothing, we accept
# what they already emit, most explicit name first. Widening these once a real
# payload has been seen is the one change reproject_all() exists for.
_NAME_KEYS = ("name", "item_name", "product_name", "description", "item", "product", "title")
_PRICE_KEYS = ("price", "unit_price", "sale_price", "selling_price", "rate")
_COST_KEYS = ("cost_price", "cost", "unit_cost", "buying_price", "purchase_price")
_TOTAL_KEYS = ("total", "total_amount", "grand_total", "net_amount", "amount", "value")
_QTY_KEYS = ("quantity", "qty", "stock", "stock_level", "on_hand", "balance", "count")
_UNIT_KEYS = ("unit", "uom", "unit_of_measure", "measure")
_CATEGORY_KEYS = ("category", "group", "item_group", "department", "class")
_DATE_KEYS = ("created_at", "date", "transaction_date", "sale_date", "invoice_date",
              "occurred_at", "timestamp", "datetime", "posted_at")
_PAYMENT_KEYS = ("payment_method", "payment", "tender", "tender_type", "pay_mode", "mode")

_PAYMENT_VALUES = {
    "cash": "CASH", "mpesa": "MPESA", "m-pesa": "MPESA", "mobile": "MPESA",
    "mobile money": "MPESA", "card": "CARD", "visa": "CARD", "mastercard": "CARD",
    "credit": "CARD", "debit": "CARD",
}

# Entity names MacSoft might use for each domain concept.
_ENTITY_ALIASES = {
    "order": {"order", "orders", "sale", "sales", "transaction", "transactions",
              "invoice", "invoices", "receipt", "receipts", "bill", "bills"},
    "menu_item": {"menu_item", "menu_items", "menu", "product", "products",
                  "item", "items", "dish", "dishes", "sku", "skus"},
    "inventory_item": {"inventory_item", "inventory_items", "inventory", "stock",
                       "stock_item", "stock_items", "ingredient", "ingredients"},
}


def _first(record: dict, keys) -> Any:
    """First key in `keys` present on `record` with a usable value."""
    for k in keys:
        if k in record and record[k] is not None:
            v = record[k]
            if isinstance(v, str) and not v.strip():
                continue
            return v
    return None


def _to_cents(value: Any) -> int | None:
    """Money in the configured unit -> integer cents. None if unusable.

    Refuses negatives rather than clamping. Every money column in models.py
    carries a `>= 0` CheckConstraint, so a negative would raise at flush and
    take the batch's transaction with it; clamping to zero would quietly record
    a refund as a zero-value sale. Refusing means the record is reported as
    unmapped, with the reason, and can be re-projected once handled properly.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if num < 0:
        return None
    return int(round(num * 100)) if money_unit() == "shillings" else int(round(num))


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _to_datetime(value: Any) -> datetime | None:
    """Parse the common export date shapes. An unknown shape returns None and
    the caller falls back to the arrival time rather than dropping the record:
    an order with the wrong minute still counts as revenue; one that never
    lands does not."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S",
                    "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def classify(entity: str, record: dict) -> str | None:
    """Which domain concept a record is, or None if it cannot be told.

    The envelope's `entity` wins when recognisable. The shape fallback is
    deliberately conservative: an unrecognised shape returns None and the record
    is recorded as unmapped, because writing a stock count into the orders table
    is worse than writing nothing.
    """
    raw = (entity or "").strip().lower()
    for concept, aliases in _ENTITY_ALIASES.items():
        if raw in aliases or raw.rstrip("s") in aliases:
            return concept
    if _first(record, _TOTAL_KEYS) is not None and _first(record, _PRICE_KEYS) is None:
        return "order"
    if _first(record, _QTY_KEYS) is not None and _first(record, _UNIT_KEYS) is not None:
        return "inventory_item"
    if _first(record, _PRICE_KEYS) is not None and _first(record, _NAME_KEYS) is not None:
        return "menu_item"
    return None


def resolve_restaurant_id(db: Session) -> tuple[int | None, str | None]:
    """(restaurant_id, reason_if_none). Explicit config wins; otherwise the sole
    restaurant of the configured tenant. Ambiguity is never resolved by picking
    one: a day of sales attached to the wrong restaurant is silent and
    unrecoverable, so it is refused and reported."""
    import models

    configured = (os.getenv("MACSOFT_RESTAURANT_ID") or "").strip()
    if configured:
        try:
            rid = int(configured)
        except ValueError:
            return None, f"MACSOFT_RESTAURANT_ID is not an integer: {configured!r}"
        exists = db.query(models.Restaurant.id).filter(models.Restaurant.id == rid).first()
        return (rid, None) if exists else (None, f"MACSOFT_RESTAURANT_ID={rid} does not exist")

    tenant_name = (os.getenv("MACSOFT_TENANT_NAME") or DEFAULT_TENANT_NAME).strip()
    tenant = db.query(models.Tenant).filter(models.Tenant.name == tenant_name).first()
    if tenant is None:
        return None, f"no tenant named {tenant_name!r}; set MACSOFT_RESTAURANT_ID"
    rows = db.query(models.Restaurant.id).filter(
        models.Restaurant.tenant_id == tenant.id).all()
    if len(rows) == 1:
        return rows[0][0], None
    if not rows:
        return None, f"tenant {tenant_name!r} has no restaurant"
    return None, (f"tenant {tenant_name!r} has {len(rows)} restaurants; "
                  "set MACSOFT_RESTAURANT_ID to disambiguate")


# ── Projectors ───────────────────────────────────────────────────────────────
# Each returns (domain_table, domain_id) or raises _Unmappable with the reason.
# They take the linked row when one exists, so a correction updates in place.
# None of them delete: a source-side deletion is not represented in a push-only
# feed, and inventing one here would silently destroy history.

class _Unmappable(Exception):
    """A record that cannot become a domain row, carrying why."""


def _project_menu_item(db: Session, rid: int, record: dict, existing):
    import models

    name = _first(record, _NAME_KEYS)
    if not name:
        raise _Unmappable("no recognisable name field")
    price_cents = _to_cents(_first(record, _PRICE_KEYS))
    if price_cents is None:
        raise _Unmappable("no parseable non-negative price")

    row = existing
    if row is None:
        # Match by name before creating: the owner's menu already exists, and
        # MacSoft pushing it again must not produce a second copy of every dish.
        row = db.query(models.MenuItem).filter(
            models.MenuItem.restaurant_id == rid,
            models.MenuItem.name == str(name).strip(),
        ).first()
    if row is None:
        row = models.MenuItem(restaurant_id=rid, name=str(name).strip())
        db.add(row)

    row.name = str(name).strip()
    row.price = price_cents
    cost = _to_cents(_first(record, _COST_KEYS))
    if cost is not None:
        # Only a known cost overwrites a known cost. A push that omits
        # cost_price must not zero it: ai/profit/intelligence.py:181 reads a
        # zero cost as a 100% margin and :204 excludes it from leak detection,
        # so the dish would be reported as the best performer on the menu.
        row.cost_price = cost
    category = _first(record, _CATEGORY_KEYS)
    if category:
        row.category = str(category).strip()
    db.flush()
    return "menu_items", row.id


def _project_inventory_item(db: Session, rid: int, record: dict, existing):
    import models

    name = _first(record, _NAME_KEYS)
    if not name:
        raise _Unmappable("no recognisable item name")
    qty = _to_float(_first(record, _QTY_KEYS))
    if qty is None:
        raise _Unmappable("no parseable quantity")

    row = existing
    if row is None:
        row = db.query(models.InventoryItem).filter(
            models.InventoryItem.restaurant_id == rid,
            models.InventoryItem.item_name == str(name).strip(),
        ).first()
    if row is None:
        row = models.InventoryItem(
            restaurant_id=rid, item_name=str(name).strip(),
            unit=str(_first(record, _UNIT_KEYS) or "unit"),
            low_stock_threshold=0,
        )
        db.add(row)

    row.item_name = str(name).strip()
    row.quantity = qty
    unit = _first(record, _UNIT_KEYS)
    if unit:
        row.unit = str(unit).strip()
    cost = _to_cents(_first(record, _COST_KEYS))
    if cost is not None:
        row.cost_per_unit_cents = cost
    db.flush()
    return "inventory_items", row.id


def _project_order(db: Session, rid: int, record: dict, existing, arrived_at: datetime):
    import models

    total_cents = _to_cents(_first(record, _TOTAL_KEYS))
    if total_cents is None:
        raise _Unmappable("no parseable non-negative total")

    row = existing
    if row is None:
        row = models.Order(restaurant_id=rid)
        db.add(row)

    row.total = total_cents
    row.created_at = _to_datetime(_first(record, _DATE_KEYS)) or arrived_at
    # A record arriving from the POS is a completed sale, not a pending ticket.
    # SERVED and paid is what makes it count: every agent's revenue basis is
    # paid, non-cancelled orders (routers/overview.py's revenue_basis).
    row.status = models.OrderStatus.SERVED
    row.is_paid = True
    if row.completed_at is None:
        row.completed_at = row.created_at

    tender = _first(record, _PAYMENT_KEYS)
    if tender:
        mapped = _PAYMENT_VALUES.get(str(tender).strip().lower())
        if mapped:
            row.payment_method = getattr(models.PaymentMethod, mapped)
    db.flush()
    return "orders", row.id


_DOMAIN_MODELS = {
    "orders": "Order",
    "menu_items": "MenuItem",
    "inventory_items": "InventoryItem",
}


def _existing_row(db: Session, link):
    """The domain row a previous projection created, if it still exists."""
    if link is None or link.domain_table is None or link.domain_id is None:
        return None
    import models
    model = getattr(models, _DOMAIN_MODELS.get(link.domain_table, ""), None)
    if model is None:
        return None
    return db.query(model).filter(model.id == link.domain_id).first()


# ── Batch driver ─────────────────────────────────────────────────────────────

def project_batch(
    db: Session,
    *,
    source_system_id: int,
    entity: str,
    records: list[tuple[str, str, dict]],
    arrived_at: datetime | None = None,
) -> dict:
    """Project one push batch. `records` is [(source_id, source_version, payload)].

    Returns counts, never raises. Commits its own transaction: the mirror rows
    are already committed by the caller and remain the source of truth, which
    is what lets a later reproject_all() recover anything this pass got wrong.
    """
    arrived_at = arrived_at or datetime.utcnow()
    out = {"projected": 0, "updated": 0, "unmapped": 0, "unchanged": 0,
           "by_table": {}, "reasons": {}}

    rid, why = resolve_restaurant_id(db)
    if rid is None:
        reason = why or "restaurant unresolved"
        out["unmapped"] = len(records)
        out["reasons"][reason] = len(records)
        for source_id, source_version, _payload in records:
            _upsert_link(db, None, source_system_id, entity, source_id,
                         status="unmapped", reason=reason,
                         version=source_version, table=None, domain_id=None)
        _safe_commit(db)
        return out

    for source_id, source_version, payload in records:
        link = _find_link(db, source_system_id, entity, source_id)
        if (link is not None and link.status == "projected"
                and link.projected_version == source_version):
            out["unchanged"] += 1
            continue

        concept = classify(entity, payload)
        try:
            if concept is None:
                raise _Unmappable("could not classify as order, menu item or inventory")
            existing = _existing_row(db, link)
            if concept == "order":
                table, dom_id = _project_order(db, rid, payload, existing, arrived_at)
            elif concept == "menu_item":
                table, dom_id = _project_menu_item(db, rid, payload, existing)
            else:
                table, dom_id = _project_inventory_item(db, rid, payload, existing)
        except _Unmappable as exc:
            reason = str(exc)
            out["unmapped"] += 1
            out["reasons"][reason] = out["reasons"].get(reason, 0) + 1
            _upsert_link(db, link, source_system_id, entity, source_id,
                         status="unmapped", reason=reason,
                         version=source_version, table=None, domain_id=None)
            continue
        except Exception as exc:  # noqa: BLE001 — one bad record never sinks a batch
            logger.warning("[projection] %s/%s failed: %s", entity, source_id, exc)
            reason = f"projector error: {type(exc).__name__}"
            out["unmapped"] += 1
            out["reasons"][reason] = out["reasons"].get(reason, 0) + 1
            db.rollback()
            _upsert_link(db, None, source_system_id, entity, source_id,
                         status="unmapped", reason=reason,
                         version=source_version, table=None, domain_id=None)
            continue

        if link is not None and link.status == "projected":
            out["updated"] += 1
        else:
            out["projected"] += 1
        out["by_table"][table] = out["by_table"].get(table, 0) + 1
        _upsert_link(db, link, source_system_id, entity, source_id,
                     status="projected", reason=None, version=source_version,
                     table=table, domain_id=dom_id)

    if not _safe_commit(db):
        return {"projected": 0, "updated": 0, "unmapped": len(records),
                "unchanged": 0, "by_table": {},
                "reasons": {"projection commit failed": len(records)}}
    return out


def _safe_commit(db: Session) -> bool:
    try:
        db.commit()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("[projection] commit failed — the mirror is unaffected")
        db.rollback()
        return False


def _find_link(db: Session, source_system_id: int, entity: str, source_id: str):
    return db.query(ProjectionLink).filter(
        ProjectionLink.source_system_id == source_system_id,
        ProjectionLink.entity == entity,
        ProjectionLink.source_id == source_id,
    ).first()


def _upsert_link(db, link, source_system_id, entity, source_id, *,
                 status, reason, version, table, domain_id) -> None:
    if link is None:
        link = _find_link(db, source_system_id, entity, source_id)
    if link is None:
        link = ProjectionLink(source_system_id=source_system_id, entity=entity,
                              source_id=source_id)
        db.add(link)
    link.status = status
    link.reason = reason
    link.projected_version = version
    link.projected_at = datetime.utcnow()
    if table is not None:
        link.domain_table = table
        link.domain_id = domain_id
    db.flush()


def reproject_all(db: Session, source_system_id: int, batch_size: int = 500) -> dict:
    """Replay every mirrored record through the current mapping.

    Run this after widening the key lists above, once MacSoft's real field names
    are known. Safe to run repeatedly: records already projected against the
    same version are skipped and the rest update in place.

    Only the latest kept action per record is replayed — a superseded version is
    history, and re-applying it would undo the correction that replaced it.
    """
    from sqlalchemy import func

    latest = (
        db.query(MirrorEvent.entity, MirrorEvent.source_id,
                 func.max(MirrorEvent.id).label("max_id"))
        .filter(MirrorEvent.source_system_id == source_system_id,
                MirrorEvent.action.in_(("inserted", "superseded")))
        .group_by(MirrorEvent.entity, MirrorEvent.source_id)
        .all()
    )
    ids = [row.max_id for row in latest]
    totals = {"projected": 0, "updated": 0, "unmapped": 0, "unchanged": 0,
              "by_table": {}, "reasons": {}, "considered": len(ids)}

    for start in range(0, len(ids), batch_size):
        chunk = db.query(MirrorEvent).filter(
            MirrorEvent.id.in_(ids[start:start + batch_size])).all()
        by_entity: dict[str, list] = {}
        for ev in chunk:
            by_entity.setdefault(ev.entity, []).append(
                (ev.source_id, ev.source_version, ev.raw or {}))
        for entity, records in by_entity.items():
            res = project_batch(db, source_system_id=source_system_id,
                                entity=entity, records=records)
            for key in ("projected", "updated", "unmapped", "unchanged"):
                totals[key] += res[key]
            for key, val in res["by_table"].items():
                totals["by_table"][key] = totals["by_table"].get(key, 0) + val
            for key, val in res["reasons"].items():
                totals["reasons"][key] = totals["reasons"].get(key, 0) + val
    return totals


def projection_summary(db: Session, source_system_id: int) -> dict:
    """Counts for the status endpoint: what landed, what did not, and why."""
    from sqlalchemy import func

    by_status = {
        status: int(count)
        for status, count in db.query(
            ProjectionLink.status, func.count(ProjectionLink.id)
        ).filter(ProjectionLink.source_system_id == source_system_id)
         .group_by(ProjectionLink.status).all()
    }
    tables = db.query(
        ProjectionLink.domain_table, func.count(ProjectionLink.id)
    ).filter(ProjectionLink.source_system_id == source_system_id,
             ProjectionLink.status == "projected"
    ).group_by(ProjectionLink.domain_table).all()
    reasons = db.query(
        ProjectionLink.reason, func.count(ProjectionLink.id)
    ).filter(ProjectionLink.source_system_id == source_system_id,
             ProjectionLink.status == "unmapped"
    ).group_by(ProjectionLink.reason).order_by(
        func.count(ProjectionLink.id).desc()).limit(5).all()

    return {
        "projected": by_status.get("projected", 0),
        "unmapped": by_status.get("unmapped", 0),
        "by_table": {t: int(c) for t, c in tables if t},
        "top_unmapped_reasons": {r: int(c) for r, c in reasons if r},
        "money_unit": money_unit(),
    }
