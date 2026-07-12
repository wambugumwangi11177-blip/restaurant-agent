# External Hardening Checklist (operator actions)

> **Status:** actionable checklist — owner/operator to complete in the Railway,
> Vercel, GitHub, and Sentry consoles. These items **cannot be closed in code**;
> they are the "Phase 3b" companion to the code hardening in
> [engineering-standards.md](engineering-standards.md) and
> [operations-and-reliability.md](operations-and-reliability.md). Tick each box
> in a copy of this file (or a tracking issue) as you complete it.

Everything here is a one-time or low-frequency console action. None of it needs a
deploy. Ordered by risk-reduction.

---

## 1. Database backups + restore drill  🔴 highest priority

A backup you have never restored is a hope, not a backup.

- [ ] **Confirm automatic backups are ON** for the production Postgres
      (Railway add-on or Neon). Record provider + schedule + retention window in
      [backend/DISASTER_RECOVERY.md](../backend/DISASTER_RECOVERY.md) (it has
      blank placeholders waiting for these values).
- [ ] **Confirm Point-in-Time Recovery (PITR)** is available and note the
      recovery granularity (e.g. "any second within 7 days").
- [ ] **Run one real restore drill:** restore the latest backup into a *throwaway*
      database (never prod), boot the app against it read-only, confirm row counts
      and a recent order/payment are present. Record RTO (time to restore) and RPO
      (data-loss window) in the DR runbook's TBD fields.
- [ ] Set a calendar reminder to repeat the drill quarterly.

## 2. Guard the production DATABASE_URL  🔴

Root cause of the 2026-07-11 prod crash-loop: a non-prod deploy ran
`alembic upgrade head` against the **prod** database because it shared
`DATABASE_URL`. The Dockerfile migrates at every container start.

- [ ] **No preview / branch / local environment may use the prod `DATABASE_URL`.**
      Give every non-prod environment its own database.
- [ ] In Railway, verify no preview/branch deploy inherits the prod DB variable.
- [ ] Restrict who/what can run migrations against prod (only the master deploy).
- [ ] (Optional cleanup) Remove the stale unused `CORS_ORIGIN` (singular) var from
      Railway — harmless but confusing next to `CORS_ORIGINS`.

## 3. Production environment variables  🟠

- [ ] `MPESA_CALLBACK_TOKEN` is set in prod (app refuses to boot without it when
      M-Pesa is configured — `startup_checks.py`).
- [ ] `CORS_ORIGINS` includes the exact Vercel domain
      (`https://restaurant-agent-seven.vercel.app` and any custom domain).
- [ ] `SECRET_KEY` is set and stable (rotating it invalidates all JWTs / logs
      everyone out).
- [ ] `SENTRY_DSN` is set (enables error + performance monitoring; see item 5).
- [ ] After any backend URL/account change, **repoint the three silent-failure
      integrations** (they fail without erroring):
  - [ ] Safaricom Daraja registered `CallBackURL` →
        `https://<backend>/webhooks/mpesa/<MPESA_CALLBACK_TOKEN>`
  - [ ] Twilio WhatsApp inbound webhook → `https://<backend>/webhooks/whatsapp`
  - [ ] Vercel `NEXT_PUBLIC_API_URL` → new backend URL

## 4. GitHub branch protection  🟠

Makes the review + green-CI policy enforced rather than a convention. The new
[.github/CODEOWNERS](../.github/CODEOWNERS) file only takes effect once this is on.

- [ ] Protect `master`: require pull request before merging.
- [ ] Require status checks to pass: `pytest`, `dependency-audit`, `sast`,
      `frontend-ci`, `gitleaks` (leave `container-scan` non-required until its
      baseline is triaged — see [tech-debt-register.md](tech-debt-register.md)).
- [ ] Require review from Code Owners.
- [ ] Do not allow force-push / deletion of `master`.

## 5. Monitoring & alerting  🟠

- [ ] In Sentry, set `SENTRY_DSN` in prod and author alert rules:
      new-issue, error-rate spike, and P95 latency regression.
- [ ] Add an uptime monitor (UptimeRobot / Betterstack) hitting `/health` and
      `/health/db` every 1–5 min, alerting to the owner's phone/email.
- [ ] Decide and record an on-call / who-gets-paged rota (even if it's "just me")
      in [operations-and-reliability.md](operations-and-reliability.md)'s Open items.

## 6. Later, when scale justifies it  ⚪ (not yet)

Tracked here so they aren't forgotten — deferred by design (see the roadmap):

- [ ] Provision managed Redis (unblocks multi-worker, distributed rate limiting,
      caching) — this is the keystone for the reliability-depth phase.
- [ ] OWASP ZAP baseline scan against staging.
- [ ] Load test to find the real capacity ceiling.

---

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial external-action checklist (Phase 3b); companion to the code hardening pass |
