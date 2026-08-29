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

### 3c. Third-party outage (Twilio / M-Pesa / LLM)
- The app **degrades, not dies**: external calls have timeouts + (LLM) bounded
  retries; a failed send/STK-push is best-effort and never blocks order/payment
  state. Confirm via `/health` staying 200.
- M-Pesa down: orders can still be created and paid by cash/card at the POS;
  Safaricom **retries** its callback, so a temporarily-down webhook self-heals.
- Twilio down: owner alerts/receipts queue as failures in logs; no data loss.
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
- [ ] `MPESA_CALLBACK_TOKEN`, `SECRET_KEY`, `CORS_ORIGINS` present on the service.
- [ ] Frontend reaches the API (login works end-to-end).
- [ ] Announce restored; note RTO/RPO actually achieved.

## 5. Required env vars (keep an offline copy; values NOT here)
`SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, `MPESA_CONSUMER_KEY`,
`MPESA_CONSUMER_SECRET`, `MPESA_SHORTCODE`, `MPESA_PASSKEY`,
`MPESA_CALLBACK_URL`, `MPESA_CALLBACK_TOKEN`, `MPESA_ENV`,
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`,
`GROQ_API_KEY` (or `ANTHROPIC_API_KEY`), `SENTRY_DSN`.
See `backend/.env.example` for the full annotated list.
