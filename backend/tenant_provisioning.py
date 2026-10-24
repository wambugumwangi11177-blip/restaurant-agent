"""Provision the "Demo Restaurant" tenant: an owner login and a restaurant, no data.

Demo Restaurant is a separate client in this multi-tenant app, with the same
owner shell as Vibanda Village (/demo). It records its data directly, so it
never waits on MacSoft (routers/overview.py DIRECT_SOURCE_TENANTS).

Two callers share this:
  * execution/provision_demo_restaurant.py — run by hand against a reachable DB.
  * provision_demo_from_env() — the startup hook. The live Postgres is private
    to Railway, so the tenant is created from inside the service when
    DEMO_RESTAURANT_OWNER_EMAIL and DEMO_RESTAURANT_OWNER_PASSWORD are set.

Idempotent and additive: an existing tenant/restaurant/owner is reused and
nothing is deleted. An existing owner's password is only changed when
reset_password=True, which the startup hook never passes.
"""
import logging
import os
import secrets

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
from models import Restaurant, Role, StaffRole, Tenant, User

logger = logging.getLogger("tenant_provisioning")

DEMO_NAME = "Demo Restaurant"

# Logins for the staff screens in the owner guide. Passwords are never stored
# in the repo: each one is read from its env var, the same way the owner
# password is. The kitchen login is the person who confirms a store issue.
DEMO_STAFF = (
    ("manager", "manager@demo-restaurant.example", StaffRole.MANAGER, "DEMO_RESTAURANT_MANAGER_PASSWORD"),
    ("storekeeper", "store@demo-restaurant.example", StaffRole.STOCKKEEPER, "DEMO_RESTAURANT_STOREKEEPER_PASSWORD"),
    ("kitchen", "kitchen@demo-restaurant.example", StaffRole.KITCHEN, "DEMO_RESTAURANT_KITCHEN_PASSWORD"),
    ("accountant", "accountant@demo-restaurant.example", StaffRole.CONTROLLER, "DEMO_RESTAURANT_ACCOUNTANT_PASSWORD"),
)


class ProvisionError(Exception):
    pass


def upsert_demo_staff(db: Session, tenant: Tenant, restaurant_id: int | None, *, reset_password: bool) -> tuple[dict, list[str]]:
    """Create the demo staff logins. A password env var is applied on create, and on reset when re-seeding.

    When the variable is unset the row is still created (handovers need a person) but its password is random
    and is not logged. An existing password is left alone unless reset_password is set, matching the owner.
    """
    users: dict = {}
    log: list[str] = []
    for key, email, staff_role, env_name in DEMO_STAFF:
        password = os.getenv(env_name, "")
        user = db.query(User).filter(User.email == email).first()
        if user and (tenant is None or user.tenant_id != tenant.id):
            raise ProvisionError(f"{email} is already registered to another tenant.")
        if password:
            try:
                auth.require_strong_password(password)
            except HTTPException as exc:
                raise ProvisionError(f"{env_name}: {exc.detail}") from exc
        if user is None:
            hashed = auth.get_password_hash(password or secrets.token_urlsafe(32))
            user = User(tenant_id=tenant.id, email=email, hashed_password=hashed,
                        role=Role.STAFF, staff_role=staff_role, is_active=True)
            db.add(user)
            db.flush()
            log.append(f"[CREATED] {key} {email}" + ("" if password else " (set " + env_name + " to choose the login password)"))
        else:
            user.role, user.staff_role, user.is_active = Role.STAFF, staff_role, True
            if password and reset_password:
                try:
                    unchanged = auth.verify_password(password, user.hashed_password)
                except Exception:
                    unchanged = False
                # bcrypt uses a new salt on every hash, so re-hashing the same password
                # looks like a change. Leave it when it already matches.
                if unchanged:
                    log.append(f"[EXISTS]  {key} {email} (password unchanged)")
                else:
                    user.hashed_password = auth.get_password_hash(password)
                    user.failed_login_attempts, user.locked_until = 0, None
                    log.append(f"[UPDATED] {key} {email} (password reset from {env_name})")
            else:
                log.append(f"[EXISTS]  {key} {email}" + ("" if password else " (password unchanged; " + env_name + " is unset)"))
        if restaurant_id:
            user.active_restaurant_id = restaurant_id
        users[key] = user
    return users, log


