"""
execution/provision_showcase_login.py
────────────────────────────────────────
Give the owner a guaranteed login to the Lavy showcase data (tenant_id=3,
restaurant_id=3 — the 108k-order dataset). Existing account passwords are
argon2 hashes and can't be recovered, so this provisions a dedicated ADMIN
login with a known password (creating it if absent, resetting it if present)
WITHOUT disturbing the other accounts.

Uses raw SQL against only the columns that exist in production. The ORM User
model carries a `last_login_at` column from in-progress work whose migration
(008) hasn't been applied to production, so querying via the ORM fails there;
raw SQL sidesteps that.

Run: SHOWCASE_ADMIN_PASSWORD="<strong-password>" python execution/provision_showcase_login.py --yes
"""
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)
from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _guard import require_non_production, require_write_confirmation
require_non_production("provisions an ADMIN login with an operator-supplied password")
require_write_confirmation("creates or resets a showcase ADMIN login")



def _required_password(env_var: str, purpose: str) -> str:
    """Read the password from the environment. No literal fallback.

    Security pass 2026-07-28: this script previously carried the password as a
    literal, so a known-credential ADMIN login for the production showcase data
    was committed to git and printed to stdout on every run. Same class of bug
    already fixed in populate_production.py (see its docstring); fixed the same
    way here.
    """
    value = os.getenv(env_var, "").strip()
    if not value:
        print(
            f"[ABORT] {env_var} is not set.\n"
            f"        This script {purpose}; it will not invent or hardcode a password.\n"
            f"        Set it and re-run, e.g.:\n"
            f'            {env_var}="<strong-password>" py execution/provision_showcase_login.py --yes'
        )
        sys.exit(1)
    return value

import auth
from database import engine
from sqlalchemy import text

TENANT_ID = 3
DEMO_EMAIL = "showcase@lavy.co.ke"
DEMO_PASSWORD = _required_password(
    "SHOWCASE_ADMIN_PASSWORD", "creates or resets an ADMIN login"
)

with engine.begin() as c:
    rest = c.execute(text("SELECT id, name FROM restaurants WHERE tenant_id = :t LIMIT 1"),
                     {"t": TENANT_ID}).fetchone()
    print(f"Tenant {TENANT_ID} restaurant: id={rest[0]} name={rest[1]!r}")

    print("\nExisting accounts on this tenant (data-owning accounts):")
    for email, role in c.execute(text("SELECT email, role FROM users WHERE tenant_id = :t ORDER BY id"),
                                 {"t": TENANT_ID}).fetchall():
        print(f"  - {email}   (role={role})")

    pw = auth.get_password_hash(DEMO_PASSWORD)
    c.execute(text("""
        INSERT INTO users (tenant_id, email, hashed_password, role, failed_login_attempts)
        VALUES (:t, :email, :pw, 'ADMIN', 0)
        ON CONFLICT (email) DO UPDATE
          SET hashed_password = EXCLUDED.hashed_password,
              tenant_id = :t, role = 'ADMIN',
              failed_login_attempts = 0, locked_until = NULL
    """), {"t": TENANT_ID, "email": DEMO_EMAIL, "pw": pw})

    row = c.execute(text("SELECT id, email, role, tenant_id FROM users WHERE email = :e"),
                    {"e": DEMO_EMAIL}).fetchone()

print(f"\n[OK] Provisioned login (id={row[0]}):")
print(f"     email:    {DEMO_EMAIL}")
print("     password: (the value of SHOWCASE_ADMIN_PASSWORD)")
print(f"     role:     ADMIN   tenant: {TENANT_ID} (the 108k-order Lavy data)")
