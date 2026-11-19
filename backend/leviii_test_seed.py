"""Idempotent Eleven test stack for Jack deployments (env-gated).

Set SEED_TEST_DATA=1 and SEED_OWNER_PASSWORD on test stacks only. Production
leaves both unset — this module is a no-op.
"""
from __future__ import annotations

import logging
import os

import auth
import models
from fastapi import HTTPException
from models import Role, StaffRole, StaffSetupProgress
from routers.store_intake import ensure_zones
from sqlalchemy.orm import Session

logger = logging.getLogger("leviii_test_seed")

ELEVEN = "Eleven"
OWNER_EMAIL = "owner@eleven.leviii"
STAFF = (
    ("jack@eleven.leviii", StaffRole.STOCKKEEPER, "Jack"),
    ("amina@eleven.leviii", StaffRole.CONTROLLER, "Amina"),
)


class SeedError(Exception):
    pass


def ensure_eleven_test_data(db: Session, owner_password: str) -> list[str]:
    """Create Eleven owner, Jack, accountant, zones, and a little stock if missing."""
    try:
        auth.require_strong_password(owner_password)
    except HTTPException as exc:
        raise SeedError(exc.detail) from exc

    log: list[str] = []
    tenant = db.query(models.Tenant).filter(models.Tenant.name == ELEVEN).first()
    if tenant is None:
        tenant = models.Tenant(name=ELEVEN)
        db.add(tenant)
        db.flush()
        log.append(f"[CREATED] tenant {ELEVEN!r}")
    else:
        log.append(f"[EXISTS] tenant {ELEVEN!r}")

    restaurant = db.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).first()
    if restaurant is None:
        restaurant = models.Restaurant(tenant_id=tenant.id, name=ELEVEN, address="Ngong Road")
        db.add(restaurant)
        db.flush()
        log.append("[CREATED] restaurant Eleven")
    else:
        log.append("[EXISTS] restaurant Eleven")

    owner = db.query(models.User).filter(models.User.email == OWNER_EMAIL).first()
    if owner is None:
        owner = models.User(
            email=OWNER_EMAIL,
            hashed_password=auth.get_password_hash(owner_password),
            role=Role.ADMIN,
            staff_role=StaffRole.OWNER,
            tenant_id=tenant.id,
            must_change_password=False,
            is_email_verified=True,
            is_active=True,
        )
        db.add(owner)
        log.append(f"[CREATED] owner {OWNER_EMAIL}")
    else:
        owner.role = Role.ADMIN
        owner.staff_role = StaffRole.OWNER
        owner.is_active = True
        log.append(f"[EXISTS] owner {OWNER_EMAIL} (password unchanged)")
    owner.active_restaurant_id = restaurant.id

    for email, role, name in STAFF:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is None:
            user = models.User(
                email=email,
                hashed_password=None,
                role=Role.STAFF,
                staff_role=role,
                tenant_id=tenant.id,
                must_change_password=True,
                is_active=True,
            )
            db.add(user)
            db.flush()
            db.add(StaffSetupProgress(user_id=user.id, restaurant_id=restaurant.id))
            log.append(f"[CREATED] staff login {email}")
        else:
            log.append(f"[EXISTS] staff login {email}")
        if (
            db.query(models.StaffMember)
            .filter(models.StaffMember.restaurant_id == restaurant.id, models.StaffMember.user_id == user.id)
            .first()
            is None
        ):
            db.add(
                models.StaffMember(
                    restaurant_id=restaurant.id,
                    user_id=user.id,
                    name=name,
                    role_title=role.value,
                )
            )
            log.append(f"[CREATED] staff member {name}")

    zones_before = db.query(models.StockZone).filter(models.StockZone.restaurant_id == restaurant.id).count()
    ensure_zones(db, restaurant.id)
    if zones_before == 0:
        log.append("[CREATED] default storage zones")

    if (
        db.query(models.InventoryItem)
        .filter(models.InventoryItem.restaurant_id == restaurant.id)
        .first()
        is None
    ):
        db.add(
            models.InventoryItem(
                restaurant_id=restaurant.id,
                item_name="Rice",
                quantity=12,
                unit="kg",
                cost_per_unit=0,
                low_stock_threshold=2,
            )
        )
        log.append("[CREATED] sample stock (Rice)")

    if db.query(models.Supplier).filter(models.Supplier.restaurant_id == restaurant.id).first() is None:
        db.add(
            models.Supplier(
                restaurant_id=restaurant.id,
                name="Fresh Farm",
                contact_phone="0700111222",
                contact_email="",
                notes="Sample supplier for Jack test",
            )
        )
        log.append("[CREATED] sample supplier")

    db.commit()
    return log


def provision_test_data_from_env() -> None:
    flag = os.getenv("SEED_TEST_DATA", "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return
    password = os.getenv("SEED_OWNER_PASSWORD", "")
    if not password:
        logger.warning("[eleven-seed] SEED_TEST_DATA is set but SEED_OWNER_PASSWORD is missing — skipped")
        return

    from database import SessionLocal

    db = SessionLocal()
    try:
        for line in ensure_eleven_test_data(db, password):
            logger.info("[eleven-seed] %s", line)
    except Exception as exc:
        db.rollback()
        logger.warning("[eleven-seed] skipped: %s", exc)
    finally:
        db.close()