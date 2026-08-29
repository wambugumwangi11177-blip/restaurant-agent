# RUNBOOK — running the stack locally

## One command

```bash
./dev.sh
```

- Backend:  http://localhost:8000  (ready in a few seconds)
- Frontend: http://localhost:3000  (ready in a few seconds)
- `Ctrl+C` stops both. Logs land in `./backend.log` and `./frontend.log`.
- `./dev.sh --dev` runs the frontend in hot-reload mode for coding (slower
  page opens — each route compiles on first visit). Default is the fast
  prebuilt production server.

## Local runs on a COPY of your data (sandbox)

Local dev points at `backend/local_dev.db` — a SQLite snapshot of the
production Neon database (taken 2026-08-22, 661,884 rows). Every query runs
in milliseconds instead of crossing the ocean to the US, which is what makes
the dashboards fast locally.

- **It's a sandbox**: orders/edits you make locally do NOT touch production.
- **Refresh the copy** from live Neon any time:
  ```bash
  cd backend && venv/bin/python dev_snapshot.py
  ```
- **Work against LIVE remote data instead** (slow locally — every page pays
  the international round-trips): in `backend/.env`, swap the values of
  `DATABASE_URL` (→ the postgres URL) and `REMOTE_DATABASE_URL` (→ the
  sqlite one), restart, and swap back when done.

## Is it working?

- `http://localhost:8000/health/` → `{"status":"ok"}`
- Open `http://localhost:3000`, log in, and the dashboard loads in seconds.

## First-time setup (or after a rebuild)

```bash
# Backend — Python virtualenv
cd backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python dev_snapshot.py   # build local_dev.db from Neon

# Frontend — node modules (dev.sh builds .next automatically on first run)
cd ../frontend
npm install
```

## If something breaks

**`ModuleNotFoundError: fastapi` (or any package)**
The venv was probably built for a different Python than the one now on the
machine — this is exactly what took the whole stack down once already (venv
built on Python 3.12, system upgraded to 3.14). Rebuild it:

```bash
cd backend && rm -rf venv && python3 -m venv venv && venv/bin/pip install -r requirements.txt
```

**Login returns "Internal server error" (HTTP 500)**
Almost always schema drift: the database is behind the code. Check with:

```bash
cd backend && venv/bin/alembic current   # compare against `venv/bin/alembic heads`
```

If they differ, bring the database up to date:

```bash
cd backend && venv/bin/alembic upgrade head
```

**Backend never becomes ready**
Give it 40 seconds first. Then check `backend.log` — startup failures there
are usually the database (DATABASE_URL in `backend/.env`) being unreachable.

**Ports already in use ("8000 free"/"3000 free" not so free)**

```bash
pkill -f "uvicorn main:app"; pkill -f next-server
```

## Notes

- The local `.env` files (`backend/.env`, `frontend/.env.local`) are gitignored
  and already point everything at the right places (Neon Postgres +
  localhost). Nothing to configure.
- SMTP email and Web Push are intentionally optional — without keys set, reset
  links are logged to the backend console and push is skipped. The in-app
  notification feed still works.