def ensure_demo_restaurant(db: Session, owner_email: str, owner_password: str,
                           reset_password: bool = False) -> list[str]:
    """Create or reuse the Demo Restaurant tenant, restaurant and owner. Commits."""
    try:
        auth.require_strong_password(owner_password)
    except HTTPException as exc:
        raise ProvisionError(exc.detail) from exc

    log: list[str] = []
    tenant = db.query(Tenant).filter(func.lower(Tenant.name) == DEMO_NAME.lower()).first()
    # Restaurant login resolves the owner by restaurant name, so the name must
    # be unique across tenants or nobody can sign in.
    clash = db.query(Restaurant).filter(
        func.lower(Restaurant.name) == DEMO_NAME.lower(),
        Restaurant.tenant_id != (tenant.id if tenant else -1)).first()
    if clash:
        raise ProvisionError(f"A restaurant named {DEMO_NAME!r} already exists in tenant {clash.tenant_id}.")
    owner = db.query(User).filter(User.email == owner_email).first()
    if owner and (tenant is None or owner.tenant_id != tenant.id):
        raise ProvisionError(f"{owner_email} is already registered to another tenant.")

    if tenant is None:
        tenant = Tenant(name=DEMO_NAME)
        db.add(tenant)
        db.flush()
        log.append(f"[CREATED] tenant {DEMO_NAME!r} (id={tenant.id})")
    else:
        log.append(f"[EXISTS]  tenant {DEMO_NAME!r} (id={tenant.id})")

    restaurant = db.query(Restaurant).filter(Restaurant.tenant_id == tenant.id).first()
    if restaurant is None:
        restaurant = Restaurant(tenant_id=tenant.id, name=DEMO_NAME, address="")
        db.add(restaurant)
        db.flush()
        log.append(f"[CREATED] restaurant {DEMO_NAME!r} (id={restaurant.id})")
    else:
        log.append(f"[EXISTS]  restaurant {restaurant.name!r} (id={restaurant.id})")

    if owner is None:
        owner = User(tenant_id=tenant.id, email=owner_email,
                     hashed_password=auth.get_password_hash(owner_password),
                     role=Role.ADMIN, staff_role=StaffRole.OWNER, is_active=True)
        db.add(owner)
        log.append(f"[CREATED] owner {owner_email}")
    else:
        owner.role, owner.staff_role, owner.is_active = Role.ADMIN, StaffRole.OWNER, True
        if reset_password:
            owner.hashed_password = auth.get_password_hash(owner_password)
            owner.failed_login_attempts, owner.locked_until = 0, None
            log.append(f"[UPDATED] owner {owner_email} (password reset)")
        else:
            log.append(f"[EXISTS]  owner {owner_email} (password unchanged)")
    owner.active_restaurant_id = restaurant.id
    _users, staff_log = upsert_demo_staff(db, tenant, restaurant.id, reset_password=reset_password)
    log.extend(staff_log)
    db.commit()
    return log


def provision_demo_from_env() -> None:
    """Startup hook: provision Demo Restaurant when its env vars are set.

    Create-only (never resets a password) and never blocks boot.
    """
    email = os.getenv("DEMO_RESTAURANT_OWNER_EMAIL", "").strip()
    password = os.getenv("DEMO_RESTAURANT_OWNER_PASSWORD", "")
    if not (email and password):
        return
    from database import SessionLocal
    db = SessionLocal()
    try:
        for line in ensure_demo_restaurant(db, email, password):
            logger.info("[demo-provision] %s", line)
    except Exception as exc:
        db.rollback()
        logger.warning("[demo-provision] skipped: %s", exc)
    finally:
        db.close()
