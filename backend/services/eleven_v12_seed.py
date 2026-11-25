"""Rich Eleven data-stack catalogue for owner v12 screenshots (test only)."""
from __future__ import annotations

from datetime import timedelta

import models
from models import OrderStatus, OrderType, PaymentMethod
from sqlalchemy.orm import Session
from time_utils import utcnow

import storage
from ai.reorder import draft_purchase_order, find_reorder_candidates
from services.restock_workflow import attach_draft_to_notes, build_invoice_draft
from services.reorder_points import sync_restaurant

_MARKER = "[V12-DEMO]"
_DISHES = (
    ("Pilau", 45000, 14000, "Rice Bowls"),
    ("Nyama Choma", 85000, 32000, "Grill"),
    ("Chapati", 8000, 2500, "Sides"),
    ("Sukuma Wiki", 12000, 3500, "Sides"),
    ("Mandazi", 6000, 1800, "Bakery"),
    ("Beef Stew", 55000, 21000, "Kitchen"),
    ("Chicken Curry", 52000, 19500, "Kitchen"),
    ("Githeri", 38000, 12000, "Kitchen"),
    ("Samosa (3)", 15000, 4500, "Snacks"),
    ("Coconut Fish", 72000, 28000, "Grill"),
    ("Ugali", 10000, 2800, "Sides"),
    ("Kachumbari", 9000, 2200, "Salads"),
)
_STOCK = (
    ("Rice", "kg", 4.5, 25, 5, 560),
    ("Cooking oil", "L", 8.0, 20, 4, 420),
    ("Onions", "kg", 6.0, 15, 3, 85),
    ("Tomatoes", "kg", 5.5, 18, 4, 120),
    ("Beef trim", "kg", 3.0, 12, 2, 890),
    ("Chicken", "kg", 4.0, 14, 3, 650),
    ("Maize flour", "kg", 10.0, 30, 6, 95),
    ("Coconut milk", "L", 6.0, 16, 3, 310),
    ("Cabbage", "kg", 7.0, 12, 3, 45),
    ("Potatoes", "kg", 9.0, 22, 5, 75),
    ("Wheat flour", "kg", 8.0, 18, 4, 110),
    ("Spices mix", "kg", 2.0, 6, 1, 1200),
    ("Fish fillet", "kg", 2.5, 8, 2, 950),
    ("Cooking gas", "kg", 12.0, 20, 5, 180),
    ("Tea leaves", "kg", 3.0, 8, 2, 450),
)
_SUPPLIERS = (
    ("Fresh Farm", 2.0, 96.0, ""),
    ("City Produce", 1.5, 91.0, ""),
    ("Nairobi Meats", 3.0, 88.0, ""),
    ("Coast Seafood", 2.5, 84.0, "[DEMO-PRICE-JUMP]"),
    ("Bakery Direct", 1.0, 93.0, ""),
)


