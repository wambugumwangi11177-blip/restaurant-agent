"""
backend/routers/export.py
──────────────────────────
Data-subject rights endpoints (Kenya Data Protection Act 2019 — and what the
DPA/Privacy Policy promise):

  • Portability — GET /data/export/orders.csv, /data/export/customers.csv
      Tenant-scoped CSV export the admin can download from the dashboard.
  • Erasure    — POST /data/erase-customer
      Scrubs a customer's PII (name + phone) from orders and reservations,
      deletes their consent records, and records an opt-out so downstream
      marketing never re-targets a number the person asked us to forget.

All endpoints are authed and restaurant-scoped via the shared
get_or_create_restaurant dependency — a token for one tenant can only ever
export or erase its own data.
"""

import csv
import io
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from schemas import StrictModel
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func

from database import get_db
import models
import auth
from routers.deps import get_or_create_restaurant
from payments.mpesa_client import normalize_phone
from audit import record_security_event, hash_identifier, SUCCESS

router = APIRouter(prefix="/data", tags=["data-rights"])


# Leading characters a spreadsheet app (Excel/Sheets/LibreOffice) interprets as
# the start of a formula. Customer-supplied fields (name, phone, item names) end
# up in these CSVs, so a value like `=HYPERLINK(...)` or `=cmd|...` would execute
# in the admin's spreadsheet on open — classic CSV/formula injection. We neutralize
# by prefixing a single quote so the cell is treated as literal text.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """Neutralize spreadsheet formula injection in a single cell value."""
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    if s and s[0] in _CSV_FORMULA_PREFIXES:
        return "'" + s
    return s


