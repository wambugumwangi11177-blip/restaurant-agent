from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from rate_limit import limiter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from time_utils import utcnow

router = APIRouter(prefix="/orders", tags=["orders"])


def _find_by_idempotency_key(db: Session, key: str, restaurant_id: int):
    """Tenant-scoped idempotency lookup. Factored out because create_order runs
    it twice — once as the fast path, once after losing the insert race — and
    because a test needs to stub the first call to reproduce that race."""
    return db.query(models.Order).filter(
        models.Order.idempotency_key == key,
        models.Order.restaurant_id == restaurant_id,
    ).first()


@router.post("/", response_model=schemas.OrderOut)
async def create_order(
    order: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)

    # Idempotent replay (tech-debt D15): the POS offline queue retries the
    # same key after a network drop. Scoped to this tenant so a key collision
    # across restaurants can't leak/return someone else's order.
    if order.idempotency_key:
        existing = _find_by_idempotency_key(db, order.idempotency_key, restaurant.id)
        if existing:
            return _order_to_dict(existing)

    # PIN quick-switch attribution (tech-debt D16) — validate the attributed
    # user belongs to THIS tenant before stamping it (same IDOR discipline as
    # everywhere else; this is metadata, not a privilege, but a cross-tenant
    # id must still never be accepted silently). Falls back to no attribution
    # rather than erroring — a device that hasn't PIN-switched still works.
    attributed_user_id = None
    if order.attributed_user_id:
        attributed_user = db.query(models.User).filter(
            models.User.id == order.attributed_user_id,
            models.User.tenant_id == current_user.tenant_id,
            models.User.is_active.is_(True),
        ).first()
        if attributed_user:
            attributed_user_id = attributed_user.id

    # Look up menu items and calculate total with modifiers
    total = 0
    order_items = []
    for oi in order.items:
        menu_item = db.query(models.MenuItem).filter(
            models.MenuItem.id == oi.menu_item_id,
            models.MenuItem.restaurant_id == restaurant.id,
        ).first()
        if not menu_item:
            raise HTTPException(status_code=404, detail=f"Menu item {oi.menu_item_id} not found")
        
        # Calculate modifiers price delta
        mod_deltas = 0
        db_mods = []
        for mod in (oi.modifiers or []):
            mod_deltas += mod.price_delta_cents
            db_mods.append(models.OrderItemModifier(
                modifier_option_id=mod.modifier_option_id,
                name=mod.name,
                price_delta_cents=mod.price_delta_cents,
            ))

        line_unit_price = menu_item.price + mod_deltas
        line_total = line_unit_price * oi.quantity
        total += line_total

        order_items.append(models.OrderItem(
            menu_item_id=menu_item.id,
            quantity=oi.quantity,
            unit_price=line_unit_price,
            notes=oi.notes or "",
            modifiers=db_mods,
        ))

        # Recipe / BOM automatic stock depletion on order
        recipes = db.query(models.MenuIngredient).filter(
            models.MenuIngredient.menu_item_id == menu_item.id
        ).all()
        for rec in recipes:
            inv_item = db.query(models.InventoryItem).filter(
                models.InventoryItem.id == rec.inventory_item_id,
                models.InventoryItem.restaurant_id == restaurant.id,
            ).first()
            if inv_item:
                deplete_qty = rec.quantity_per_serving * oi.quantity
                inv_item.quantity = (inv_item.quantity or 0) - deplete_qty
                db.add(models.StockMovement(
                    inventory_item_id=inv_item.id,
                    movement_type=models.StockMovementType.OUT,
                    quantity=deplete_qty,
                    reason="sale",
                    user_id=attributed_user_id or current_user.id,
                ))

    # Apply discounts, tax, and service charge
    calculated_total = max(0, total - (order.discount_cents or 0)) + (order.tax_cents or 0) + (order.service_charge_cents or 0)

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

    # Payments list
    order_payments = []
    paid_sum = 0
    for p in (order.payments or []):
        paid_sum += p.amount_cents
        order_payments.append(models.OrderPayment(
            payment_method=p.payment_method,
            amount_cents=p.amount_cents,
            reference=p.reference,
        ))

    is_paid = (payment_method != models.PaymentMethod.PENDING and payment_method is not None) or (paid_sum >= calculated_total and calculated_total > 0)

    db_order = models.Order(
        restaurant_id=restaurant.id,
        order_type=order_type,
        delivery_channel=delivery_channel,
        payment_method=payment_method,
        is_paid=is_paid,
        customer_name=order.customer_name,
        customer_phone=order.customer_phone,
        table_number=order.table_number,
        total=calculated_total,
        notes=order.notes,
        discount_cents=order.discount_cents or 0,
        discount_reason=order.discount_reason or "",
        tax_cents=order.tax_cents or 0,
        service_charge_cents=order.service_charge_cents or 0,
        items=order_items,
        payments=order_payments,
        idempotency_key=order.idempotency_key,
        attributed_user_id=attributed_user_id,
    )
    db.add(db_order)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if order.idempotency_key:
            existing = _find_by_idempotency_key(db, order.idempotency_key, restaurant.id)
            if existing:
                return _order_to_dict(existing)
        raise
    db.refresh(db_order)
    return _order_to_dict(db_order)


