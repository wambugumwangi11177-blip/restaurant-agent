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

Run: python execution/provision_showcase_login.py
"""
import os
import sys

_backend = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, _backend)
from dotenv import load_dotenv
load_dotenv(os.path.join(_backend, ".env"))

import auth
from database import engine
from sqlalchemy import text

TENANT_ID = 3
DEMO_EMAIL = "showcase@lavy.co.ke"
DEMO_PASSWORD = "LavyShowcase2026!"

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
print(f"     password: {DEMO_PASSWORD}")
print(f"     role:     ADMIN   tenant: {TENANT_ID} (the 108k-order Lavy data)")