def _csv_stream(header: list[str], rows):
    """
    Stream rows as CSV without buffering the whole file in memory — matters
    for restaurants with 100k+ orders. Yields the header then one line per row.
    Every cell is passed through _csv_safe to defuse formula injection.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def take():
        value = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return value

    writer.writerow(header)
    yield take()
    for row in rows:
        writer.writerow([_csv_safe(cell) for cell in row])
        yield take()


def _phone_variants(phone: str) -> list[str]:
    """
    The same person's number may be stored in several shapes across orders and
    reservations (0712…, +254712…, 254712…). Match all common variants of the
    canonical number so erasure/export don't miss rows on formatting alone.
    """
    variants = {phone}
    canonical = normalize_phone(phone)  # 2547XXXXXXXX or None
    if canonical:
        local = canonical[3:]  # 7XXXXXXXX
        variants.update({canonical, "+" + canonical, "0" + local, local})
    return [v for v in variants if v]


# ── Portability ───────────────────────────────────────────────────────────────

@router.get("/export/orders.csv")
async def export_orders_csv(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    """One row per order (with an item summary). Money reported in KES."""
    restaurant = get_or_create_restaurant(db, current_user)
    orders = (
        db.query(models.Order)
        .options(selectinload(models.Order.items).selectinload(models.OrderItem.menu_item))
        .filter(models.Order.restaurant_id == restaurant.id)
        .order_by(models.Order.created_at.asc())
        .yield_per(500)
    )

    header = [
        "order_id", "created_at", "status", "order_type", "payment_method",
        "is_paid", "total_kes", "customer_name", "customer_phone", "items",
    ]

    def rows():
        for o in orders:
            items = "; ".join(
                f"{(oi.menu_item.name if oi.menu_item else '?')} x{oi.quantity}"
                for oi in (o.items or [])
            )
            yield [
                o.id,
                o.created_at.isoformat() if o.created_at else "",
                o.status.value if o.status else "",
                o.order_type.value if o.order_type else "",
                o.payment_method.value if o.payment_method else "",
                "yes" if o.is_paid else "no",
                (o.total or 0) / 100,
                o.customer_name or "",
                o.customer_phone or "",
                items,
            ]

    # Recorded BEFORE the response is returned. The rows() generator below runs
    # while the response streams, after this function has returned, so an audit
    # write attempted from inside it would race the session teardown. commit=True
    # because a read-only endpoint has no write of its own to ride along with.
    record_security_event(
        db, request, "data.export.orders", SUCCESS,
        actor=current_user, restaurant_id=restaurant.id,
        target_type="restaurant", target_ref=str(restaurant.id),
        includes_pii=True, commit=True,
    )

    filename = f"orders_restaurant_{restaurant.id}.csv"
    return StreamingResponse(
        _csv_stream(header, rows()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/customers.csv")
async def export_customers_csv(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    """Aggregated customer list (portability of the customer records we hold)."""
    restaurant = get_or_create_restaurant(db, current_user)
    customer_rows = (
        db.query(
            models.Order.customer_phone,
            func.max(models.Order.customer_name).label("customer_name"),
            func.count(models.Order.id).label("order_count"),
            func.sum(models.Order.total).label("total_spend"),
            func.max(models.Order.created_at).label("last_order"),
        )
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.customer_phone.isnot(None),
            models.Order.customer_phone != "",
        )
        .group_by(models.Order.customer_phone)
        .order_by(func.sum(models.Order.total).desc())
        .all()
    )

    header = ["customer_phone", "customer_name", "order_count", "total_spend_kes", "last_order"]

    def rows():
        for r in customer_rows:
            yield [
                r.customer_phone or "",
                r.customer_name or "",
                r.order_count,
                (r.total_spend or 0) / 100,
                r.last_order.isoformat() if r.last_order else "",
            ]

    # This endpoint hands over every customer's name, phone, spend and last-order
    # date for the tenant. It is the single largest PII egress in the app, and
    # until now it left no trace at all — "who exported the customer list, and
    # when" had no answer. Row count is recorded; the rows themselves are not.
    record_security_event(
        db, request, "data.export.customers", SUCCESS,
        actor=current_user, restaurant_id=restaurant.id,
        target_type="restaurant", target_ref=str(restaurant.id),
        rows_exported=len(customer_rows), includes_pii=True, commit=True,
    )

    filename = f"customers_restaurant_{restaurant.id}.csv"
    return StreamingResponse(
        _csv_stream(header, rows()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Erasure ───────────────────────────────────────────────────────────────────

class EraseCustomerRequest(StrictModel):
    customer_phone: str


def _restaurant_knows_phone(db: Session, restaurant_id: int, variants: list[str]) -> bool:
    """
    True iff this restaurant holds at least one order, reservation, or consent
    row for any variant of the phone number. Gate for the phone-global opt-out
    write — see `erase_customer`.
    """
    for model in (models.Order, models.Reservation, models.CustomerConsent):
        exists = (
            db.query(model.id)
            .filter(
                model.restaurant_id == restaurant_id,
                model.customer_phone.in_(variants),
            )
            .first()
        )
        if exists:
            return True
    return False


@router.post("/erase-customer")
async def erase_customer(
    body: EraseCustomerRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role(models.Role.ADMIN)),
):
    """
    Right to erasure. Scrubs customer PII from this restaurant's orders and
    reservations (order/booking records are kept for financial/tax integrity,
    but the name and phone are nulled), removes consent rows, and adds an
    opt-out so the number is never re-targeted. Restaurant-scoped: only the
    caller's own tenant data is touched.

    Ownership pre-flight (security pass): the opt-out list this writes to
    (`CustomerOptOut`) is phone-global and has no restaurant_id — a suppressed
    number is suppressed for EVERY tenant. Without the check below, tenant A
    could submit tenant B's customer's number and permanently destroy B's
    ability to WhatsApp them (denial-of-messaging). So we only honour an
    erasure for a phone this tenant demonstrably holds data for.
    """
    restaurant = get_or_create_restaurant(db, current_user)
    variants = _phone_variants(body.customer_phone)

    # The hashed reference is computed once and reused: it is what makes the
    # trail useful (correlate repeated actions on one target, match a number
    # from a complaint) without ever storing the number itself. Storing it raw
    # would mean this endpoint permanently records the phone number the customer
    # asked to have forgotten.
    phone_ref = hash_identifier(normalize_phone(body.customer_phone) or body.customer_phone)

    if not _restaurant_knows_phone(db, restaurant.id, variants):
        # Worth recording, not just returning. The docstring above reasons about
        # a tenant submitting another tenant's customer's number to poison the
        # phone-global opt-out; a run of these is what that abuse looks like, and
        # without a row there is nothing to detect it with.
        record_security_event(
            db, request, "data.erase_customer.no_data", SUCCESS,
            actor=current_user, restaurant_id=restaurant.id,
            target_type="customer", target_ref=phone_ref,
            commit=True,
        )
        return {
            "status": "no_data",
            "customer_phone": body.customer_phone,
            "orders_scrubbed": 0,
            "reservations_scrubbed": 0,
            "consents_deleted": 0,
        }

    orders_scrubbed = (
        db.query(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.customer_phone.in_(variants),
        )
        .update({models.Order.customer_name: None, models.Order.customer_phone: None},
                synchronize_session=False)
    )

    reservations_scrubbed = (
        db.query(models.Reservation)
        .filter(
            models.Reservation.restaurant_id == restaurant.id,
            models.Reservation.customer_phone.in_(variants),
        )
        .update({models.Reservation.customer_name: None,
                 models.Reservation.customer_phone: None,
                 models.Reservation.customer_email: None},
                synchronize_session=False)
    )

    consents_deleted = (
        db.query(models.CustomerConsent)
        .filter(
            models.CustomerConsent.restaurant_id == restaurant.id,
            models.CustomerConsent.customer_phone.in_(variants),
        )
        .delete(synchronize_session=False)
    )

    # Same transaction as the scrub above: if the audit row cannot be written the
    # erasure rolls back with it, so there is no irreversible PII deletion that
    # nobody can account for afterwards.
    record_security_event(
        db, request, "data.erase_customer", SUCCESS,
        actor=current_user, restaurant_id=restaurant.id,
        target_type="customer", target_ref=phone_ref,
        orders_scrubbed=orders_scrubbed,
        reservations_scrubbed=reservations_scrubbed,
        consents_deleted=consents_deleted,
    )

    db.commit()

    # Suppress future marketing to this number (idempotent, phone-global).
    from ai.whatsapp.optout import record_opt_out
    record_opt_out(db, body.customer_phone, source="erasure_request")

    return {
        "status": "erased",
        "customer_phone": body.customer_phone,
        "orders_scrubbed": orders_scrubbed,
        "reservations_scrubbed": reservations_scrubbed,
        "consents_deleted": consents_deleted,
    }