@router.get("/", response_model=List[schemas.OrderOut])
async def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    channel: Optional[str] = None,
    unpaid: Optional[bool] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    q = db.query(models.Order).options(
        joinedload(models.Order.items).joinedload(models.OrderItem.menu_item),
        joinedload(models.Order.items).joinedload(models.OrderItem.modifiers),
        joinedload(models.Order.payments),
    ).filter(models.Order.restaurant_id == restaurant.id)

    if status_filter:
        try:
            q = q.filter(models.Order.status == models.OrderStatus(status_filter))
        except ValueError:
            pass

    if channel:
        try:
            q = q.filter(models.Order.delivery_channel == models.DeliveryChannel(channel))
        except ValueError:
            pass

    if unpaid is not None:
        q = q.filter(models.Order.is_paid == (not unpaid))

    if search:
        s = f"%{search.strip()}%"
        q = q.filter(
            (models.Order.customer_name.ilike(s)) |
            (models.Order.customer_phone.ilike(s)) |
            (models.Order.id.cast(models.String).ilike(s))
        )

    if date_from:
        q = q.filter(models.Order.created_at >= f"{date_from} 00:00:00")
    if date_to:
        q = q.filter(models.Order.created_at <= f"{date_to} 23:59:59")

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
    order = db.query(models.Order).filter(
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

    db.commit()
    db.refresh(order)
    return _order_to_dict(order)


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
        items=order_items,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    if payment_method == models.PaymentMethod.MPESA:
        _trigger_mpesa_stk_push(db, db_order)

    return _order_to_dict(db_order)


@router.get("/{order_id}", response_model=schemas.OrderOut)
async def get_order_by_id(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    order = db.query(models.Order).options(
        joinedload(models.Order.items).joinedload(models.OrderItem.menu_item),
        joinedload(models.Order.items).joinedload(models.OrderItem.modifiers),
        joinedload(models.Order.payments),
    ).filter(
        models.Order.id == order_id,
        models.Order.restaurant_id == restaurant.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_dict(order)


@router.post("/{order_id}/void", response_model=schemas.OrderOut)
async def void_order(
    order_id: int,
    req: schemas.OrderVoidRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not req.void_reason or not req.void_reason.strip():
        raise HTTPException(status_code=400, detail="Void reason is mandatory")
    restaurant = get_or_create_restaurant(db, current_user)
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        models.Order.restaurant_id == restaurant.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = models.OrderStatus.CANCELLED
    order.void_reason = req.void_reason.strip()
    db.commit()
    db.refresh(order)
    return _order_to_dict(order)


@router.post("/{order_id}/refund", response_model=schemas.OrderOut)
async def refund_order(
    order_id: int,
    req: schemas.OrderRefundRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not req.refund_reason or not req.refund_reason.strip():
        raise HTTPException(status_code=400, detail="Refund reason is mandatory")
    if req.refund_cents <= 0:
        raise HTTPException(status_code=400, detail="Refund amount must be positive")
    restaurant = get_or_create_restaurant(db, current_user)
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        models.Order.restaurant_id == restaurant.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.refund_cents = (order.refund_cents or 0) + req.refund_cents
    order.refund_reason = req.refund_reason.strip()
    db.commit()
    db.refresh(order)
    return _order_to_dict(order)


@router.post("/{order_id}/items/{item_id}/void", response_model=schemas.OrderOut)
async def void_order_item(
    order_id: int,
    item_id: int,
    req: schemas.OrderVoidRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not req.void_reason or not req.void_reason.strip():
        raise HTTPException(status_code=400, detail="Void reason is mandatory")
    restaurant = get_or_create_restaurant(db, current_user)
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        models.Order.restaurant_id == restaurant.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    oi = db.query(models.OrderItem).filter(
        models.OrderItem.id == item_id,
        models.OrderItem.order_id == order.id,
    ).first()
    if not oi:
        raise HTTPException(status_code=404, detail="Order item not found")

    oi.is_voided = True
    oi.void_reason = req.void_reason.strip()

    # Recalculate order total from non-voided items
    active_items = db.query(models.OrderItem).filter(
        models.OrderItem.order_id == order.id,
        models.OrderItem.is_voided == False,
    ).all()
    subtotal = sum(item.unit_price * item.quantity for item in active_items)
    order.total = max(0, subtotal - (order.discount_cents or 0)) + (order.tax_cents or 0) + (order.service_charge_cents or 0)
    db.commit()
    db.refresh(order)
    return _order_to_dict(order)


@router.post("/{order_id}/reprint")
async def reprint_receipt(
    order_id: int,
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
    return {"status": "printed", "order_id": order.id, "message": "Receipt sent to printer port"}


@router.post("/{order_id}/resend-kitchen")
async def resend_to_kitchen(
    order_id: int,
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
    order.status = models.OrderStatus.PENDING
    db.commit()
    db.refresh(order)
    return _order_to_dict(order)


@router.get("/{order_id}/customer-history")
async def get_customer_history(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    order = db.query(models.Order).filter(
        models.Order.id == order_id,
        models.Order.restaurant_id == restaurant.id,
    ).first()
    if not order or not order.customer_phone:
        return {"customer_phone": order.customer_phone if order else "", "order_count": 0, "total_spent_cents": 0, "past_orders": []}

    past = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant.id,
        models.Order.customer_phone == order.customer_phone,
    ).order_by(models.Order.created_at.desc()).limit(20).all()

    total_spent = sum(o.total or 0 for o in past if o.status != models.OrderStatus.CANCELLED)
    return {
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "order_count": len(past),
        "total_spent_cents": total_spent,
        "past_orders": [_order_to_dict(o) for o in past],
    }


# ── Till Sessions ──

@router.post("/tills/open", response_model=schemas.TillSessionOut)
async def open_till(
    body: schemas.TillSessionOpen,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    open_till = db.query(models.TillSession).filter(
        models.TillSession.restaurant_id == restaurant.id,
        models.TillSession.status == "open",
    ).first()
    if open_till:
        return _till_to_dict(open_till, current_user)

    till = models.TillSession(
        restaurant_id=restaurant.id,
        user_id=current_user.id,
        opening_float_cents=body.opening_float_cents,
        status="open",
        notes=body.notes or "",
    )
    db.add(till)
    db.commit()
    db.refresh(till)
    return _till_to_dict(till, current_user)


@router.get("/tills/current", response_model=Optional[schemas.TillSessionOut])
async def get_current_till(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    till = db.query(models.TillSession).filter(
        models.TillSession.restaurant_id == restaurant.id,
        models.TillSession.status == "open",
    ).first()
    if not till:
        return None
    return _till_to_dict(till, current_user)


@router.get("/tills/{till_id}/x-report")
async def get_till_x_report(
    till_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    till = db.query(models.TillSession).filter(
        models.TillSession.id == till_id,
        models.TillSession.restaurant_id == restaurant.id,
    ).first()
    if not till:
        raise HTTPException(status_code=404, detail="Till session not found")

    end_time = till.closed_at or utcnow()
    orders = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant.id,
        models.Order.created_at >= till.opened_at,
        models.Order.created_at <= end_time,
        models.Order.status != models.OrderStatus.CANCELLED,
    ).all()

    cash_total = sum(o.total or 0 for o in orders if o.payment_method == models.PaymentMethod.CASH and o.is_paid)
    mpesa_total = sum(o.total or 0 for o in orders if o.payment_method == models.PaymentMethod.MPESA and o.is_paid)
    card_total = sum(o.total or 0 for o in orders if o.payment_method == models.PaymentMethod.CARD and o.is_paid)
    unpaid_total = sum(o.total or 0 for o in orders if not o.is_paid)
    expected_cash = till.opening_float_cents + cash_total

    return {
        "till_id": till.id,
        "status": till.status,
        "opened_at": till.opened_at,
        "closed_at": till.closed_at,
        "opening_float_cents": till.opening_float_cents,
        "cash_sales_cents": cash_total,
        "mpesa_sales_cents": mpesa_total,
        "card_sales_cents": card_total,
        "unpaid_cents": unpaid_total,
        "total_revenue_cents": cash_total + mpesa_total + card_total,
        "expected_cash_cents": expected_cash,
        "closing_counted_cents": till.closing_counted_cents,
        "variance_cents": till.variance_cents,
        "variance_reason": till.variance_reason,
        "order_count": len(orders),
    }


@router.post("/tills/{till_id}/close", response_model=schemas.TillSessionOut)
async def close_till(
    till_id: int,
    body: schemas.TillSessionClose,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    till = db.query(models.TillSession).filter(
        models.TillSession.id == till_id,
        models.TillSession.restaurant_id == restaurant.id,
    ).first()
    if not till:
        raise HTTPException(status_code=404, detail="Till session not found")

    now = utcnow()
    orders = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant.id,
        models.Order.created_at >= till.opened_at,
        models.Order.created_at <= now,
        models.Order.status != models.OrderStatus.CANCELLED,
    ).all()
    cash_total = sum(o.total or 0 for o in orders if o.payment_method == models.PaymentMethod.CASH and o.is_paid)
    expected_cash = till.opening_float_cents + cash_total
    variance = body.closing_counted_cents - expected_cash

    till.closed_at = now
    till.status = "closed"
    till.closing_counted_cents = body.closing_counted_cents
    till.expected_cash_cents = expected_cash
    till.variance_cents = variance
    till.variance_reason = body.variance_reason or ""
    if body.notes:
        till.notes = f"{till.notes}\n{body.notes}".strip()

    db.commit()
    db.refresh(till)
    return _till_to_dict(till, current_user)


@router.get("/tills/history", response_model=List[schemas.TillSessionOut])
async def list_till_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    tills = db.query(models.TillSession).filter(
        models.TillSession.restaurant_id == restaurant.id
    ).order_by(models.TillSession.opened_at.desc()).limit(50).all()
    return [_till_to_dict(t, current_user) for t in tills]


def _till_to_dict(till: models.TillSession, user: models.User) -> dict:
    return {
        "id": till.id,
        "user_id": till.user_id,
        "user_name": user.display_name or user.email,
        "opening_float_cents": till.opening_float_cents or 0,
        "closing_counted_cents": till.closing_counted_cents,
        "expected_cash_cents": till.expected_cash_cents,
        "variance_cents": till.variance_cents,
        "variance_reason": till.variance_reason or "",
        "status": till.status or "open",
        "opened_at": till.opened_at,
        "closed_at": till.closed_at,
        "notes": till.notes or "",
    }


def _trigger_mpesa_stk_push(db: Session, order: models.Order) -> None:
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


def _order_to_dict(order: models.Order) -> dict:
    """Convert Order model to dict matching OrderOut schema."""
    items_out = []
    for oi in (order.items or []):
        item_name = ""
        if oi.menu_item:
            item_name = oi.menu_item.name
        
        mods_out = []
        for mod in (oi.modifiers or []):
            mods_out.append({
                "id": mod.id,
                "name": mod.name,
                "price_delta_cents": mod.price_delta_cents,
            })

        items_out.append({
            "id": oi.id,
            "menu_item_id": oi.menu_item_id,
            "quantity": oi.quantity,
            "unit_price": oi.unit_price,
            "item_name": item_name,
            "is_voided": bool(oi.is_voided),
            "void_reason": oi.void_reason or "",
            "notes": oi.notes or "",
            "modifiers": mods_out,
        })

    payments_out = []
    for p in (order.payments or []):
        payments_out.append({
            "id": p.id,
            "payment_method": p.payment_method,
            "amount_cents": p.amount_cents,
            "reference": p.reference or "",
            "created_at": p.created_at,
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
        "discount_cents": order.discount_cents or 0,
        "discount_reason": order.discount_reason or "",
        "void_reason": order.void_reason or "",
        "refund_cents": order.refund_cents or 0,
        "refund_reason": order.refund_reason or "",
        "tax_cents": order.tax_cents or 0,
        "service_charge_cents": order.service_charge_cents or 0,
        "created_at": order.created_at,
        "completed_at": order.completed_at,
        "items": items_out,
        "payments": payments_out,
        "attributed_user_id": order.attributed_user_id,
    }

