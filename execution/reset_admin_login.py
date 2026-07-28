"""
execution/reset_admin_login.py
────────────────────────────────
Reset the password on the existing admin@lavy.co.ke account (tenant_id=3, the
108k-order Lavy showcase) to a known value so the owner can log in as the
primary ADMIN. Raw SQL against production columns only (the ORM User model's
last_login_at column has no matching production migration).

Run: RESET_ADMIN_PASSWORD="<strong-password>" python execution/reset_admin_login.py --yes
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
require_non_production("resets a known ADMIN account password")
require_write_confirmation("resets the admin@lavy.co.ke password and clears its lockout")



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
            f'            {env_var}="<strong-password>" py execution/reset_admin_login.py --yes'
        )
        sys.exit(1)
    return value

import auth
from database import engine
from sqlalchemy import text

EMAIL = os.getenv("RESET_ADMIN_EMAIL", "admin@lavy.co.ke")
NEW_PASSWORD = _required_password(
    "RESET_ADMIN_PASSWORD", "resets an ADMIN account password"
)

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
print("     password: (the value of RESET_ADMIN_PASSWORD)")