def seed_v12_catalog(
    db: Session,
    restaurant: models.Restaurant,
    jack: models.User | None,
    log: list[str],
    demo_jpeg: bytes,
) -> models.MenuItem | None:
    """Idempotent rich demo data for owner@eleven.leviii."""
    now = utcnow()
    suppliers: list[models.Supplier] = []
    for name, lead, score, notes in _SUPPLIERS:
        row = (
            db.query(models.Supplier)
            .filter(models.Supplier.restaurant_id == restaurant.id, models.Supplier.name == name)
            .first()
        )
        if row is None:
            row = models.Supplier(restaurant_id=restaurant.id, name=name, notes=notes, brings="Main food")
            db.add(row)
            db.flush()
        row.avg_lead_days = lead
        row.reliability_score = score
        row.notes = notes
        suppliers.append(row)
    if suppliers:
        log.append(f"[V12] {len(suppliers)} suppliers with reliability")

    inv_by_name: dict[str, models.InventoryItem] = {}
    for idx, (name, unit, qty, par, low, cost) in enumerate(_STOCK):
        item = (
            db.query(models.InventoryItem)
            .filter(models.InventoryItem.restaurant_id == restaurant.id, models.InventoryItem.item_name == name)
            .first()
        )
        if item is None:
            item = models.InventoryItem(restaurant_id=restaurant.id, item_name=name, unit=unit)
            db.add(item)
            db.flush()
        item.quantity = qty
        item.par_level = par
        item.low_stock_threshold = low
        item.cost_per_unit = cost
        item.default_supplier_id = suppliers[idx % len(suppliers)].id
        inv_by_name[name] = item
    log.append(f"[V12] {len(_STOCK)} stock lines with par levels")

    pilau_item: models.MenuItem | None = None
    menu_ids: list[models.MenuItem] = []
    for name, price, cost, category in _DISHES:
        dish = (
            db.query(models.MenuItem)
            .filter(models.MenuItem.restaurant_id == restaurant.id, models.MenuItem.name == name)
            .first()
        )
        if dish is None:
            dish = models.MenuItem(
                restaurant_id=restaurant.id,
                name=name,
                category=category,
                price=price,
                cost_price=cost,
            )
            db.add(dish)
            db.flush()
        else:
            dish.price = price
            dish.cost_price = cost
            dish.category = category
        menu_ids.append(dish)
        if name == "Pilau":
            pilau_item = dish
        key_ing = "Rice" if name in ("Pilau", "Githeri") else "Onions"
        ing_item = inv_by_name.get(key_ing) or inv_by_name["Rice"]
        if not db.query(models.MenuIngredient).filter_by(menu_item_id=dish.id, inventory_item_id=ing_item.id).first():
            db.add(
                models.MenuIngredient(
                    menu_item_id=dish.id,
                    inventory_item_id=ing_item.id,
                    quantity_per_serving=0.2 if key_ing == "Rice" else 0.05,
                    recipe_unit=ing_item.unit,
                    yield_fraction=1.0,
                )
            )
    log.append(f"[V12] {len(_DISHES)} menu dishes with recipe links")

    marker = f"{_MARKER}-SALES-90D"
    for day in range(90):
        when = now - timedelta(days=day)
        if db.query(models.Order.id).filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.notes == f"{marker} day-{day}",
        ).first():
            continue
        weekend = when.weekday() >= 4
        dish = menu_ids[(day + weekend) % len(menu_ids)]
        alt = menu_ids[(day * 3 + 1) % len(menu_ids)]
        qty = (10 if weekend else 6) + (day % 5)
        qty2 = 2 + (day % 3)
        pay = PaymentMethod.MPESA if day % 3 == 0 else PaymentMethod.CASH
        otype = OrderType.DELIVERY if day % 4 == 0 else OrderType.DINE_IN
        line_total = qty * dish.price + qty2 * alt.price
        stamped = when.replace(hour=12 + (day % 8), minute=(day * 11) % 60)
        order = models.Order(
            restaurant_id=restaurant.id,
            status=OrderStatus.SERVED,
            order_type=otype,
            is_paid=True,
            payment_method=pay,
            total=line_total,
            notes=f"{marker} day-{day}",
            created_at=stamped,
        )
        db.add(order)
        db.flush()
        db.add(models.OrderItem(order_id=order.id, menu_item_id=dish.id, quantity=qty, unit_price=dish.price))
        db.add(models.OrderItem(order_id=order.id, menu_item_id=alt.id, quantity=qty2, unit_price=alt.price))

    if jack:
        for idx, (name, item) in enumerate(inv_by_name.items()):
            marker_use = f"{_MARKER} weekly usage v2 {name}"
            if db.query(models.StockMovement).filter(
                models.StockMovement.inventory_item_id == item.id,
                models.StockMovement.reason == marker_use,
            ).first():
                continue
            weekly = max(0.35, (item.par_level or 8) / 12)
            for week in range(4):
                db.add(
                    models.StockMovement(
                        inventory_item_id=item.id,
                        movement_type=models.StockMovementType.OUT,
                        quantity=round(weekly * (0.85 + (idx + week) % 3 * 0.1), 2),
                        reason=marker_use,
                        performed_by_user_id=jack.id,
                        created_at=now - timedelta(days=week * 7 + 2, hours=idx),
                    )
                )

    for demo_name in ("Pilau (demo)", "Nyama Choma (demo)"):
        demo_dish = (
            db.query(models.MenuItem)
            .filter(models.MenuItem.restaurant_id == restaurant.id, models.MenuItem.name == demo_name)
            .first()
        )
        if demo_dish:
            db.query(models.MenuIngredient).filter(models.MenuIngredient.menu_item_id == demo_dish.id).delete()
            db.delete(demo_dish)
            log.append(f"[V12] removed {demo_name}")

    rice = inv_by_name["Rice"]
    if jack:
        if not db.query(models.StockMovement).filter(
            models.StockMovement.inventory_item_id == rice.id,
            models.StockMovement.reason == f"{_MARKER} kitchen issue",
        ).first():
            db.add(
                models.StockMovement(
                    inventory_item_id=rice.id,
                    movement_type=models.StockMovementType.OUT,
                    quantity=2.8,
                    reason=f"{_MARKER} kitchen issue",
                    performed_by_user_id=jack.id,
                    created_at=now - timedelta(days=1),
                )
            )
        if not db.query(models.StockMovement).filter(
            models.StockMovement.inventory_item_id == rice.id,
            models.StockMovement.reason == f"{_MARKER} sales usage",
        ).first():
            db.add(
                models.StockMovement(
                    inventory_item_id=rice.id,
                    movement_type=models.StockMovementType.OUT,
                    quantity=3.6,
                    reason=f"{_MARKER} sales usage",
                    performed_by_user_id=jack.id,
                    created_at=now - timedelta(hours=6),
                )
            )
        photo_key = f"stock-variance/{restaurant.id}/rice-gap.jpg"
        if not storage.exists(photo_key):
            storage.save(demo_jpeg, key=photo_key, content_type="image/jpeg")
        log.append("[V12] missing-stock gap + photo for Rice")

    sync_restaurant(db, restaurant.id)
    for po in list(
        db.query(models.PurchaseOrder)
        .filter(models.PurchaseOrder.restaurant_id == restaurant.id, models.PurchaseOrder.notes.contains(_MARKER))
        .all()
    ):
        db.delete(po)
    rice.quantity = min(rice.quantity, 1.5)
    db.flush()
    for candidate in find_reorder_candidates(db, restaurant.id)[:4]:
        po = draft_purchase_order(db, restaurant.id, candidate, requested_by_user_id=jack.id if jack else None)
        po.notes = f"{_MARKER} {po.notes or ''}".strip()
        attach_draft_to_notes(po, build_invoice_draft(db, po))
        po.status = "PENDING"
        db.add(po)
    if jack and rice.default_supplier_id:
        legacy = (
            db.query(models.PurchaseOrder)
            .filter(
                models.PurchaseOrder.restaurant_id == restaurant.id,
                models.PurchaseOrder.inventory_item_id == rice.id,
                models.PurchaseOrder.status != "SENT",
            )
            .order_by(models.PurchaseOrder.id.desc())
            .first()
        )
        if legacy is None or legacy.status == "APPROVED":
            po = models.PurchaseOrder(
                restaurant_id=restaurant.id,
                supplier_id=rice.default_supplier_id,
                inventory_item_id=rice.id,
                quantity_ordered=8,
                unit="kg",
                cost_per_unit=56000,
                total_cost=448000,
                status="PENDING",
                notes=f"{_MARKER} Restock Rice for home card",
                requested_by_user_id=jack.id,
            )
            db.add(po)
            db.flush()
            attach_draft_to_notes(po, build_invoice_draft(db, po))
    log.append("[V12] pending reorder POs with invoice drafts")
    db.flush()
    return pilau_item