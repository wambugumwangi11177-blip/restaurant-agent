# v2 production rollout — 19 Oct 2026

What it takes to move production from `4fe7ae5` (30 Sept) to the v2 build, what was rehearsed, and how to go back. Confidence tags: **[Certain]** was observed, **[Likely]** is inferred, **[Guessing]** was not tested.

## What a merge to `master` does

- **[Certain]** Railway builds `master` (root `/backend`, `backend/Dockerfile`); Vercel's production domains track `master` too. Every v2 commit so far built only as a Vercel *preview* (branch `ccr-fc67b65b-k9czx3`).
- **[Certain]** The backend container's start command is `init_db()` (create_all) → `alembic upgrade head` → gunicorn. **A deploy is therefore a migration**: 051 → 056 (six, not three) run when the new container boots, and Railway only marks the deploy healthy when `/health/db` answers.
- **[Certain]** No new environment variables are read by the app (the diff since `4fe7ae5` adds only test-time ones). New pinned dependencies: `openpyxl==3.1.5`, `et-xmlfile==2.0.0`; a clean Python 3.12 install of `requirements.txt` and `import main` both succeed.
- **[Certain]** Production has had no running backend since **17 Oct 07:07 UTC** (Railway log: "Stopping Container"; no deployment with status SUCCESS exists). The merge therefore *starts* the service, and with it the 5-minute escalation/outbox sweeps, the 07:00 reservation reminders, the 20:00 Nairobi evening digest, and whatever `FEATURE_DEMO_CREATIVE` / `OPENROUTER_API_KEY` allow. Why it was stopped is unknown.
- **[Certain]** The production database is Railway's own Postgres 18 (`postgres-ssl:18`, 500 MB volume), private to Railway. It is not the Neon project.

## Rehearsal (scratch Postgres 16, nothing remote touched)

1. Old code (`git archive 4fe7ae5`): `init_db()` + `alembic upgrade head` → head 050; `populate_production.py` → 2 tenants, 736 orders; 3 notifications inserted by SQL.
2. New code, same boot sequence as the container: **six migrations in 1.7 s**, head 056; a second boot runs none; orders and notifications intact; `notifications.push_held` is nullable with no default (so old code still inserts).
3. New app on the migrated database: login and 8 owner endpoints return 200 for both tenants; writes work on Postgres (setting + its audit row, expense + void, 19 lazily created categories, M-Pesa statement upload and removal, Ask).
4. `alembic check` reports the same four tables (`mirror_events`, `reconcile_runs`, `source_systems`, `sync_cursors`) before and after: drift that predates v2. v2 adds none.
5. Downgrade 056 → 050 with the new code: all six downgrades run, data intact; re-upgrade works (round trip).
6. **Not rehearsed:** Postgres 18 (rehearsed on 16; the DDL is plain CREATE TABLE / ADD COLUMN, so **[Likely]** fine) and the real production data. The Docker build was not run here (no daemon) but CI's `container-scan` job built the image on the PR and passed **[Certain]**; the repo's own `owner-postgres-release` CI job also passed.

## Rollback — the part that is not obvious

**[Certain]** Redeploying the old commit onto a database at 056 does not start: the old container's `alembic upgrade head` fails with `Can't locate revision '056_mpesa_match_setting'`, the `&&` chain stops, gunicorn never runs, Railway restart-loops it. The database must go back first:

1. From inside the running new container (Railway CLI `railway ssh`, or any shell that reaches the private database): `alembic downgrade 050_creative_takes`. **[Guessing]** that this is the easiest way in; the database has no public proxy. This drops the v2 tables (settings, money ledger, M-Pesa statements) and the `push_held` column; orders and everything older stay (rehearsed).
2. Then redeploy `4fe7ae5` (or revert the merge on `master`).

Moving forward instead (fixing the new build) needs no downgrade.

## After the deploy

- Check Railway: deployment SUCCESS, log lines `Running upgrade 050_creative_takes -> 051 … 056`, `Application startup complete`.
- The production demo restaurant keeps its old data. v2's richer demo (expenses, bills, the M-Pesa statement, planted scenarios) comes from the guarded `backend/scripts/reseed_demo.py` (read its docstring first: it deletes and regenerates the demo restaurant's data); **the build deliberately never runs it against a remote database**. Until someone re-seeds, the money and M-Pesa panels honestly say "no data".
- `CLAUDE.md` still forbids deploys and production migrations "as part of this build"; the owner lifted it for this one rollout on 19 Oct 2026.
