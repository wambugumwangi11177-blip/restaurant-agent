"""Idempotent Eleven test stack for Jack deployments (env-gated).

Set SEED_TEST_DATA=1 on test stacks only. Production leaves it unset — no-op.
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
from staff_audit import record_entry

logger = logging.getLogger("leviii_test_seed")

ELEVEN = "Eleven"
TEST_TENANT = "Test Restaurant"
SUPERADMIN_EMAIL = "wambugu@leviii.ai"
TEST_OWNER_EMAIL = "owner@test.restaurant.leviii"
OWNER_EMAIL = "owner@eleven.leviii"
OWNER_RESET_MARKER = "eleven_test_owner_first_login_reset"
STAFF = (
    ("jack@eleven.leviii", StaffRole.STOCKKEEPER, "Jack"),
    ("amina@eleven.leviii", StaffRole.CONTROLLER, "Amina"),
)


class SeedError(Exception):
    pass


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def _reset_marker_applied(db: Session, owner_id: int) -> bool:
    return (
        db.query(models.StaffEntryAudit)
        .filter(
            models.StaffEntryAudit.action == OWNER_RESET_MARKER,
            models.StaffEntryAudit.entity_id == owner_id,
        )
        .first()
        is not None
    )


def ensure_eleven_test_data(
    db: Session,
    owner_password: str,
    *,
    owner_first_login: bool = False,
    owner_reset_first_login: bool = False,
) -> list[str]:
    """Create Eleven owner, Jack, accountant, zones, and a little stock if missing."""
    if not owner_first_login and owner_password:
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
        if owner_first_login:
            hashed = None
            must_change = True
            log.append(f"[CREATED] owner {OWNER_EMAIL} (first login — no password)")
        else:
            if not owner_password:
                raise SeedError("SEED_OWNER_PASSWORD is required when SEED_OWNER_FIRST_LOGIN is off")
            hashed = auth.get_password_hash(owner_password)
            must_change = False
            log.append(f"[CREATED] owner {OWNER_EMAIL}")
        owner = models.User(
            email=OWNER_EMAIL,
            hashed_password=hashed,
            role=Role.ADMIN,
            staff_role=StaffRole.OWNER,
            tenant_id=tenant.id,
            must_change_password=must_change,
            is_email_verified=True,
            is_active=True,
        )
        db.add(owner)
        db.flush()
    else:
        owner.role = Role.ADMIN
        owner.staff_role = StaffRole.OWNER
        owner.is_active = True
        if (
            owner_reset_first_login
            and owner.hashed_password
            and not _reset_marker_applied(db, owner.id)
        ):
            owner.hashed_password = None
            owner.must_change_password = True
            record_entry(
                db,
                restaurant.id,
                owner,
                OWNER_RESET_MARKER,
                "system",
                "Owner password cleared once for Jack test first-login.",
                entity_id=owner.id,
                detail={"email": OWNER_EMAIL},
            )
            log.append(f"[RESET] owner {OWNER_EMAIL} (first login, one-time)")
        else:
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

    # Test Restaurant — proves the data wall (no shared stock with Eleven).
    test_tenant = db.query(models.Tenant).filter(models.Tenant.name == TEST_TENANT).first()
    if test_tenant is None:
        test_tenant = models.Tenant(name=TEST_TENANT)
        db.add(test_tenant)
        db.flush()
        log.append(f"[CREATED] tenant {TEST_TENANT!r}")
    test_restaurant = (
        db.query(models.Restaurant).filter(models.Restaurant.tenant_id == test_tenant.id).first()
    )
    if test_restaurant is None:
        test_restaurant = models.Restaurant(
            tenant_id=test_tenant.id,
            name=TEST_TENANT,
            address="Wall test only",
        )
        db.add(test_restaurant)
        db.flush()
        log.append("[CREATED] restaurant Test Restaurant")
    test_owner = db.query(models.User).filter(models.User.email == TEST_OWNER_EMAIL).first()
    if test_owner is None:
        test_owner = models.User(
            email=TEST_OWNER_EMAIL,
            hashed_password=None,
            role=Role.ADMIN,
            staff_role=StaffRole.OWNER,
            tenant_id=test_tenant.id,
            must_change_password=True,
            is_active=True,
            is_email_verified=True,
        )
        db.add(test_owner)
        db.flush()
        log.append(f"[CREATED] test owner {TEST_OWNER_EMAIL} (first login)")
    test_owner.active_restaurant_id = test_restaurant.id

    super_user = db.query(models.User).filter(models.User.email == SUPERADMIN_EMAIL).first()
    if super_user is None:
        if not owner_password and not owner_first_login:
            log.append(f"[SKIP] super-admin {SUPERADMIN_EMAIL} (needs SEED_OWNER_PASSWORD on first run)")
        else:
            super_user = models.User(
                email=SUPERADMIN_EMAIL,
                hashed_password=auth.get_password_hash(owner_password) if owner_password else None,
                role=Role.SUPERADMIN,
                staff_role=StaffRole.OWNER,
                tenant_id=tenant.id,
                must_change_password=bool(owner_first_login and not owner_password),
                is_active=True,
                is_email_verified=True,
            )
            db.add(super_user)
            log.append(f"[CREATED] super-admin {SUPERADMIN_EMAIL}")
    else:
        super_user.role = Role.SUPERADMIN
        log.append(f"[EXISTS] super-admin {SUPERADMIN_EMAIL}")

    db.commit()
    return log


def provision_test_data_from_env() -> None:
    if not _truthy("SEED_TEST_DATA"):
        return
    owner_first = _truthy("SEED_OWNER_FIRST_LOGIN")
    owner_reset = _truthy("SEED_OWNER_RESET_FIRST_LOGIN")
    password = os.getenv("SEED_OWNER_PASSWORD", "")
    if not owner_first and not password:
        logger.warning(
            "[eleven-seed] SEED_TEST_DATA is set but SEED_OWNER_PASSWORD is missing "
            "(and SEED_OWNER_FIRST_LOGIN is off) — skipped"
        )
        return

    from database import SessionLocal

    db = SessionLocal()
    try:
        for line in ensure_eleven_test_data(
            db,
            password,
            owner_first_login=owner_first,
            owner_reset_first_login=owner_reset,
        ):
            logger.info("[eleven-seed] %s", line)
    except Exception as exc:
        db.rollback()
        logger.warning("[eleven-seed] skipped: %s", exc)
    finally:
        db.close()