"""
execution/e6_backend.py — the backend the owner-task browser tests (E6) run against.

Builds a throwaway SQLite database in .tmp/e6/ — the demo restaurant with every scenario planted (backend/demo/generator.py) plus a
brand-new restaurant with nothing recorded — and serves the API on port 8000 (the one the built frontend's content-security policy
allows). It refuses any database that is not a local file, never reads backend/.env, and never touches DATABASE_URL: the database is
named here, in this file, and deleted and rebuilt on every start.

    python execution/e6_backend.py            # build and serve (what `npx playwright test` starts)
    python execution/e6_backend.py --build    # build only
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
DB_PATH = os.path.join(ROOT, ".tmp", "e6", "e6.db")
PORT = int(os.getenv("E6_BACKEND_PORT", "8000"))

DEMO_OWNER, DEMO_NAME = "owner@demo-restaurant.example", "Demo Restaurant"
# Brand-new restaurants (nothing recorded). The test that saves targets changes its restaurant, so each browser size gets its own.
FRESH = (("New Kitchen", "owner@new-kitchen.example"), ("Targets Phone", "owner@targets-phone.example"), ("Targets Desk", "owner@targets-desk.example"))
PASSWORD = "E6-Passw0rd!x"                   # a throwaway password for a throwaway database

# Set before any backend module is imported: they read these at import time.
# These credentials exist only in the disposable E6 database.
for role in ("MANAGER", "STOREKEEPER", "KITCHEN", "ACCOUNTANT"):
    os.environ[f"DEMO_RESTAURANT_{role}_PASSWORD"] = PASSWORD
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ.setdefault("SECRET_KEY", "e6-" + "x" * 48)
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
sys.path.insert(0, BACKEND)


def build() -> None:
    for suffix in ("", "-journal", "-wal", "-shm"):
        try:
            os.remove(DB_PATH + suffix)
        except FileNotFoundError:
            pass
    import auth
    import models
    from database import SessionLocal, engine
    from demo.generator import build as build_demo
    from time_utils import utcnow

    models.Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        build_demo(db, DEMO_OWNER, PASSWORD, now=utcnow())
        for name, email in FRESH:
            tenant = models.Tenant(name=name)
            db.add(tenant)
            db.flush()
            db.add(models.Restaurant(tenant_id=tenant.id, name=name, address="Kisumu"))
            db.add(models.User(tenant_id=tenant.id, email=email, hashed_password=auth.get_password_hash(PASSWORD), role=models.Role.ADMIN,
                               staff_role=models.StaffRole.OWNER, token_version=0))
        db.commit()
    finally:
        db.close()
    # The first-week screens count days from the Nairobi date a restaurant was created, so a run that crosses Nairobi midnight (21:00 UTC)
    # meets "day 2" where the tests expect "day 1". The browser tests read this and say so rather than fail.
    from time_utils import eat_date
    with open(os.path.join(os.path.dirname(DB_PATH), "built_on.txt"), "w") as f:
        f.write(eat_date(utcnow()).isoformat())


if __name__ == "__main__":
    from demo import safety
    safety.require_safe_target(os.environ["DATABASE_URL"], yes=True, allow_remote=False, typed=None)
    build()
    print(f"e6 database ready: {DB_PATH}", flush=True)
    if "--build" not in sys.argv:
        import uvicorn

        import rate_limit
        # Twenty browser tests sign in far faster than the production login limit (10 a minute per address) allows. Switched off for this
        # process only: it exists to run the owner-task tests, serves a throwaway database and is never started by anything else.
        rate_limit.limiter.enabled = False
        uvicorn.run("main:app", host="127.0.0.1", port=PORT, log_level="warning")
