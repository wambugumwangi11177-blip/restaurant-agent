# Disaster Recovery Runbook

Scope: the production backend (FastAPI on **Railway**) + managed **Postgres**
(Railway/Neon) + **Vercel** frontend. This app settles real M-Pesa payments, so
the database is the crown jewel — everything else is redeployable from git.

> Status: **template — the RTO/RPO figures below are targets until the first
> restore drill fills them in.** Do the drill (§2) before onboarding a paying
> restaurant.

---

## 0. At-a-glance

| Question | Answer |
|---|---|
| What must never be lost? | The Postgres database (orders, payments, consents, audit log). |
| Backup mechanism | Railway/Neon managed automatic backups (+ optional `pg_dump`, §1). |
| RPO target (max data loss) | ≤ 24h (managed daily) — tighten with PITR if the plan supports it. |
| RTO target (max downtime) | ≤ 1h (measure in the drill). |
| Who runs recovery | _<name / on-call — fill in>_ |
| Where secrets live | Railway service env vars (never in git). Keep an offline copy of the list in §5. |

---

## 1. Backups

**Primary — managed provider backups.** In the Railway dashboard → the Postgres
service → **Backups**: confirm automatic backups are **enabled** and note the
schedule + retention. On Neon, confirm **Point-in-Time Restore** is on and note
the history window. Record the actual values here once verified:

- Provider: __________  Schedule: __________  Retention: __________  PITR window: __________

**Secondary (recommended) — logical dump to object storage.** Belt-and-suspenders
against "provider account compromised / project deleted". Implemented (not just
described) as `backend/scripts/backup_db.sh`, run daily by
`.github/workflows/backup.yml` (GitHub Actions scheduled workflow, 03:17 UTC +
manual `workflow_dispatch`):

```bash
DATABASE_URL=...        # a read-only DB role if possible
BACKUP_S3_BUCKET=...
bash backend/scripts/backup_db.sh
```

Set an S3 lifecycle rule on the bucket/prefix to expire old backups (e.g. keep
30 days) — the script does not manage retention itself.

