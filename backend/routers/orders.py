from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from rate_limit import limiter
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from time_utils import utcnow
import stock_ledger

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/", response_model=schemas.OrderOut)
async def create_order(
    order: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)

    # Idempotent replay: the offline POS queue (frontend lib/offlineQueue.ts)
    # can't always tell whether a queued order it's flushing actually reached
    # the server — the request may have succeeded and only the RESPONSE was
    # lost to a flaky connection, in which case retrying a plain create would
    # ring in the same ticket twice and deduct its stock twice. A client that
    # sent client_order_id gets the SAME order back on a repeat, not a new one.
    existing = _find_by_client_order_id(db, restaurant.id, order.client_order_id)
    if existing is not None:
        return _order_to_dict(existing)

    # Look up menu items and calculate total
    total = 0
    order_items = []
    for oi in order.items:
        menu_item = db.query(models.MenuItem).filter(
            models.MenuItem.id == oi.menu_item_id,
            models.MenuItem.restaurant_id == restaurant.id,
        ).first()
        if not menu_item:
            raise HTTPException(status_code=404, detail=f"Menu item {oi.menu_item_id} not found")
        line_total = menu_item.price * oi.quantity
        total += line_total
        order_items.append(models.OrderItem(
            menu_item_id=menu_item.id,
            quantity=oi.quantity,
            unit_price=menu_item.price,
        ))

    # Map string enums safely
    try:
        order_type = models.OrderType(order.order_type)
    except ValueError:
        order_type = models.OrderType.DINE_IN
    try:
        delivery_channel = models.DeliveryChannel(order.delivery_channel)
    except ValueError:
        delivery_channel = models.DeliveryChannel.WALK_IN
    try:
        payment_method = models.PaymentMethod(order.payment_method)
    except ValueError:
        payment_method = models.PaymentMethod.PENDING

    is_paid = payment_method != models.PaymentMethod.PENDING

    db_order = models.Order(
        restaurant_id=restaurant.id,
        order_type=order_type,
        delivery_channel=delivery_channel,
        payment_method=payment_method,
        is_paid=is_paid,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        table_number=order.table_number,
        total=total,
        notes=order.notes,
        client_order_id=order.client_order_id,
        items=order_items,
    )
    db.add(db_order)
    # flush (not commit) to get the order id, then deduct ingredients inside the
    # SAME transaction — if anything below fails, the sale and the stock movement
    # roll back together and can't leave inventory drifted from what was sold.
    db.flush()
    stock_ledger.consume_for_order(db, db_order)
    db.commit()
    db.refresh(db_order)
    return _order_to_dict(db_order)


@router.get("/", response_model=List[schemas.OrderOut])
async def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    q = db.query(models.Order).options(
        joinedload(models.Order.items).joinedload(models.OrderItem.menu_item)
    ).filter(models.Order.restaurant_id == restaurant.id)

    if status_filter:
        try:
            q = q.filter(models.Order.status == models.OrderStatus(status_filter))
        except ValueError:
            pass

    orders = q.order_by(models.Order.created_at.desc()).limit(200).all()
    return [_order_to_dict(o) for o in orders]


