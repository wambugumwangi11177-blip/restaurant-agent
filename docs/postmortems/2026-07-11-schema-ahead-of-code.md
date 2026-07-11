# Postmortem: Production down — database schema ahead of deployed code

**Date:** 2026-07-11
**Severity:** SEV-1 (production backend unreachable, all endpoints 502)
**Duration:** ~19:32–19:49 GMT+3 (~17 minutes)
**Status:** Resolved

## Summary

Production crash-looped on every boot with `alembic.util.exc.CommandError: Can't locate revision identified by '018_add_token_usage_prompt_version'`. Root cause: the production database's Alembic revision stamp had been advanced to `018_add_token_usage_prompt_version` by a non-production boot (most likely a local/dev run of the `feat/phase1-production-hardening` branch with `DATABASE_URL` pointed at production), while the code actually deployed on Railway (`master`) only contained migrations `001`-`014`. `master` had no way to resolve the database's stamp against its own migration history and failed closed on every start.

Resolved by merging `feat/phase1-production-hardening` (which contains migrations `015`-`018`, already tested — 212 backend tests, Bandit clean, `tsc` clean) into `master`, restoring parity between deployed code and the schema already physically present in the database.

## Timeline (GMT+3)

- **~15:37** — Last known-good boot of `master` at migrations `001`-`014`. Container starts cleanly, `alembic upgrade head` runs with no errors, app serves traffic normally. This confirms the database was **not yet** stamped to `018` at this point — the same code, given the same database, would have failed identically if it had been.
- **15:37-19:32** — Sometime in this window, migrations `015`-`018` are run against the **production** `DATABASE_URL`, most likely from a local or CI boot of the unmerged `feat/phase1-production-hardening` branch. [Likely, not directly observed — no boot/deploy event in this window is recorded against the production Railway service itself.] This stamps the production database to `018` without any corresponding code deploy.
- **19:32** — An unrelated, routine change (adding the `CORS_ORIGINS` environment variable) triggers a redeploy of `master`'s existing container.
- **19:32-19:33** — New container repeatedly fails `alembic upgrade head` with `Can't locate revision identified by '018_add_token_usage_prompt_version'`. Deployment marked `CRASHED`. All endpoints return 502.
- **~19:38** — Manual restart attempted as a first recovery step. Fails identically, confirming the issue is deterministic (database state), not a transient container fault.
- **~19:40-19:47** — Root cause diagnosed: compared `master`'s `backend/alembic/versions/` (highest revision `014`) against the database's `alembic_version` stamp (`018`), and confirmed `018` exists only on the unmerged `feat/phase1-production-hardening` branch.
- **19:47** — Decision made: bring `master`'s code up to the schema, not the schema down to the code (see Decision section below).
- **19:48** — PR #1 (`feat/phase1-production-hardening` -> `master`) merged after confirming all 6 CI checks green (`pytest`, `dependency-audit`, `sast`, `frontend-ci`, Vercel preview, plus the merge-commit status check).
- **19:49:10-19:49:20** — Railway redeploys `master`. `alembic upgrade head` no-ops (database already at `018`, code now recognizes it). Gunicorn boots cleanly. `[CORS] Allowed origins: [...]` confirms the original config change is also live.
- **19:50-19:54** — Verified `/health` (200), `/health/db` (200), and a real cross-origin login request from the Vercel frontend reaching the backend and returning a proper `401` (not a CORS or network failure), confirming full end-to-end recovery.

## Root cause

The backend's `Dockerfile` runs `alembic upgrade head` unconditionally on every container start:

```
CMD ["sh", "-c", "python -c 'from database import init_db; init_db()' && alembic upgrade head && gunicorn ..."]
```

This is correct for how Railway deploys (there is no separate "release phase" step on the Dockerfile builder — migrations *must* run at container start or they silently never run at all). But it also means **any** process that boots this app, or runs `alembic upgrade head` directly, against a given `DATABASE_URL` will migrate that database — regardless of whether the boot is a real production deploy, a local dev run, or CI.

