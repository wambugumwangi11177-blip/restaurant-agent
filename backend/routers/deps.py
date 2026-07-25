"""
backend/routers/deps.py
─────────────────────────
Shared FastAPI dependencies. Extracted 2026-07-07: the "find this user's
restaurant" lookup had drifted into 4 near-identical copies (ai.py,
inventory.py, orders.py, reservations.py) plus 4 more inline query blocks
(menu.py x2, auth.py x2, analytics.py) — a DRY violation, and worse, an
inconsistency: some copies auto-created a missing restaurant, one raised 404,
one silently returned 0. Auto-create is the correct behavior (the majority
pattern, and it matches auth.py's register() already guaranteeing every new
user gets a restaurant) — a 404/silent-0 here would only ever fire for data
that shouldn't exist under normal signup flow, so failing soft is safer than
failing loud for what should be an impossible case.
"""

from sqlalchemy.orm import Session
import models


def get_or_create_restaurant(db: Session, user: models.User) -> models.Restaurant:
    """Get the restaurant for the current user's tenant, creating one if missing."""
    restaurant = get_restaurant_or_none(db, user)
    if not restaurant:
        restaurant = models.Restaurant(
            name=f"{user.tenant.name}'s Restaurant",
            tenant_id=user.tenant_id,
        )
        db.add(restaurant)
        db.commit()
        db.refresh(restaurant)
    return restaurant


def get_restaurant_or_none(db: Session, user: models.User) -> models.Restaurant | None:
    """
    Read-only lookup — never creates. For GET endpoints where auto-creating
    a restaurant as a side effect would violate command-query separation
    (e.g. GET /me should never write data just by being called).

    Multi-restaurant tenants (audit remediation, Tier 5 item 11 — this
    function used to always return the tenant's first restaurant with no way
    for a chain owner to pick a different one, tracked as tech-debt D4): if
    `user.active_restaurant_id` is set via POST /restaurants/select AND still
    belongs to this user's own tenant, that restaurant is returned. Otherwise
    falls back to the tenant's first restaurant by id — the exact behavior
    this function always had for every single-restaurant tenant (the
    overwhelming majority), now an explicit, deterministic default rather
    than an accidental one.
    """
    if user.active_restaurant_id is not None:
        selected = db.query(models.Restaurant).filter(
            models.Restaurant.id == user.active_restaurant_id,
            models.Restaurant.tenant_id == user.tenant_id,
        ).first()
        if selected:
            return selected
    return db.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == user.tenant_id
    ).order_by(models.Restaurant.id).first()


def list_restaurants_for_tenant(db: Session, user: models.User) -> "list[models.Restaurant]":
    """Every restaurant belonging to this user's tenant, ordered by id — the
    source list for GET /restaurants (audit remediation, Tier 5 item 11).
    Length 1 for the overwhelming majority of tenants; the frontend switcher
    only renders when this returns more than one."""
    return db.query(models.Restaurant).filter(
        models.Restaurant.tenant_id == user.tenant_id
    ).order_by(models.Restaurant.id).all()


def get_staff_users_for_restaurant(
    db: Session, restaurant: models.Restaurant, staff_roles: "list[models.StaffRole]"
) -> "list[models.User]":
    """
    The reverse of get_restaurant_or_none: every active dashboard login at
    this restaurant's tenant whose staff_role is one of staff_roles. Added
    for ai/notify.py's role-based fan-out (directive 016 flagged that no
    per-staff/per-role notification routing existed at all — this is that
    lookup). Belongs here, not inline in the caller, per this file's own
    rationale above (near-identical restaurant/user lookups scattered across
    routers is the exact DRY violation this module was extracted to fix).
    """
    return db.query(models.User).filter(
        models.User.tenant_id == restaurant.tenant_id,
        models.User.staff_role.in_(staff_roles),
        models.User.is_active == True,  # noqa: E712 - SQLAlchemy filter, not a Python bool compare
    ).all()