@router.get("/active", response_model=List[schemas.OrderOut])
async def active_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Orders for the KDS — pending, cooking, or ready."""
    restaurant = get_or_create_restaurant(db, current_user)
    active_statuses = [models.OrderStatus.PENDING, models.OrderStatus.PREP, models.OrderStatus.READY]
    orders = db.query(models.Order).options(
        joinedload(models.Order.items).joinedload(models.OrderItem.menu_item)
    ).filter(
        models.Order.restaurant_id == restaurant.id,
        models.Order.status.in_(active_statuses),
    ).order_by(models.Order.created_at.asc()).all()
    return [_order_to_dict(o) for o in orders]


@router.patch("/{order_id}/status", response_model=schemas.OrderOut)
async def update_order_status(
    order_id: int,
    update: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    # joinedload items→menu_item: _record_prep_start needs each item's
    # prep_station, and without eager loading that's an N+1 on every KDS bump.
    order = db.query(models.Order).options(
        joinedload(models.Order.items).joinedload(models.OrderItem.menu_item)
    ).filter(
        models.Order.id == order_id,
        models.Order.restaurant_id == restaurant.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        new_status = models.OrderStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

    order.status = new_status
    if new_status == models.OrderStatus.SERVED:
        order.completed_at = utcnow()

    # Kitchen timing capture. Until 2026-08-06 nothing in the running app ever
    # wrote a PrepTime row — the only writer in the codebase was the demo seeder
    # (populate_production.py) — so ai/kds_intelligence.py (station p95s,
    # bottleneck severity, queue depth, delay risk, ~12 analytics in all) read an
    # empty table on every real restaurant and returned _empty_response(). This
    # is the missing write path, not new analytics.
    _record_prep_timing(db, order, new_status)

    # A voided ticket gives its ingredients back. Guarded inside the ledger so a
    # double-tapped cancel can't restore twice and silently inflate stock.
    if new_status == models.OrderStatus.CANCELLED:
        stock_ledger.restore_for_order(db, order)

    db.commit()
    db.refresh(order)
    return _order_to_dict(order)


# ── Kitchen prep timing ──────────────────────────────────────────────────────
#
# One PrepTime row per OrderItem, opened when the ticket reaches the kitchen and
# closed when it leaves. ai/kds_intelligence.py only ever reads rows where
# actual_minutes is not None, so an order that is cancelled mid-prep simply
# leaves an open row that never enters the statistics — no cleanup needed and no
# skew from abandoned tickets.

_PREP_OPEN_STATUSES  = {models.OrderStatus.PREP}
_PREP_CLOSE_STATUSES = {models.OrderStatus.READY, models.OrderStatus.SERVED}


def _record_prep_timing(db: Session, order: models.Order, new_status: models.OrderStatus) -> None:
    """
    Open or close this order's per-item prep timers for a status transition.

    Both halves are idempotent: re-sending the same status (a double-tap on the
    KDS, or a retry) must not create a second row or overwrite a measurement
    that has already been taken. A backwards bump (READY -> PREP) deliberately
    does NOT reopen a closed row — the first completion is kept as the
    measurement rather than being silently extended by however long the ticket
    sat before someone corrected the status.
    """
    if new_status in _PREP_OPEN_STATUSES:
        _open_prep_timers(db, order)
    elif new_status in _PREP_CLOSE_STATUSES:
        # A kitchen that bumps straight from PENDING to READY never passes
        # through PREP, so open the timers first — otherwise those tickets
        # contribute nothing at all. Their start is the order's own created_at,
        # which measures the full ticket time; that is the only defensible
        # reading when the kitchen never signalled when it picked the order up.
        _open_prep_timers(db, order, started_at=order.created_at)
        _close_prep_timers(db, order)


def _open_prep_timers(db: Session, order: models.Order, started_at=None) -> None:
    """Create a PrepTime row for each order item that doesn't already have one."""
    existing = {
        pt.order_item_id
        for pt in db.query(models.PrepTime.order_item_id).filter(
            models.PrepTime.order_item_id.in_([oi.id for oi in (order.items or [])] or [0])
        ).all()
    }
    start = started_at or utcnow()
    for oi in (order.items or []):
        if oi.id in existing:
            continue
        db.add(models.PrepTime(
            order_item_id=oi.id,
            # The station the dish is actually made at. MenuItem.prep_station has
            # existed (defaulting to "main") since the original schema but was
            # never read by anything that writes — this is what turns
            # kds_intelligence's per-station breakdown from one bucket into real
            # grill/fryer/salad/drinks numbers.
            station=(oi.menu_item.prep_station if oi.menu_item else "main") or "main",
            started_at=start,
        ))


def _close_prep_timers(db: Session, order: models.Order) -> None:
    """Stamp completed_at + actual_minutes on this order's still-open timers."""
    item_ids = [oi.id for oi in (order.items or [])]
    if not item_ids:
        return
    # flush() so rows added by _open_prep_timers in this same transaction (the
    # PENDING->READY skip path) are visible to the query below.
    db.flush()
    now = utcnow()
    open_timers = db.query(models.PrepTime).filter(
        models.PrepTime.order_item_id.in_(item_ids),
        models.PrepTime.completed_at.is_(None),
    ).all()
    for pt in open_timers:
        pt.completed_at = now
        start = pt.started_at or now
        # Clamp at 0: a clock adjustment between open and close must never
        # produce a negative prep time, which would corrupt every downstream
        # average, p95 and std-dev in kds_intelligence.
        pt.actual_minutes = max(0.0, (now - start).total_seconds() / 60.0)


