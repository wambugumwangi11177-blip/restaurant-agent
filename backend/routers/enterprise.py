"""
backend/routers/enterprise.py
───────────────────────────────
Enterprise administration endpoints (Phase 10): cross-location benchmarking and
the organization-wide audit center. ADMIN-gated, and every request is checked to
belong to the caller's own tenant — a chain owner can never read another tenant's
organization.
"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from auth import require_role
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