There was no enforced isolation guaranteeing that non-production boots (local development, an agent session testing the hardening branch, etc.) could only ever point at a non-production database. At some point on 2026-07-11, a boot of the `feat/phase1-production-hardening` branch — a branch not yet merged, reviewed, or deployed — had `DATABASE_URL` resolving to the production Postgres instance, and ran migrations `015` through `018` against it. This is consistent with, though not directly proven by, the fact that migration `018` only exists on that branch and the production database was demonstrably still at a pre-`018` state as recently as 15:37 the same day. [Likely]

Once the schema was ahead of `master`, any future redeploy of `master` — regardless of what changed — was guaranteed to crash-loop. The 19:32 CORS variable change simply happened to be the thing that triggered the next redeploy.

## Decision: fix code up to schema, never schema down to code

The two options considered on the live incident were:

1. **Deploy code that matches the schema** (merge the hardening PR to `master`), or
2. **Force the database backward** — downgrade or manually re-stamp `alembic_version` to `014` to match `master`'s original code.

Option 2 was rejected. Migrations `016` and `017` had already introduced real, physically-present constraints on the production database: `CHECK` constraints (`money >= 0`, `quantities/party > 0`), a composite `UNIQUE (restaurant_id, table_number)`, and a `NOT NULL` `token_version` column. Reversing those on a database that settles real M-Pesa payments risks either an outright failure (existing data may already depend on the new constraints) or, worse, a *successful* downgrade that leaves `alembic_version` claiming a schema state that no longer matches the physical columns and constraints actually enforced — silent drift, which `backend/DISASTER_RECOVERY.md` Section 3b already identifies as a higher-risk failure mode than staying ahead.

Option 1 was lower-risk: the hardening branch's code was already fully tested (212 backend tests passing, Bandit SAST clean, `tsc --noEmit` clean, migrations independently verified to reach `head` cleanly) and its PR had green CI. Merging it made the deployed code match a state that already existed on disk.

## Impact

- Backend fully unreachable (502 on every route, including `/health`) for approximately 17 minutes.
- No data loss. No payment webhook activity during the window (M-Pesa is not yet configured on this deployment — see Action Items).
- Frontend (Vercel) remained up but non-functional for any action requiring the API.

## Action items

| # | Action | Priority | Status |
|---|--------|----------|--------|
| 1 | Audit every Railway service/environment (and any local `.env` files) for which `DATABASE_URL` they resolve to. Exactly one thing — the production backend service — should hold the production connection string. PR/preview/branch environments must provision their own database. | High | Open |
| 2 | Never place the production `DATABASE_URL` in a local `.env` or run `alembic upgrade head` locally against it. Local/dev/CI should use SQLite or a disposable Postgres instance. | High | Open |
| 3 | Add a startup preflight that detects "database stamp not found in this build's migration history" and fails with a clear, actionable message instead of Alembic's raw `Can't locate revision` error. | Medium | Done — this PR (`backend/scripts/check_migration_drift.py`) |
| 4 | Enable branch protection on `master`: require PR + the 6 CI checks + no force-push. Would also have prevented an out-of-band schema change from going undetected until the next deploy. | Medium | Open |
| 5 | Delete the unused, stale `CORS_ORIGIN` (singular) Railway variable — dead config left over from before this incident, never read by the app. | Low | Open |
| 6 | Complete the Postgres backup + restore drill per `backend/DISASTER_RECOVERY.md` Section 1-2 before the first paying restaurant. Requires database credentials only the account owner should handle. | High (business) | Open |

## Lessons

- A `Dockerfile` `CMD` that runs migrations at boot is the right call for this deploy path (Railway's Dockerfile builder has no release-phase hook), but it means **every** boot is a migration event. Treat `DATABASE_URL` with the same care as a production credential everywhere, including local shells — because functionally, for this app, it is one.
- When code and schema disagree, prefer moving code forward over moving schema backward, especially once real constraints or non-nullable columns are involved. A schema rollback that "succeeds" but leaves the stamp lying about physical reality is a worse failure mode than a schema that's honestly ahead.
- A clear, specific startup error (see Action Item #3) turns an incident like this from a ~20-minute log-reading exercise into an immediate, actionable diagnosis.
