"""Create a workspace and its first founder account (there is no public sign-up).

Usage:
  python execution/bootstrap_workspace.py --slug acme --name "Acme Ltd" \
      --email you@acme.co.ke --full-name "Your Name" [--phone 0712345678]
The password is prompted for (never passed on the command line, so it stays out
of shell history), or read from BOOTSTRAP_PASSWORD for non-interactive setup.
"""

import argparse
import getpass
import os
import sys

import _common  # noqa: F401

from app.db import session_factory
from app.kernel.bootstrap import BootstrapError, create_workspace_with_founder
from app.security import WeakPasswordError


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--full-name", required=True)
    ap.add_argument("--phone")
    ap.add_argument("--timezone", default="Africa/Nairobi")
    ap.add_argument("--currency", default="KES")
    a = ap.parse_args()

    password = os.environ.get("BOOTSTRAP_PASSWORD")
    if not password:
        password = getpass.getpass("Founder password: ")
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match", file=sys.stderr)
            return 2
    db = session_factory()()
    try:
        ws, user = create_workspace_with_founder(
            db, slug=a.slug, name=a.name, email=a.email, full_name=a.full_name, password=password,
            phone=a.phone, timezone=a.timezone, currency=a.currency)
        db.commit()
    except (BootstrapError, WeakPasswordError, ValueError) as e:
        db.rollback()
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()
    print(f"Created workspace '{ws.slug}' (id {ws.id}) with founder {user.email}. Log in at the web shell.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
