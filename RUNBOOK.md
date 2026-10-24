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

## Demo staff logins

The restaurant-name form signs in the **owner** only. Store, kitchen, manager and accountant use **Sign in with email instead**.

Passwords are never written in this file or in the seed. Set them in the environment next to `DEMO_RESTAURANT_OWNER_PASSWORD`, then re-seed (a re-seed applies these passwords; a normal process start creates the accounts once and does not reset a password you already set):

| Screen | Email | Env var | After login |
| --- | --- | --- | --- |
| Manager | `manager@demo-restaurant.example` | `DEMO_RESTAURANT_MANAGER_PASSWORD` | `/staff/manager` |
| Storekeeper | `store@demo-restaurant.example` | `DEMO_RESTAURANT_STOREKEEPER_PASSWORD` | `/staff/stockkeeper` |
| Kitchen / chef | `kitchen@demo-restaurant.example` | `DEMO_RESTAURANT_KITCHEN_PASSWORD` | `/staff/kitchen` |
| Accountant | `accountant@demo-restaurant.example` | `DEMO_RESTAURANT_ACCOUNTANT_PASSWORD` | `/staff/controller` |

The kitchen login is the person who confirms what arrived from the store. The storekeeper can issue stock and cannot confirm their own issue. Each password needs at least 8 characters, one letter and one number (the same rule as the owner password).

```bash
export DEMO_RESTAURANT_OWNER_PASSWORD='…'
export DEMO_RESTAURANT_MANAGER_PASSWORD='…'
export DEMO_RESTAURANT_STOREKEEPER_PASSWORD='…'
export DEMO_RESTAURANT_KITCHEN_PASSWORD='…'
export DEMO_RESTAURANT_ACCOUNTANT_PASSWORD='…'
python execution/reseed_demo.py --yes
```

Optional `MENU_QUOTE_SECRET` signs scheduled-price quotes separately from login tokens. When it is unset, quotes use a key derived from `SECRET_KEY` that login tokens cannot verify.

## Railway environment for the demo

Set these on the backend service. Leave Twilio unset: WhatsApp is shelved (`FEATURE_WHATSAPP` defaults to false) and the demo does not send phone messages.

| Variable | Required | What it does |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | Yes, for any written AI | Without it, Ask still answers sales questions from the records and the writing assistant says AI is unavailable. |
| `OPENROUTER_MODEL` | No | Defaults to `deepseek/deepseek-v4-flash`. |
| `OPENROUTER_MODEL_HIGH` | No | Same default. |
| `OPENROUTER_MODEL_LOW` | No | Same default. |
| `OPENROUTER_MODEL_CREATIVE` | No | Same default. Used for Home's read and the report note. |
| `OPENROUTER_FALLBACK_MODEL` | No | Defaults to `qwen/qwen3.7-flash` when the first model returns nothing usable. |
| `OPENROUTER_REASONING` | No | Defaults to `off`. deepseek-v4-flash reasons unless this is sent, and a short budget then comes back with no answer. Set `on` only for a call that should reason. |
| `DAILY_LLM_SPEND_CAP_USD` | No | Defaults to `1`. Raise it when the owner budget allows. |
| `FEATURE_AI_NARRATION` | No | Defaults to true. Set `false` to stop every LLM call. |
| `FEATURE_CREATIVE_LAYER` | No | Defaults to true. The note is written only when a provider key is set. Set `false` to keep numbers without the written note. |
| `FEATURE_WHATSAPP` | No | Defaults to false. Do not set Twilio credentials for this demo. |
| `DEMO_RESTAURANT_OWNER_PASSWORD` | Yes, for the owner login | Plus the four staff passwords in the table above. |
| `MENU_QUOTE_SECRET` | No | Optional separate key for scheduled-price quotes. |

OpenRouter requests send `provider.data_collection = deny` and, unless `OPENROUTER_REASONING=on`, `reasoning.enabled = false`. A reply with `content` null and `finish_reason=length` is logged and retried once; it is not shown as an empty answer. Do not switch the model variables back to a `:free` model; some of those providers train on prompts.

## Notes

- The local `.env` files (`backend/.env`, `frontend/.env.local`) are gitignored
  and already point everything at the right places (Neon Postgres +
  localhost). Nothing to configure.
- SMTP email and Web Push are intentionally optional — without keys set, reset
  links are logged to the backend console and push is skipped. The in-app
  notification feed still works.
