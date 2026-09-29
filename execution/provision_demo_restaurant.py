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

The logic lives in backend/tenant_provisioning.py, shared with the env-gated
startup hook the live Railway service uses (its Postgres is not reachable from
outside Railway). Idempotent and additive; an existing owner's password is only
changed with --reset-password.

NOTE: this writes to whatever DATABASE_URL points at (backend/.env by default).

Usage:
  python execution/provision_demo_restaurant.py \
      --owner-email owner@demo-restaurant.example --owner-password '<password>'
"""
import argparse
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_backend, ".env"))

from database import SessionLocal  # noqa: E402
from tenant_provisioning import DEMO_NAME, ProvisionError, ensure_demo_restaurant  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Provision the empty '{DEMO_NAME}' tenant and its owner login.")
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--owner-password", required=True)
    parser.add_argument("--reset-password", action="store_true",
                        help="also reset the password if the owner already exists")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        for line in ensure_demo_restaurant(db, args.owner_email, args.owner_password, args.reset_password):
            print(line)
    except ProvisionError as exc:
        print(f"[ERROR] {exc}")
        return 1
    finally:
        db.close()

    print(f"\n[OK] Sign in at /login with Restaurant = {DEMO_NAME!r} and the owner password. Lands on /demo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
