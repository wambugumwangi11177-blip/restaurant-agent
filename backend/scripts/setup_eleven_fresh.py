"""Create or refresh a fresh Eleven owner account with no transactional data.

Idempotent: safe to run twice. Creates tenant + restaurant + owner user only.
Does not seed orders, inventory, menu, cash counts, or demo generators.

Usage (local/staging only):
  ELEVEN_SETUP_ALLOWED=true \\
  ELEVEN_OWNER_EMAIL=owner@example.test \\
  ELEVEN_OWNER_PASSWORD='use-a-strong-secret' \\
  python scripts/setup_eleven_fresh.py --yes-eleven-fresh

Passwords are read from the environment only; this script never prints them.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import get_password_hash, require_strong_password
from database import SessionLocal, init_db
from models import Restaurant, Role, StaffRole, Tenant, User

DEFAULT_TENANT = "Eleven"
DEFAULT_RESTAURANT = "Eleven"

_BLOCKED_URL_FRAGMENTS = (
    "neon.tech",
    "railway.app",
    "amazonaws.com",
    "prod",
    "production",
)


def _assert_safe_environment() -> None:
    if os.getenv("ELEVEN_SETUP_ALLOWED", "").lower() != "true":
        raise SystemExit("Refusing to run: set ELEVEN_SETUP_ALLOWED=true (local/staging only).")
    url = (os.getenv("DATABASE_URL") or "").lower()
    if url and any(fragment in url for fragment in _BLOCKED_URL_FRAGMENTS):
        raise SystemExit("Refusing to run against a production-looking DATABASE_URL.")


def ensure_eleven_fresh(
    db,
    *,
    owner_email: str,
    owner_password: str,
    tenant_name: str,
    restaurant_name: str,
) -> Restaurant:
    require_strong_password(owner_password)

    tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
    if tenant is None:
        tenant = Tenant(name=tenant_name)
        db.add(tenant)
        db.flush()

    owner = db.query(User).filter(User.email == owner_email).first()
    if owner is None:
        owner = User(
            tenant_id=tenant.id,
            email=owner_email,
            hashed_password=get_password_hash(owner_password),
            role=Role.ADMIN,
            staff_role=StaffRole.OWNER,
        )
        db.add(owner)
        db.flush()
    elif owner.tenant_id != tenant.id:
        raise SystemExit(f"Email {owner_email} already belongs to another tenant.")

    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.tenant_id == tenant.id, Restaurant.name == restaurant_name)
        .first()
    )
    if restaurant is None:
        restaurant = Restaurant(tenant_id=tenant.id, name=restaurant_name, address="")
        db.add(restaurant)
        db.flush()

    owner.active_restaurant_id = restaurant.id
    db.commit()
    return restaurant


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotent fresh Eleven owner setup (no demo data).")
    parser.add_argument(
        "--yes-eleven-fresh",
        action="store_true",
        help="Required confirmation that this is not production.",
    )
    parser.add_argument("--tenant-name", default=os.getenv("ELEVEN_TENANT_NAME", DEFAULT_TENANT))
    parser.add_argument("--restaurant-name", default=os.getenv("ELEVEN_RESTAURANT_NAME", DEFAULT_RESTAURANT))
    args = parser.parse_args()

    _assert_safe_environment()
    if not args.yes_eleven_fresh:
        parser.error("Pass --yes-eleven-fresh after confirming this database is local/staging.")

    owner_email = os.getenv("ELEVEN_OWNER_EMAIL", "").strip()
    owner_password = os.getenv("ELEVEN_OWNER_PASSWORD", "")
    if not owner_email or not owner_password:
        parser.error("Set ELEVEN_OWNER_EMAIL and ELEVEN_OWNER_PASSWORD in the environment.")

    init_db()
    db = SessionLocal()
    try:
        restaurant = ensure_eleven_fresh(
            db,
            owner_email=owner_email,
            owner_password=owner_password,
            tenant_name=args.tenant_name.strip(),
            restaurant_name=args.restaurant_name.strip(),
        )
    finally:
        db.close()

    print(f"Eleven fresh account ready: tenant={args.tenant_name!r} restaurant_id={restaurant.id}")
    print(f"Owner login email: {owner_email}")
    print("(Password was taken from ELEVEN_OWNER_PASSWORD — not shown.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
