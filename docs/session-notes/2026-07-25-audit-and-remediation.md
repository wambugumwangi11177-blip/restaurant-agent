# Session notes — 13-module audit + full remediation (2026-07-25)

Working record of a single extended session: an "AI Audit Prompt Template"-style
review (3 source PDFs, adapted to this codebase) followed by a full remediation
pass against its own findings, then live ops setup (Sentry, UptimeRobot). Kept
here rather than as scattered commit messages so the whole arc is readable in
one place.

## 1. The audit

Three source PDFs, all the same underlying pattern — a checklist of named
checks, each demanding "pass or fail with a specific example":

- Two vertical "certification exam" templates (construction, EdTech), 7 modules
  each, sharing an identical skeleton with domain-specific items swapped in.
- One generic, 13-module ancestor template with no vertical flavor, covering
  the same core ground plus six areas the verticals drop entirely: CI/CD
  hygiene, hosting/deploy config, cloud compute & scaling, paid-API rate
  limiting & cost caps, caching/performance, error-tracking depth.

Reskinned for `restaurant-agent`'s actual domain (M-Pesa, WhatsApp, POS/KDS,
multi-tenant staff roles, paid LLM calls) into 13 modules / 68 individual
checks, using 7+ parallel research passes (Explore-style subagents) plus
direct source reads for evidence. Published as an artifact scorecard.

**Original score: 43/68 (63%).**

## 2. Remediation plan

Turned into a tiered implementation plan (Plan-mode, user-approved) before any
code changed:

- **Tier 0** — ops-gated foundation, no code (Redis provisioning for the
  already-Redis-ready rate limiter).
- **Tier 1** — mechanical fixes: rate limits on every `routers/ai.py` endpoint,
  pagination on two unbounded list endpoints, phone-number log masking,
  deepened `/health/` DB check.
- **Tier 2** — reliability/compliance infra: a `NotificationOutbox` table +
  retry sweep for failed event-bus deliveries, a 90-day `AgentAuditLog` purge
  job.
- **Tier 3** — design-decision items: a daily LLM spend cap (`ai/spend_cap.py`,
  reusing existing `TokenUsage` data, no new table), PII name-scrubbing via a
  denylist built from on-record customer/staff names.
- **Tier 4** — frontend resilience: `dashboard/error.tsx` + `global-error.tsx`
  error boundaries, a POS offline order outbox (IndexedDB, greenfield — no
  existing queue precedent in this frontend).
- **Tier 5** — larger features (included at the user's explicit choice rather
  than deferred): a multi-restaurant switcher (`User.active_restaurant_id`,
  `GET`/`POST /restaurants`) and a shared-device PIN quick-switch
  (`POST /auth/quick-switch`, reusing the existing lockout mechanism).
  Application-layer encryption was deliberately deferred — it needs a KMS
  decision (provider, rotation policy) before any code should be written, not
  something to decide unilaterally.

A real bug was caught and fixed during Tier 5, not a test artifact: the
multi-restaurant switcher's first draft mutated `current_user` (loaded via one
FastAPI dependency's session) and committed a *different* session — confirmed
with raw `sqlite3` reads bypassing the ORM, then fixed by re-querying the user
via the route's own session, the same pattern `routers/auth.py`'s MFA/password
routes already used for exactly this reason.

Commits `8c1ed8f` → `bcbfec8` (6 commits). 569/569 backend tests passing at
this point (up from 539 at session start), clean `tsc`/`eslint`/`next build`
throughout, migration chain 000→042 verified against a fresh `init_db()`-seeded
DB matching the real Dockerfile boot order.

## 3. No-credential follow-up

Checked this environment for cloud/infra credentials before claiming anything
else was blocked — none existed (no GitHub token, AWS, Redis URL, Sentry DSN,
UptimeRobot key). Closed what was still code-only:

- `backend/scripts/load_test.js` — a k6 script (staged ramp to the "10x" case
  the audit itself flagged). Writing it is in scope; running it against real
  staging deliberately isn't, from a coding session.
- `backend/alerting.py` — critical-error alerting wired into the existing
  unhandled-exception handler, firing a Slack-compatible webhook on an error
  *spike* (not per-exception), gated behind `ALERT_WEBHOOK_URL` (unset by
  default, same graceful-no-op posture as this codebase's Twilio/VAPID/SMTP).
- Relocated the 5-script lead-generation cluster (`execution/` →
  `sales/scripts/`, with a README) — it read as unfinished "document
  delivery" product scope on the audit when it's actually outbound sales
  tooling, unrelated to the running app.

Commit `5173af9`. 573/573 tests passing.

## 4. Live ops setup

The user then supplied real credentials mid-session for two services flagged
as blocked:

**Sentry** — a `sntryu_...` token revealed the `leviii` org had zero projects.
With explicit confirmation first (project creation is an external,
account-visible action), created `restaurant-agent-backend`, saved its DSN to
`backend/.env` (gitignored, never committed), and verified it end-to-end by
capturing and flushing a real test exception, then confirming it landed via
the Sentry API — not just configured on faith. Two active alert rules
(new-issue-seen; 10+ events/hour spike), both notifying by email. Commit
`b197ee5`.

**UptimeRobot** — a `u3668703-...` key worked for read operations
(`getAccountDetails`, `getMonitors`) but consistently 403'd on `newMonitor`
across five genuinely different parameter attempts (default/explicit
interval, form vs JSON body, explicit alert-contact) — an account/plan-level
gate on API-based monitor *creation*, not a parameter mistake. The user
created the monitor manually instead; it was initially pointed at the bare
root `/` (a hardcoded static response with no DB check — the exact "shallow
health check" failure mode Module 13 flagged, just relocated from the app's
own routing into the monitor's target). `editMonitor` turned out **not** to be
under the same restriction — repointed it to `/health/` (the deepened check
from Tier 1) via one clean API call, verified the change stuck.

## 5. Where things stand

**Score: 59/68 (87%) at last full artifact update**, up from 43/68 (63%) at
the original audit — see the published artifact for the module-by-module
breakdown and the "What's left" list (backup GitHub secrets, Redis
provisioning, actually running the load test, encryption KMS decision — all
genuinely blocked on the account owner, not on code).

Sentry and UptimeRobot were closed in real time during this same session,
after this note was drafted — check `HARDENING_STATUS.md` and the artifact
for whichever is more current if the two ever drift.