**Still required before this is live** (not fixable by editing files —
credential/dashboard access needed): add `DATABASE_URL`, `BACKUP_S3_BUCKET`,
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` as GitHub Actions repo secrets.
Until then the scheduled workflow will fail at the "Run backup" step every
night — that failure is itself a signal the secrets are still missing.

Verify a dump restores (§2 — also now scripted, `backend/scripts/restore_drill.sh`)
— an untested backup is not a backup.

---

## 2. Restore drill (DO THIS BEFORE LAUNCH)

Goal: prove you can rebuild the DB and measure real RTO/RPO. Use a **throwaway**
target DB — never restore over production during a drill.

1. Provision a scratch Postgres (Railway "new database" or local Docker).
2. Restore the latest backup into it:
   - Managed snapshot: use the provider's "restore to new database" flow.
   - Logical dump: run `backend/scripts/restore_drill.sh` (mechanizes steps
     2-3 below — restore, migrate, health-check, print row timestamps) with
     `SCRATCH_DATABASE_URL` and `DUMP_FILE` set. It refuses to run if
     `SCRATCH_DATABASE_URL` contains "prod".
3. Point a local app at it: `DATABASE_URL=$SCRATCH_URL alembic upgrade head` then
   boot the app; hit `/health/db` (expect 200) and spot-check row counts for
   `orders`, `token_usage`, `customer_consents`.
4. **Record** the wall-clock time taken (→ RTO) and the age of the newest data
   restored (→ RPO) in the table above.
5. Tear down the scratch DB.

**Still required before this is done** (not fixable by editing files — needs a
real scratch DB and real credentials): actually run `restore_drill.sh` once
end-to-end and fill in §0's RTO/RPO/provider/schedule/retention blanks with
the real, observed values.

---

## 3. Recovery scenarios

### 3a. Accidental table drop / bad bulk DELETE/UPDATE
- **Stop writes** if feasible (pause the service) to cap further damage.
- If the provider has **PITR**: restore to a new DB at a timestamp just *before*
  the mistake, verify, then cut over `DATABASE_URL`.
- If only daily snapshots: restore the latest snapshot (accept up to RPO loss).
- Never hand-edit prod to "undo" — restore to a scratch DB, verify, then swap.

### 3b. Failed / partial migration
- Symptom: container won't boot because `alembic upgrade head` errors (the
  Dockerfile runs it at startup).
- The migrations here are written to be **idempotent and non-blocking** (see
  009, 011, 015, 016 — inspector guards, `NOT VALID`, dupe-guards). If one still
  fails: read the alembic error in Railway logs, identify the revision.
- Fix forward: correct the migration, redeploy. If a revision half-applied,
  `alembic downgrade <prev>` on a scratch copy to confirm the down path, then
  reconcile. Do NOT `alembic stamp` past a failure without understanding what
  did/didn't apply — that hides drift (see migration 011's purpose).
- Roll back the deploy in Railway to the last green image to restore service
  while you fix the migration.

### 3c. Optional AI provider outage
- External AI calls have timeouts and bounded retries. Confirm database
  readiness through `/health/db`; this does not prove provider availability.
- Owner communication uses the in-app inbox. M-Pesa and Twilio transports
  are retired; do not recreate their credentials or callbacks during recovery.
- LLM down: `is_available()` gates it — dashboards serve deterministic numbers
  with no narrative. Nothing customer-facing breaks.
- Action: confirm it's the provider (status page), not us; no restore needed.

### 3d. SSL certificate expiry
- **Platform-managed.** Railway and Vercel auto-provision and auto-renew TLS.
  There is no cert to rotate by hand and no monitor to build here. If HTTPS
  fails, it's a platform incident — check Railway/Vercel status, don't touch the
  app.

### 3e. Full region / provider loss
- Redeploy the backend from git to a new Railway project (IaC is in-repo:
  Dockerfile + railway.json), restore the DB from the §1 secondary dump, set the
  env vars from §5, repoint the frontend `NEXT_PUBLIC_API_URL`.

---

## 4. Cutover checklist (after any DB restore)
- [ ] `alembic upgrade head` clean against the restored DB.
- [ ] `/health/db` returns 200.
- [ ] Spot-check latest `orders` / `token_usage` timestamps match expected RPO.
- [ ] `APP_ENV=production`, `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS` configured.
- [ ] Frontend reaches the API (login works end-to-end).
- [ ] Announce restored; note RTO/RPO actually achieved.

## 5. Required env vars (keep an offline copy; values NOT here)
Required: `APP_ENV=production`, `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS`.
Optional AI, SMTP, monitoring and off-site backup credentials must match the
configured providers. Verify delivery, monitoring and backup operation separately;
their presence alone is not evidence that recovery or alerting works.
See `backend/.env.example` for the full annotated list.

## 6. Operator runbook (rollback, key rotation, who to call)

Written so a second person can act without the founder.

**Roll back a bad deploy.** Railway → backend service → Deployments → pick the
last green deployment → Redeploy. Images are retained 72h (Hobby) / 120h (Pro),
so roll back inside that window. Health-check failures keep the previous
version serving. Never roll back past a migration without §3b.

**Rotate keys** (after any suspected leak, or a person leaving):
1. `SECRET_KEY` (invalidates all sessions), `DATABASE_URL` password, LLM keys
   (`OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` / `GROQ_API_KEY`), backup keys.
2. Set the new value in Railway env vars, redeploy, verify `/health/db`.
3. Revoke the old value at the provider. Record the date in the vault.

**Token hygiene (PocketOS lesson).** No agent or CI environment may hold a
Railway *account* token. Use a project-scoped token for CI; give teammates the
Editor role (cannot delete services/volumes); seal production secrets.

**Backups must leave the blast radius.** `wiping a volume deletes all
backups` on Railway, and `backend/scripts/backup/run_backup.sh` uploads to a
Railway bucket in the same project. Treat that as convenience only: the
GitHub Actions dump (§1, `backup.yml`) to a *different provider and account*
is the real off-platform copy. Enable Postgres PITR (about 4-week window).

**Billing.** Railway stops workloads if credit hits zero and deletes volumes
60-90 days after cancellation. Company card plus a backup card; a second
person with billing access.

**Who to call** (fill in; keep in the vault too):
- Second director / signatory: ________
- Retained engineer: ________  (P1 response target: 30 min in service hours)
- Accountant / tax agent: ________  Company secretary / advocate: ________

**Model retirement.** Anthropic gives 60 days' notice. Check
https://platform.claude.com/docs/en/about-claude/model-deprecations monthly
and grep for model ids (`ai/llm_client.py`, `.env.example`, Railway env
`ANTHROPIC_MODEL*`). Claude 4.7+ models reject `temperature`; the client
already omits it (`_anthropic_accepts_temperature`).
