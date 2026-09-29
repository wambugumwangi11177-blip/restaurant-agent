"""
execution/provision_demo_restaurant.py
──────────────────────────────────────
Create the "Demo Restaurant" tenant: a restaurant with an owner login and NO
data (no menu, stock, staff, tables, orders or bookings).

Its owner signs in by restaurant name + password (the same restaurant login as
Vibanda Village) and lands on /demo — a clone of the Vibanda owner shell. Unlike
Vibanda it never waits on MacSoft or any API push: the backend reports its
source as "direct" (routers/overview.py DIRECT_SOURCE_TENANTS), so whatever is
recorded for it shows immediately.

Idempotent and additive: an existing tenant/restaurant/owner is reused, nothing
is deleted, and an existing owner's password is only changed with
--reset-password.

NOTE: backend/.env points at the live Neon database. Running this writes there.

Usage:
  python execution/provision_demo_restaurant.py \
      --owner-email owner@demo-restaurant.example --owner-password '<password>'
  # re-set the owner's password later:
  python execution/provision_demo_restaurant.py --owner-email ... --owner-password ... --reset-password
"""
import argparse
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_backend, ".env"))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import func  # noqa: E402

import auth  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Restaurant, Role, StaffRole, Tenant, User  # noqa: E402

DEMO_NAME = "Demo Restaurant"


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Provision the empty '{DEMO_NAME}' tenant and its owner login.")
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--owner-password", required=True)
    parser.add_argument("--reset-password", action="store_true",
                        help="also reset the password if the owner already exists")
    args = parser.parse_args()
    try:
        auth.require_strong_password(args.owner_password)
    except HTTPException as exc:
        parser.error(exc.detail)

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(func.lower(Tenant.name) == DEMO_NAME.lower()).first()
        # Restaurant login resolves the owner by restaurant name, so the name
        # must be unique across tenants or nobody can sign in.
        clash = db.query(Restaurant).filter(
            func.lower(Restaurant.name) == DEMO_NAME.lower(),
            Restaurant.tenant_id != (tenant.id if tenant else -1)).first()
        if clash:
            print(f"[ERROR] A restaurant named {DEMO_NAME!r} already exists in tenant {clash.tenant_id}. Aborting.")
            return 1
        email_owner = db.query(User).filter(User.email == args.owner_email).first()
        if email_owner and (tenant is None or email_owner.tenant_id != tenant.id):
            print(f"[ERROR] {args.owner_email} is already registered to another tenant. Use a different email.")
            return 1

        if tenant is None:
            tenant = Tenant(name=DEMO_NAME)
            db.add(tenant)
            db.flush()
            print(f"[CREATED] tenant {DEMO_NAME!r} (id={tenant.id})")
        else:
            print(f"[EXISTS]  tenant {DEMO_NAME!r} (id={tenant.id})")

        restaurant = db.query(Restaurant).filter(Restaurant.tenant_id == tenant.id).first()
        if restaurant is None:
            restaurant = Restaurant(tenant_id=tenant.id, name=DEMO_NAME, address="")
            db.add(restaurant)
            db.flush()
            print(f"[CREATED] restaurant {DEMO_NAME!r} (id={restaurant.id})")
        else:
            print(f"[EXISTS]  restaurant {restaurant.name!r} (id={restaurant.id})")

        owner = email_owner
        if owner is None:
            owner = User(tenant_id=tenant.id, email=args.owner_email,
                         hashed_password=auth.get_password_hash(args.owner_password),
                         role=Role.ADMIN, staff_role=StaffRole.OWNER, is_active=True)
            db.add(owner)
            print(f"[CREATED] owner {args.owner_email}")
        else:
            owner.role, owner.staff_role, owner.is_active = Role.ADMIN, StaffRole.OWNER, True
            if args.reset_password:
                owner.hashed_password = auth.get_password_hash(args.owner_password)
                owner.failed_login_attempts, owner.locked_until = 0, None
                print(f"[UPDATED] owner {args.owner_email} (password reset)")
            else:
                print(f"[EXISTS]  owner {args.owner_email} (password unchanged; pass --reset-password to change it)")
        owner.active_restaurant_id = restaurant.id
        db.commit()
    finally:
        db.close()

    print(f"\n[OK] Sign in at /login with Restaurant = {DEMO_NAME!r} and the owner password. Lands on /demo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
