"""
execution/reset_admin_login.py
────────────────────────────────
Reset the password on the existing admin@lavy.co.ke account (tenant_id=3, the
108k-order Lavy showcase) to a known value so the owner can log in as the
primary ADMIN. Raw SQL against production columns only (the ORM User model's
last_login_at column has no matching production migration).

Run: python execution/reset_admin_login.py
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

EMAIL = "admin@lavy.co.ke"
NEW_PASSWORD = "LavyAdmin2026!"

with engine.begin() as c:
    existing = c.execute(text("SELECT id, tenant_id, role FROM users WHERE email = :e"),
                         {"e": EMAIL}).fetchone()
    if not existing:
        print(f"[ERROR] {EMAIL} not found.")
        sys.exit(1)
    pw = auth.get_password_hash(NEW_PASSWORD)
    c.execute(text("""
        UPDATE users
           SET hashed_password = :pw, failed_login_attempts = 0, locked_until = NULL
         WHERE email = :e
    """), {"pw": pw, "e": EMAIL})

print(f"[OK] Reset password for {EMAIL} (id={existing[0]}, role={existing[2]}, tenant={existing[1]}):")
print(f"     email:    {EMAIL}")
print(f"     password: {NEW_PASSWORD}")
