# 020 — External Scheduling & Automation (n8n)

## Goal

Move the *trigger* for scheduled work out of the web process, so a run that
fails is visible, retried, and recorded — without moving any business logic
out of this repository.

## Why this exists

Fourteen jobs run inside the FastAPI process, started by `main.py`'s
`_start_scheduler()`. APScheduler holds them in memory, which gives all of
them the same four properties:

- they die with the container,
- they restart silently on the next boot,
- a failure is a log line nobody reads,
- nothing anywhere records whether last night's run happened.

`escalation_sweep` is the sharpest case. It polls every five minutes so an
unacknowledged critical alert is caught inside its 15-minute window. A
redeploy at the wrong moment means it does not run, and nobody finds out,
because the thing it protects is the case where a human is already not
responding.

## Architecture

```
n8n (schedule, retry, history, alerting)
  → POST /internal/jobs/{name}   ← routers/jobs.py, shared-secret auth
      → the same function APScheduler calls, in main.py
          → the same business logic, in backend/ai/ and backend/integration/
```

The logic stays in the repo, version-controlled and tested. n8n owns only the
trigger. **Do not rebuild any of the detectors, ranking, narration or
grounding as n8n nodes** — that trades a tested guarantee for a diagram.

## The jobs

| Job | Cron (UTC) | Local (EAT) | What it does |
| --- | --- | --- | --- |
| `learning_cycle` | `0 2 * * *` | 05:00 | Records forecasts, scores matured predictions AND owner decisions |
| `audit_log_purge` | `30 1 * * *` | 04:30 | Retention trim |
| `reorder_check` | `0 3 * * *` | 06:00 | Drafts purchase orders before opening |
| `morning_briefing` | `0 4 * * *` | 07:00 | WhatsApp briefing to the owner |
| `strategist_review` | `0 5 * * 1` | Mon 08:00 | Unattended strategy review (flag-gated) |
| `reservation_reminders` | `0 7 * * *` | 10:00 | Same-day reminders; once daily, no per-reservation flag exists |
| `slow_day_check` | `0 11 * * *` | 14:00 | Matches the function's own gate |
| `variance_check` | `0 18 * * *` | 21:00 | Theoretical vs actual usage, after most covers |
| `mirror_reconcile` | `0 21 * * *` | 00:00 | Every mirrored record accounted for |
| `po_late_check` | `0 */2 * * *` | every 2h | Overdue purchase orders |
| `fraud_check` | `0 */2 * * *` | every 2h | Void spikes, refund bursts, unreceipted M-Pesa |
| `stock_check` | `0 8-22/2 * * *` | every 2h, service window | Low-stock alerts |
| `escalation_sweep` | `*/5 * * * *` | every 5 min | Advances the alert ladder |
| `outbox_sweep` | `*/5 * * * *` | every 5 min | Retries failed event handlers |

## Contract

- **Auth**: `X-Job-Key` against `INTERNAL_JOB_KEY`, compared constant-time.
  **Unset means every request is rejected.** An endpoint that runs privileged
  work must never be open because a variable is missing.
- **Synchronous**: the response arrives when the job finishes. Returning 202
  and finishing in a thread would hand back the same blindness this replaces.
- **500 on failure**, with the error in `detail`, so the caller's retry and
  alerting fire. A failure swallowed into a 200 recreates the silent failure
  in a new place.
- **409 if already running.** Several jobs send WhatsApp messages; a scheduler
  retrying on timeout must not send them twice. Exact within one process —
  which is why the deploy runs a single worker — and backed by the jobs' own
  per-subject cooldowns besides.
- `GET /internal/jobs` lists the jobs, whether the in-process scheduler is
  also running, and what is running right now.

## Cutover

1. Import `n8n/01-scheduled-jobs.json`. Set `LEVIII_API_BASE` and
   `LEVIII_JOB_KEY` in n8n; set `INTERNAL_JOB_KEY` on Railway to match.
2. Activate it and **leave `ENABLE_INTERNAL_SCHEDULER` alone** for a day.
   Both running is duplicated work; the jobs are idempotent or cooldown-
   protected, so duplication is survivable. Neither running is silence, and
   silence is the failure mode this whole directive is about.
3. When n8n's execution history shows a clean day, set
   `ENABLE_INTERNAL_SCHEDULER=false` on Railway and redeploy.
4. Confirm with `GET /internal/jobs` — `in_process_scheduler_enabled` should
   read `false`, and n8n should be the only thing firing.

To roll back, unset the variable. It defaults to ON precisely so a missing
variable cannot silently stop all scheduled work.

## The four watchdogs

These add something the app cannot do for itself.

1. **`02-macsoft-watchdog.json`** — hourly `GET /webhooks/macsoft/status`.
   Alerts when `total_records` rises while `projection.projected` stays flat:
   the signature of data arriving and not reaching the owner, which went
   unnoticed for weeks because the only check counted mirror rows. Also alerts
   on any new `top_unmapped_reasons` entry — that is MacSoft sending a field
   name the mapping does not know, fixable in minutes if you hear about it the
   same day.
2. **`03-mirror-reconciliation.json`** — nightly `mirror_reconcile`. Every
   mirrored record must have a `ProjectionLink` saying what became of it. A
   record with no link fell between the two layers and was silently dropped.
   Not a source-vs-mirror reconciliation: MacSoft is push-only and exposes no
   list endpoint, so we cannot ask them what they think they sent. Claiming
   otherwise would be a reassuring check that proves nothing.
3. **`04-deploy-verification.json`** — on Railway's deploy webhook, hits
   `/health/db` and `/webhooks/macsoft/status`. The tracer as a deploy gate
   rather than something someone remembers to check.
4. **`.github/workflows/restore-drill.yml`** — monthly, plus on demand. Not
   n8n: it runs `backend/scripts/restore_drill.sh` against a scratch database,
   which needs a runner and secrets, not an HTTP call. **Run it by hand
   today.** Until it passes once, the backups are configured, not proven.

## Environment

| Variable | Where | Purpose |
| --- | --- | --- |
| `INTERNAL_JOB_KEY` | Railway | Shared secret for the trigger endpoint. Unset = closed. |
| `ENABLE_INTERNAL_SCHEDULER` | Railway | `false` hands scheduling to n8n. Defaults ON. |
| `LEVIII_API_BASE` | n8n | Backend base URL, no trailing slash |
| `LEVIII_JOB_KEY` | n8n | Must equal `INTERNAL_JOB_KEY` |
| `LEVIII_MACSOFT_KEY` | n8n | For the status endpoint the watchdog reads |
| `LEVIII_ALERT_WEBHOOK` | n8n | Slack-compatible incoming webhook |
| `SCRATCH_DATABASE_URL` | GitHub secret | Throwaway DB for the drill. **Never production.** |

## Edge cases

- **Two schedulers at once** is safe but wasteful, and is the intended state
  during cutover. Jobs are idempotent or cooldown-protected.
- **Multiple workers** would break the 409 guard, which is in-process. The
  deploy runs `--workers 1`; raising that needs a shared lock first.
- **A job that raises** returns 500 and clears its running flag, so a retry is
  a fresh attempt rather than a permanent 409.
- **n8n unreachable** is exactly what step 2's overlap period protects
  against. Do not skip it.

## When you change this

Adding a job means adding it to `_FUNCTION_FOR` in `routers/jobs.py`,
`_JOB_NAMES` beside it, a node in `n8n/01-scheduled-jobs.json`, and a row in
the table above. `tests/test_internal_jobs.py` fails if a listed job has no
implementation behind it — a name with nothing behind it would 500 at 3am on
a schedule nobody is watching.
