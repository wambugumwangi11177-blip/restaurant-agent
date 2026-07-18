"""
execution/reset_staff_test_logins.py
───────────────────────────────────────
Reset passwords on the existing per-tier staff accounts on the Lavy showcase
restaurant (tenant_id=3) to known values, so all 7 staff_role tiers can be
logged into simultaneously (separate browser tabs / profiles) to verify
cross-account notifications (directive 016/017's staff comms work).

Every account below already exists on tenant 3 with the right staff_role —
this only resets hashed_password + clears any lockout, exactly like the
existing execution/reset_admin_login.py does for the single admin account.
Doesn't create or delete anything.

Run: python execution/reset_staff_test_logins.py
"""
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)
from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

import auth
import models
from database import SessionLocal

TENANT_ID = 3
PASSWORD = "LavyTest2026!"

# email -> expected staff_role, just to print a sanity check
ACCOUNTS = {
    "manager@lavy.co.ke": models.StaffRole.MANAGER,
    "supervisor@lavy.co.ke": models.StaffRole.SUPERVISOR,
    "controller@lavy.co.ke": models.StaffRole.CONTROLLER,
    "stockkeeper@lavy.co.ke": models.StaffRole.STOCKKEEPER,
    "kitchen@lavy.co.ke": models.StaffRole.KITCHEN,
    "waiter1@lavy.co.ke": models.StaffRole.WAITER,
}

db = SessionLocal()
try:
    pw_hash = auth.get_password_hash(PASSWORD)
    print(f"{'email':<28} {'tier':<12} status")
    print("-" * 55)

    # Owner: showcase@lavy.co.ke already has a known password from
    # execution/provision_showcase_login.py — no reset needed.
    owner = db.query(models.User).filter(models.User.email == "showcase@lavy.co.ke").first()
    print(f"{'showcase@lavy.co.ke':<28} {'OWNER':<12} already known (LavyShowcase2026!)")

    for email, expected_role in ACCOUNTS.items():
        user = db.query(models.User).filter(
            models.User.tenant_id == TENANT_ID, models.User.email == email
        ).first()
        if not user:
            print(f"{email:<28} {'?':<12} NOT FOUND — skipped")
            continue
        if user.staff_role != expected_role:
            print(f"{email:<28} {str(user.staff_role):<12} WARNING: expected {expected_role}, found this instead")
        user.hashed_password = pw_hash
        user.failed_login_attempts = 0
        user.locked_until = None
        user.is_active = True
        print(f"{email:<28} {str(user.staff_role):<12} reset")

    db.commit()
finally:
    db.close()

print()
print("Shared password for all 6 reset accounts:", PASSWORD)
print("Owner (showcase@lavy.co.ke) password:      LavyShowcase2026!")
