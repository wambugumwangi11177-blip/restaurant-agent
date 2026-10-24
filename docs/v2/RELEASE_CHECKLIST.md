# Eleven release gates — 24 October 2026

Target platform decision: Android package, Windows/macOS/Linux desktop packages, iPhone/iPad PWA; no iOS App Store. Packaging source is under `packaging/`. Public HTTPS origin and signing material have not been provided. No deployment or production migration has occurred in this completion pass.

## Candidate and migration
- Candidate branch: `codex/eleven-completion`, based on `dev/eleven-demo-fixes` at `654d116`.
- New additive migration: `060_team_workflows`, after 059. Verify actual deployed revision before preparing the migration command; do not assume production is at 050 or 056 from old notes.
- Release must include v2 foundation, Eleven readiness, demo fixes and completion changes. Review ancestry before merging. PR #25 targets readiness, not master.
- Rehearse the full required upgrade on a copy matching the actual PostgreSQL version; test rollback with compatible code. Migration 060 downgrade removes task/review audit data, so it is not a lossless production rollback. Prefer rolling forward or restoring an agreed backup.

## Before production approval
- Full backend, eval, frontend build/typecheck/lint/unit and browser checks pass on the candidate SHA.
- All security checks pass or have narrowly documented existing exceptions.
- Backup and restore rehearsal with measured recovery steps; staging role and branch checks.
- Public domain, TLS, CORS, provider budgets, feature flags, error reporting and scheduler settings verified. No secret values in documentation.
- Real Eleven source tested with Sam according to SAM_READ_ONLY_INTEGRATION.md. Eleven-only server-side read views; no writes to the POS.
- Owner/accountant reconcile a real day against source reports. Confirm missing-data labels.
- Signed Android and desktop artifacts installed/tested; iPhone PWA checked on a physical iPhone. Record versions and hashes. Do not label unsigned outputs production-ready.

## Controlled rollout
Have the release owner approve the concrete candidate, migration evidence and recovery plan. Apply only the agreed release procedure, then verify health, authentication, tenant/branch isolation, first sale/report, queued-entry replay, exports, approvals and audit events. Monitor the first full trading-day rollover and reconcile again. Provisioning and live access remain pending rather than inferred from demo success.
