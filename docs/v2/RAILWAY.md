# Railway — what the old account held, and how to rebuild it in a new one

Read from the Railway API on 20 Oct 2026 (account `r2mbuguss@gmail.com`, created 16 Sep 2026). Confidence tags as in `ROLLOUT.md`. No secret value is copied here: variables are listed by name, and their values have to come from the owner or be generated fresh.

## What is (was) there

Project **`restaurant-agent-backend`** (`123c19bf-5b77-4e1f-833d-511ad9bdd733`), workspace "Wambugu's Projects", one environment `production`, region **sfo**. A second project, `company-os`, belongs to another repository and is not part of this app.

| Service | Source | Settings that matter |
|---|---|---|
| `restaurant-agent` (API) | GitHub `wambugumwangi11177-blip/restaurant-agent`, branch **`master`**, root directory **`/backend`** | Builder **Dockerfile** (`/backend/Dockerfile`); healthcheck **`/health/db`**, timeout **120 s**; 1 replica; no pre-deploy command (the image's start command runs `init_db()` → `alembic upgrade head` → gunicorn); domain `restaurant-agent-production-653f.up.railway.app`; no custom domain; no volume |
| `Postgres` | Image `ghcr.io/railwayapp-templates/postgres-ssl:18` | Volume `postgres-volume`, **500 MB**, mounted at `/var/lib/postgresql/data`; private network name `postgres`; **no public TCP proxy** (the database cannot be reached from outside Railway) |

**API variables (names only).** `APP_ENV`, `CORS_ORIGINS`, `DATABASE_URL`, `DEMO_RESTAURANT_OWNER_EMAIL`, `DEMO_RESTAURANT_OWNER_PASSWORD`, `FEATURE_DEMO_CREATIVE`, `FEATURE_STRATEGY_AGENT`, `MACSOFT_API_KEY`, `OPENROUTER_API_KEY`, `SECRET_KEY`, `SENTRY_DSN`.
**Postgres variables** are the template's own (`PG*`, `POSTGRES_*`, `DATABASE_URL`, `PGDATA`, `SSL_CERT_DAYS`, `RAILWAY_DEPLOYMENT_DRAINING_SECONDS`); a new template creates them.

**Vercel side (project `restaurant-agent`, team `team_HuwQ7xLCU3Y7gAZZ2uEFELgT`).** The frontend finds the API through `NEXT_PUBLIC_API_URL` and `BACKEND_URL` (production and preview each). Both hold the old Railway domain and must be changed to the new one; the API's `CORS_ORIGINS` must list the Vercel domains.

## Why production is down

- **[Certain]** At **17 Oct 2026 07:07 UTC** the API container got "Stopping Container" and Postgres got `SIGTERM` → "database system is shut down", within the same eleven seconds. Neither had an error before it; the 5-minute scheduler jobs were running normally until then.
- **[Certain]** Both deployments are now `REMOVED`; Postgres has no deployment at all. The volume still exists.
- **[Likely]** The account's plan or trial ran out (created 16 Sep, stopped 31 days later; both services stopped at once by the platform, not by the app). That also means `ROLLOUT.md`'s "merging starts the service" is wrong for this account: a merge to `master` would not bring the database back, and the API's healthcheck needs it.

**Data.** Production held demo data only (owner's statement, 19 Oct): 2 tenants, ~736 orders at the 30 Sept code. **[Certain]** it cannot be exported from outside (no public proxy, services stopped). A new account starts with an empty database, which the app fills itself at boot (below). If anything in the old volume matters, the old account has to be reactivated long enough to run `pg_dump` from inside Railway.

## Rebuilding in a new account (the steps Claude will follow)

1. New project, environment `production`. Pick a region near Nairobi users if offered (the old one was `sfo`; `europe-west` is closer).
2. Add **Postgres** from Railway's template (it brings its volume and variables). Leave it private.
3. Add the API service from GitHub `wambugumwangi11177-blip/restaurant-agent`, branch `master`, root `/backend`, builder Dockerfile `/backend/Dockerfile`, healthcheck `/health/db` with 120 s.
4. Variables on the API:
   - `DATABASE_URL` = reference to the new Postgres (`${{Postgres.DATABASE_URL}}`), never pasted.
   - `SECRET_KEY` = freshly generated (`python -c "import secrets; print(secrets.token_hex(32))"`). Changing it only logs everyone out, which a new deployment does anyway.
   - `APP_ENV=production`, `CORS_ORIGINS` = the Vercel production domain(s).
   - `DEMO_RESTAURANT_OWNER_EMAIL` / `DEMO_RESTAURANT_OWNER_PASSWORD` — the startup hook creates the Demo Restaurant owner from these (create-only, idempotent).
   - `OPENROUTER_API_KEY`, `MACSOFT_API_KEY`, `SENTRY_DSN`, `FEATURE_DEMO_CREATIVE`, `FEATURE_STRATEGY_AGENT` — values from the owner; leave out any that are not wanted (the app runs without them; creative/AI features stay off).
5. Generate a Railway domain for the API; set Vercel's `NEXT_PUBLIC_API_URL` and `BACKEND_URL` (production) to it; redeploy the frontend.
6. First boot creates every table (`init_db`) and stamps alembic head (056 with v2) — no downgrade or old-schema concerns on an empty database.
7. Check: deployment `SUCCESS`, log `Application startup complete`, `GET /health/db` 200, owner login works on the Vercel site.
   **Rehearsed 20 Oct 2026 [Certain]** on an empty local Postgres 16 with this branch: the container's command (`init_db()` → `alembic upgrade head` → gunicorn) ran every migration to `056_mpesa_match_setting`; a second boot ran none; `/health/db` answered 200; the startup hook logged `[CREATED]` for the Demo Restaurant tenant, restaurant and owner; that owner logged in and `/owner/home`, `/owner/area/money` and `/owner/report/weekly` returned 200. Not rehearsed: Postgres 18 and Railway's build itself.
8. Only then, if wanted: fill the demo with `backend/scripts/reseed_demo.py` (read its docstring; it needs `--allow-remote` and a typed confirmation, and it deletes and regenerates the Demo Restaurant only).
