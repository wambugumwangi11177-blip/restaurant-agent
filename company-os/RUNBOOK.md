# Company OS — Runbook

## Incident basics
- **Health:** `GET /health` returns `{"status":"ok"}` when the API and database respond.
- **Logs:** one JSON line per event, each carrying a `request_id`. The same id is returned in the `X-Request-ID` response header, so a user-reported failure can be traced across the API, the agent run and its tool calls.
- **What happened and who did it:**
  - `GET /api/v1/audit` (founder), filterable by `entity_type` and `entity_id`.
  - `GET /api/v1/events` for the activity feed.
  - `GET /api/v1/agents/runs/{id}` for one run and every tool call it made.
- **Stop all agent spending now:** set `DAILY_LLM_SPEND_CAP_USD=0` and restart. Every LLM run returns `spend_capped`, and deterministic agents keep working.
- **Stop all outbound messages now:** unset `TWILIO_*` and `SMTP_*` and restart. Approved proposals then fail visibly with `channel_not_configured` instead of sending.
- **A member's device is lost:** Members → remove them, or have them use `POST /api/v1/auth/logout-all`. Either one bumps `token_version`, which ends every session at once.

## Scheduled jobs (cron)
Run `python execution/run_jobs.py --list` to see every job. Suggested schedule (Railway cron service or crontab; times are Africa/Nairobi):
```
*/15 * * * *  python execution/run_jobs.py sla_check
0 7 * * *     python execution/run_jobs.py daily_brief
0 8 * * *     python execution/run_jobs.py collections_check
5 8 * * *     python execution/run_jobs.py obligations_check
```
Each workspace runs in its own transaction and is audited (`job.run`, `manual: false`). One workspace failing does not stop the others, and the exit code is 1 if any failed.

## Backups
- Manual: `DATABASE_URL=... execution/backup_db.sh` writes a `pg_dump -Fc` file to `.tmp/backups/`.
- **Production (needs the founder):** schedule the same command nightly. On Railway, use a cron service running `execution/backup_db.sh` with `BACKUP_DIR` on a mounted volume or bucket, as restaurant-agent does with its Railway bucket. Keep at least one copy off Railway (restaurant-agent's `backup.yml` pattern: S3, opt-in).

## Restore drill
`DATABASE_URL=<source> execution/restore_drill.sh <dump>` restores into a scratch database, compares per-table row counts with the source, then drops the scratch database.

### Drill log
| Date (UTC) | Source | Dump | Result |
|---|---|---|---|
| 2026-09-26 | local dev DB (`cos_dev`): 1 workspace, 13 documents, 76 chunks, 14 audit rows | `company-os-20260926T114505Z.dump` (108 KB) | **PASSED**: all 21 tables matched |
| _pending_ | **production**: run after the first deploy, and quarterly after that | | |

## Deploy checklist (first time)
1. Railway: create a Postgres instance and a service from `company-os/backend` (Dockerfile).
2. Set the environment: `ENV=production`, `DATABASE_URL`, `JWT_SECRET` (`python -c "import secrets;print(secrets.token_urlsafe(48))"`), `PUBLIC_BASE_URL`, `CORS_ORIGINS`, and the LLM, Twilio and SMTP keys as needed.
3. Release command: `alembic upgrade head`.
4. One-off: `python execution/bootstrap_workspace.py ...`.
5. Vercel: root `company-os/frontend`, env `BACKEND_URL`.
6. Twilio: point the WhatsApp webhook at `https://<api>/api/v1/webhooks/whatsapp`.
7. Run the restore drill against production and add a row above.