@router.patch("/{order_id}/payment", response_model=schemas.OrderOut)
async def update_order_payment(
    order_id: int,
    update: schemas.OrderPaymentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        models.Order.restaurant_id == restaurant.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        order.payment_method = models.PaymentMethod(update.payment_method)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid payment method: {update.payment_method}")

    # Capture the transition so a receipt fires exactly once, only when an order
    # actually moves unpaid -> paid. Re-marking an already-paid order (or a paid
    # M-Pesa order the webhook already settled + receipted) must not re-send.
    was_paid = bool(order.is_paid)
    order.is_paid = update.is_paid
    db.commit()
    db.refresh(order)

    if order.is_paid and not was_paid:
        # Mirrors the M-Pesa webhook's ORDER_PAID emit (routers/webhooks.py) so
        # cash/card orders marked paid at the POS get the same itemized customer
        # receipt. No mpesa_reference for these — compose_receipt omits that line.
        from events.bus import emit_async, EventType
        emit_async(EventType.ORDER_PAID, {
            "restaurant_id": order.restaurant_id,
            "order_id": order.id,
            "amount_cents": order.total or 0,
            "customer_phone": order.customer_phone or "",
            "payment_method": order.payment_method.value if order.payment_method else "unknown",
        })

    return _order_to_dict(order)


# ── Public endpoint (no auth) for customer ordering ──

@router.post("/public", response_model=schemas.OrderOut)
@limiter.limit("20/minute")
async def create_public_order(
    request: Request,
    order: schemas.OrderCreate,
    restaurant_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Customer-facing order endpoint — no login required. Rate limited
    (security pass 2026-07-07): unauthenticated, and a real M-Pesa STK push
    can be triggered per request — unlimited requests here means both order-
    spam/DB-bloat risk and a real cost/abuse vector once M-Pesa is live.
    """
    restaurant = db.query(models.Restaurant).filter(
        models.Restaurant.id == restaurant_id
    ).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    # Idempotent replay — see create_order's comment above for why this exists.
    existing = _find_by_client_order_id(db, restaurant.id, order.client_order_id)
    if existing is not None:
        return _order_to_dict(existing)

    # Consent gate: only meaningful when actual PII (a phone number) is being
    # collected — an anonymous walk-in-style public order with no contact
    # info has nothing to consent to.
    if order.customer_phone and not order.consent:
        raise HTTPException(
            status_code=400,
            detail="Consent is required to place an order with contact details.",
        )
    if order.customer_phone:
        db.add(models.CustomerConsent(
            restaurant_id=restaurant.id,
            customer_phone=order.customer_phone,
            purpose="order_checkout",
        ))

    total = 0
    order_items = []
    for oi in order.items:
        menu_item = db.query(models.MenuItem).filter(
            models.MenuItem.id == oi.menu_item_id,
            models.MenuItem.restaurant_id == restaurant.id,
            models.MenuItem.is_available == True,
        ).first()
        if not menu_item:
            raise HTTPException(status_code=404, detail=f"Menu item {oi.menu_item_id} not found or unavailable")
        line_total = menu_item.price * oi.quantity
        total += line_total
        order_items.append(models.OrderItem(
            menu_item_id=menu_item.id,
            quantity=oi.quantity,
            unit_price=menu_item.price,
        ))

    try:
        order_type = models.OrderType(order.order_type)
    except ValueError:
        order_type = models.OrderType.TAKEOUT
    try:
        payment_method = models.PaymentMethod(order.payment_method)
    except ValueError:
        payment_method = models.PaymentMethod.PENDING

    db_order = models.Order(
        restaurant_id=restaurant.id,
        order_type=order_type,
        delivery_channel=models.DeliveryChannel.APP,
        payment_method=payment_method,
        is_paid=False,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        total=total,
        notes=order.notes,
        client_order_id=order.client_order_id,
        items=order_items,
    )
    db.add(db_order)
    # Same single-transaction deduction as the authenticated POS path above — a
    # customer self-service order consumes exactly the same ingredients.
    db.flush()
    stock_ledger.consume_for_order(db, db_order)
    db.commit()
    db.refresh(db_order)

    if payment_method == models.PaymentMethod.MPESA:
        _trigger_mpesa_stk_push(db, db_order)

    return _order_to_dict(db_order)


def _trigger_mpesa_stk_push(db: Session, order: models.Order) -> None:
    """
    Best-effort: a failed/unconfigured STK push should never break order
    creation. The customer/staff can retry payment through other means
    (cash, card, or a manual STK retry) — the order itself is already valid.
    """
    from payments import mpesa_client

    phone = mpesa_client.normalize_phone(order.customer_phone or "")
    if not phone:
        return

    result = mpesa_client.initiate_stk_push(
        phone_number=phone,
        amount_cents=order.total or 0,
        account_reference=f"ORDER-{order.id}",
        description=f"Order #{order.id}",
    )
    if result["status"] == "initiated":
        order.mpesa_checkout_request_id = result["checkout_request_id"]
        db.commit()


def _find_by_client_order_id(db: Session, restaurant_id: int, client_order_id: str | None) -> models.Order | None:
    """
    An empty/None client_order_id is the normal case (every online order) and
    must never match anything — an empty-string lookup against a nullable
    column would be a meaningless query, and treating "no id given" as "found"
    would make every plain online order collide with every other one.
    """
    if not client_order_id:
        return None
    return db.query(models.Order).options(
        joinedload(models.Order.items).joinedload(models.OrderItem.menu_item)
    ).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.client_order_id == client_order_id,
    ).first()


def _order_to_dict(order: models.Order) -> dict:
    """Convert Order model to dict matching OrderOut schema."""
    items_out = []
    for oi in (order.items or []):
        item_name = ""
        if oi.menu_item:
            item_name = oi.menu_item.name
        items_out.append({
            "id": oi.id,
            "menu_item_id": oi.menu_item_id,
            "quantity": oi.quantity,
            "unit_price": oi.unit_price,
            "item_name": item_name,
        })
    return {
        "id": order.id,
        "status": order.status.value if order.status else "pending",
        "order_type": order.order_type.value if order.order_type else "dine_in",
        "delivery_channel": order.delivery_channel.value if order.delivery_channel else "walk_in",
        "payment_method": order.payment_method.value if order.payment_method else "pending",
        "is_paid": order.is_paid or False,
        "customer_name": order.customer_name or "",
        "customer_phone": order.customer_phone or "",
        "table_number": order.table_number,
        "total": order.total or 0,
        "notes": order.notes or "",
        "created_at": order.created_at,
        "completed_at": order.completed_at,
        "items": items_out,
    }
