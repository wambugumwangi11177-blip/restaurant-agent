"""
backend/routers/staff.py
──────────────────────────
Staff roster + role assignment (directive 015).

Manager-vs-Owner boundary on who can grant which tier: an Owner can assign
any of the 7 tiers; a Manager can only assign tiers below Manager (Supervisor
downward) — a Manager cannot mint another Manager or an Owner. This isn't
spelled out as a literal rule in directive 015's matrix, but follows directly
from its stated principle ("no default that silently grants more access than
intended") extended to grantor privilege — otherwise a Manager could
self-escalate peers indefinitely. Documented here so it isn't re-litigated
per call site.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models
import schemas
import auth
from routers.deps import get_or_create_restaurant
from ai.evaluation.tracker import write_audit_log
from phone_utils import normalize_phone

router = APIRouter(prefix="/staff", tags=["staff"])

# Tiers a Manager (not Owner) is allowed to grant. Manager and Owner
# themselves are excluded — see module docstring.
_MANAGER_GRANTABLE = {
    models.StaffRole.SUPERVISOR,
    models.StaffRole.CONTROLLER,
    models.StaffRole.STOCKKEEPER,
    models.StaffRole.KITCHEN,
    models.StaffRole.WAITER,
}


def _staff_out(member: models.StaffMember, db: Session) -> dict:
    linked_role = None
    if member.user_id:
        linked_user = db.query(models.User).filter(models.User.id == member.user_id).first()
        if linked_user and linked_user.staff_role:
            linked_role = linked_user.staff_role.value
    return {
        "id": member.id,
        "restaurant_id": member.restaurant_id,
        "user_id": member.user_id,
        "name": member.name,
        "role_title": member.role_title,
        "hourly_rate": member.hourly_rate,
        "phone": member.phone,
        "is_active": member.is_active,
        "staff_role": linked_role,
    }


def _parse_staff_role(value: str) -> models.StaffRole:
    try:
        return models.StaffRole[value.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown staff role: {value}")


def _require_grant_allowed(granter: models.User, target_role: models.StaffRole) -> None:
    """Owner (Role.ADMIN) may grant any tier. A Manager-tier user may only
    grant tiers in _MANAGER_GRANTABLE. Anyone else shouldn't reach this
    function at all (the route dependency already blocks them)."""
    if granter.role in (models.Role.SUPERADMIN, models.Role.ADMIN):
        return
    if target_role not in _MANAGER_GRANTABLE:
        raise HTTPException(
            status_code=403,
            detail="Only an Owner can grant the Owner or Manager tier.",
        )


@router.get("/", response_model=List[schemas.StaffMemberOut])
async def list_staff(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_staff_role(models.StaffRole.MANAGER)
    ),
):
    restaurant = get_or_create_restaurant(db, current_user)
    members = db.query(models.StaffMember).filter(
        models.StaffMember.restaurant_id == restaurant.id
    ).order_by(models.StaffMember.name).all()
    return [_staff_out(m, db) for m in members]


@router.post("/", response_model=schemas.StaffMemberOut)
async def create_staff(
    body: schemas.StaffMemberCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_staff_role(models.StaffRole.MANAGER)
    ),
):
    restaurant = get_or_create_restaurant(db, current_user)

    linked_user = None
    if body.create_login:
        if not body.email or not body.password or not body.staff_role:
            raise HTTPException(
                status_code=400,
                detail="email, password, and staff_role are all required when create_login is true.",
            )
        auth.require_strong_password(body.password)
        target_role = _parse_staff_role(body.staff_role)
        _require_grant_allowed(current_user, target_role)

        if db.query(models.User).filter(models.User.email == body.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")

        linked_user = models.User(
            email=body.email,
            hashed_password=auth.get_password_hash(body.password),
            role=models.Role.STAFF,
            staff_role=target_role,
            tenant_id=current_user.tenant_id,
        )
        db.add(linked_user)
        db.commit()
        db.refresh(linked_user)

    member = models.StaffMember(
        restaurant_id=restaurant.id,
        user_id=linked_user.id if linked_user else None,
        name=body.name,
        role_title=body.role_title,
        hourly_rate=body.hourly_rate,
        # Normalized on write so it matches the normalized inbound WhatsApp/SMS
        # number at compare time (same reasoning as RestaurantUpdate.owner_phone
        # in routers/auth.py — storing the raw form would silently break
        # webhooks._resolve_staff_by_phone).
        phone=normalize_phone(body.phone) if body.phone else None,
    )
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        # uq_staff_members_restaurant_phone (migration 030).
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A staff member with this phone number already exists at this restaurant.",
        )
    db.refresh(member)

    if linked_user:
        write_audit_log(
            db, restaurant.id, "staff_role_assigned", "staff_router",
            entity_type="user", entity_id=linked_user.id,
            after={"staff_role": linked_user.staff_role.value, "staff_member_id": member.id},
            reasoning=f"Staff member '{member.name}' created with login and role {linked_user.staff_role.value}.",
            approved_by=current_user.email,
        )

    return _staff_out(member, db)


@router.put("/{staff_id}", response_model=schemas.StaffMemberOut)
async def update_staff(
    staff_id: int,
    body: schemas.StaffMemberUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_staff_role(models.StaffRole.MANAGER)
    ),
):
    restaurant = get_or_create_restaurant(db, current_user)
    member = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.restaurant_id == restaurant.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")

    was_active = member.is_active
    updates = body.dict(exclude_unset=True)
    if "phone" in updates and updates["phone"]:
        updates["phone"] = normalize_phone(updates["phone"])
    for key, value in updates.items():
        setattr(member, key, value)

    # Deactivation must revoke an existing login immediately (directive 016 —
    # this was a real gap: StaffMember.is_active previously had no downstream
    # effect on the linked User's ability to log in or keep an existing
    # session). Reuses the same token_version bump as /auth/logout-all.
    if was_active and member.is_active is False and member.user_id:
        linked_user = db.query(models.User).filter(models.User.id == member.user_id).first()
        if linked_user:
            linked_user.is_active = False
            linked_user.token_version = (linked_user.token_version or 0) + 1
            write_audit_log(
                db, restaurant.id, "staff_deactivated", "staff_router",
                entity_type="user", entity_id=linked_user.id,
                reasoning=f"Staff member '{member.name}' deactivated — login revoked immediately.",
                approved_by=current_user.email,
            )
    elif not was_active and member.is_active and member.user_id:
        linked_user = db.query(models.User).filter(models.User.id == member.user_id).first()
        if linked_user:
            linked_user.is_active = True

    try:
        db.commit()
    except IntegrityError:
        # uq_staff_members_restaurant_phone (migration 030).
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A staff member with this phone number already exists at this restaurant.",
        )
    db.refresh(member)
    return _staff_out(member, db)


@router.post("/{staff_id}/assign-role", response_model=schemas.StaffMemberOut)
async def assign_role(
    staff_id: int,
    body: schemas.StaffRoleAssign,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.require_staff_role(models.StaffRole.MANAGER)
    ),
):
    """Explicit role (re)assignment, separate from create — covers both the
    initial grant for a StaffMember created without create_login, and later
    promotions/demotions. Every change is audit-logged (directive 015's Edge
    Cases: role changes must be traceable — this is the theft/risk workstream's
    "who had access" answer)."""
    restaurant = get_or_create_restaurant(db, current_user)
    member = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.restaurant_id == restaurant.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if not member.user_id:
        raise HTTPException(
            status_code=400,
            detail="This staff member has no login — nothing to assign a role to.",
        )

    target_role = _parse_staff_role(body.staff_role)
    _require_grant_allowed(current_user, target_role)

    linked_user = db.query(models.User).filter(models.User.id == member.user_id).first()
    if not linked_user:
        raise HTTPException(status_code=404, detail="Linked user account not found")

    before_role = linked_user.staff_role.value if linked_user.staff_role else None
    linked_user.staff_role = target_role
    db.commit()

    write_audit_log(
        db, restaurant.id, "staff_role_assigned", "staff_router",
        entity_type="user", entity_id=linked_user.id,
        before={"staff_role": before_role},
        after={"staff_role": target_role.value},
        reasoning=f"Role changed for '{member.name}': {before_role} -> {target_role.value}.",
        approved_by=current_user.email,
    )

    db.refresh(member)
    return _staff_out(member, db)
