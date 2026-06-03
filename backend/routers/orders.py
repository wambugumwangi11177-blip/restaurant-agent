from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/orders", tags=["orders"])


def _get_restaurant(db: Session, user: models.User):
    """Get the restaurant for the current user's tenant."""
    rest = db.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == user.tenant_id
    ).first()
    if not rest:
        rest = models.Restaurant(
            name=f"{user.tenant.name}'s Restaurant",
            tenant_id=user.tenant_id,
        )
        db.add(rest)
        db.commit()
        db.refresh(rest)
    return rest


@router.post("/", response_model=schemas.OrderOut)
async def create_order(
    order: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = _get_restaurant(db, current_user)

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
        items=order_items,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return _order_to_dict(db_order)


@router.get("/", response_model=List[schemas.OrderOut])
async def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = _get_restaurant(db, current_user)
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
    restaurant = _get_restaurant(db, current_user)
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
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        new_status = models.OrderStatus(update.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update.status}")

    order.status = new_status
    if new_status == models.OrderStatus.SERVED:
        order.completed_at = datetime.utcnow()

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
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        order.payment_method = models.PaymentMethod(update.payment_method)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid payment method: {update.payment_method}")

    order.is_paid = update.is_paid
    db.commit()
    db.refresh(order)
    return _order_to_dict(order)


# ── Public endpoint (no auth) for customer ordering ──

@router.post("/public", response_model=schemas.OrderOut)
async def create_public_order(
    order: schemas.OrderCreate,
    restaurant_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """Customer-facing order endpoint — no login required."""
    restaurant = db.query(models.Restaurant).filter(
        models.Restaurant.id == restaurant_id
    ).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

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

    db_order = models.Order(
        restaurant_id=restaurant.id,
        order_type=order_type,
        delivery_channel=models.DeliveryChannel.APP,
        payment_method=models.PaymentMethod.PENDING,
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
    return _order_to_dict(db_order)


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
