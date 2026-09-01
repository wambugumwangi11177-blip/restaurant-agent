"""
backend/routers/enterprise.py
───────────────────────────────
Enterprise administration endpoints (Phase 10): cross-location benchmarking and
the organization-wide audit center. ADMIN-gated, and every request is checked to
belong to the caller's own tenant — a chain owner can never read another tenant's
organization.
"""

from time_utils import utcnow
from routers.deps import get_or_create_restaurant
from typing import List, Optional
from pydantic import BaseModel
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import require_role
import auth
import models

logger = logging.getLogger("enterprise.router")

router = APIRouter(prefix="/enterprise", tags=["enterprise"])


def _org_in_tenant(db: Session, organization_id: int, tenant_id: int) -> bool:
    """An organization is only visible to its own tenant."""
    org = (
        db.query(models.Organization.id)
        .filter(models.Organization.id == organization_id,
                models.Organization.tenant_id == tenant_id)
        .first()
    )
    return org is not None


@router.get("/organizations")
async def list_organizations(
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Organizations belonging to the caller's tenant."""
    orgs = (
        db.query(models.Organization)
        .filter(models.Organization.tenant_id == current_user.tenant_id)
        .all()
    )
    return {"organizations": [{"id": o.id, "name": o.name} for o in orgs]}


@router.get("/benchmark")
async def benchmark(
    organization_id: int,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Cross-location KPI benchmark for one organization (tenant-scoped)."""
    if not _org_in_tenant(db, organization_id, current_user.tenant_id):
        return {"available": False, "error": "Organization not found."}
    from ai.enterprise import benchmark_organization
    return benchmark_organization(db, organization_id)


@router.get("/audit")
async def audit_center(
    organization_id: int,
    days: int = 30,
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """Organization-wide AI governance audit center (tenant-scoped)."""
    if not _org_in_tenant(db, organization_id, current_user.tenant_id):
        return {"available": False, "error": "Organization not found."}
    days = min(max(days, 1), 365)
    from ai.enterprise import org_audit_center
    return org_audit_center(db, organization_id, days=days)


# ─────────────────────────────────────────────────────────────────────────────
# PURCHASING & SUPPLIERS (Pass B7)
# ─────────────────────────────────────────────────────────────────────────────


class SupplierCreate(BaseModel):
    name: str
    contact_phone: str = ""
    contact_email: str = ""
    avg_lead_days: float = 1.0
    notes: str = ""


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    inventory_item_id: Optional[int] = None
    quantity_ordered: float
    unit: str = "kg"
    cost_per_unit: int = 0  # Cents
    expected_days: int = 1
    notes: str = ""


class PurchaseOrderReceive(BaseModel):
    quantity_received: float
    cost_per_unit: Optional[int] = None
    notes: str = ""


@router.get("/purchasing/suppliers")
async def list_suppliers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    suppliers = db.query(models.Supplier).filter(
        models.Supplier.restaurant_id == restaurant.id,
        models.Supplier.is_active == True,
    ).all()
    return suppliers


@router.post("/purchasing/suppliers")
async def create_supplier(
    body: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    supplier = models.Supplier(
        restaurant_id=restaurant.id,
        name=body.name,
        contact_phone=body.contact_phone,
        contact_email=body.contact_email,
        avg_lead_days=body.avg_lead_days,
        notes=body.notes,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/purchasing/orders")
async def list_purchase_orders(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    q = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.restaurant_id == restaurant.id
    )
    if status:
        q = q.filter(models.PurchaseOrder.status == status)

    orders = q.order_by(
        models.PurchaseOrder.ordered_at.desc()).limit(100).all()

    # Mark overdue
    now = utcnow()
    results = []
    overdue_count = 0

    for po in orders:
        is_overdue = False
        days_overdue = 0
        if po.status in ["PENDING", "SENT"] and po.expected_at:
            if now > po.expected_at:
                is_overdue = True
                days_overdue = (now - po.expected_at).days
                overdue_count += 1

        results.append({
            "id": po.id,
            "supplier_id": po.supplier_id,
            "supplier_name": po.supplier.name if po.supplier else "Unknown",
            "inventory_item_id": po.inventory_item_id,
            "item_name": po.inventory_item.item_name if po.inventory_item else "General Supplies",
            "quantity_ordered": po.quantity_ordered,
            "quantity_received": po.quantity_received,
            "unit": po.unit,
            "cost_per_unit": po.cost_per_unit,
            "total_cost": po.total_cost,
            "status": po.status,
            "ordered_at": po.ordered_at,
            "expected_at": po.expected_at,
            "delivered_at": po.delivered_at,
            "is_overdue": is_overdue,
            "days_overdue": days_overdue,
            "notes": po.notes or "",
        })

    return {
        "orders": results,
        "overdue_count": overdue_count,
        "total_orders": len(orders),
    }


@router.post("/purchasing/orders")
async def create_purchase_order(
    body: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    supplier = db.query(models.Supplier).filter(
        models.Supplier.id == body.supplier_id,
        models.Supplier.restaurant_id == restaurant.id,
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    import datetime as dt
    now = utcnow()
    expected = now + dt.timedelta(days=body.expected_days)
    total_cost = int(body.quantity_ordered * body.cost_per_unit)

    po = models.PurchaseOrder(
        restaurant_id=restaurant.id,
        supplier_id=supplier.id,
        inventory_item_id=body.inventory_item_id,
        quantity_ordered=body.quantity_ordered,
        unit=body.unit,
        cost_per_unit=body.cost_per_unit,
        total_cost=total_cost,
        status="SENT",
        ordered_at=now,
        expected_at=expected,
        notes=body.notes or "",
    )
    db.add(po)
    db.commit()
    db.refresh(po)
    return {"id": po.id, "status": po.status, "message": "Purchase order created and sent"}


@router.post("/purchasing/orders/{po_id}/receive")
async def receive_purchase_order(
    po_id: int,
    body: PurchaseOrderReceive,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    restaurant = get_or_create_restaurant(db, current_user)
    po = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.id == po_id,
        models.PurchaseOrder.restaurant_id == restaurant.id,
    ).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    po.quantity_received = (po.quantity_received or 0) + body.quantity_received
    po.delivered_at = utcnow()
    if body.cost_per_unit is not None:
        po.cost_per_unit = body.cost_per_unit
        po.total_cost = int(po.quantity_received * body.cost_per_unit)

    if po.quantity_received >= po.quantity_ordered:
        po.status = "DELIVERED"
    else:
        po.status = "PARTIAL"

    # Increment inventory on-hand if linked to an item
    if po.inventory_item_id:
        item = db.query(models.InventoryItem).filter(
            models.InventoryItem.id == po.inventory_item_id,
            models.InventoryItem.restaurant_id == restaurant.id,
        ).first()
        if item:
            item.quantity = (item.quantity or 0) + body.quantity_received
            if body.cost_per_unit:
                item.cost_per_unit = body.cost_per_unit / 100.0
            db.add(models.StockMovement(
                inventory_item_id=item.id,
                movement_type=models.StockMovementType.IN,
                quantity=body.quantity_received,
                reason=f"Received against PO #{po.id} from {po.supplier.name if po.supplier else 'Supplier'}",
                user_id=current_user.id,
            ))

    db.commit()
    return {"id": po.id, "status": po.status, "quantity_received": po.quantity_received}


@router.post("/purchasing/orders/{po_id}/cancel")
async def cancel_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role(models.Role.ADMIN)),
):
    restaurant = get_or_create_restaurant(db, current_user)
    po = db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.id == po_id,
        models.PurchaseOrder.restaurant_id == restaurant.id,
    ).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    po.status = "CANCELLED"
    db.commit()
    return {"id": po.id, "status": "CANCELLED"}
