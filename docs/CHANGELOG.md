# Changelog

Notable changes to the Leviii AI platform and its documentation. Newest first. Derived from
git history on `feat/phase1-production-hardening`.

## Unreleased — In-app notifications & delivery health (2026-08-04)

### Added
- **In-app owner alerts.** `notifications` table (migration 025) + `backend/notifications.py`
  + `GET/POST /api/v1/notifications` + a dashboard bell with unread badge and deep links.
  Alerts are committed in-app first and forwarded to WhatsApp/SMS best-effort, so a
  deployment with no messaging provider still surfaces every alert.
- **Notification-chain health.** `backend/notifications_health.py`,
  `GET /health/notifications` (503 when nothing can be delivered), boot-time warnings in
  `startup_checks`, and `execution/verify_notifications.py` for pre-demo preflight.
- **Cold-outreach SOP** (`directives/015_cold_outreach.md`) and a deterministic lead
  pipeline (`execution/outreach_pipeline.py`).

### Fixed
- Owner alerts were raised behind an `if owner_phone:` gate and a configured Twilio
  account. With neither, the system computed the alert, wrote an audit log, and told
  nobody — with no trace in the product. Nine alert sites now route through
  `notifications.deliver()`.
- The supplier-late and repeated-agent-failure handlers resolved the owner phone from
  env vars only, ignoring the `owner_phone` column entirely (the same bug already fixed
  for stock alerts in migration 006).
- `TWILIO_WHATSAPP_FROM` defaults to Twilio's shared public sandbox number; a deploy that
  forgets to set it gets "sent" back for every message while reaching only handsets that
  texted the sandbox join code. Now detected and warned about explicitly.

### Changed
- **Documentation corrected against the code** (operations-and-reliability §1,
  control-evidence-matrix §7/§9, architecture §6): uptime monitoring is recorded as
  **not wired** rather than "continuous per SLA §04" — the endpoints exist, but nothing
  polls or pages. This was the E1 over-claim in `docs/sales/legal-reconciliation.md`.

### Notes
- Full backend test suite: **394 passing**. Bandit clean at `-ll`; frontend `tsc --noEmit`
  clean; `next build` green (18 routes).

## Documentation & hardening (2026-07-11)

### Added
- **Trust documentation set** under `docs/`: Control Evidence Matrix, Technical & Client
  Trust Centers, Architecture, Engineering Standards, Operations & Reliability, AI
  Governance, Threat Model + Risk Register, Compliance Matrix, FAQ, ADRs, this changelog,
  and a tech-debt register. Grounded in the codebase; operational actuals marked TBD.
- **Legal-pack redline change-list** for the externally-generated 12-document legal set.
- **RBAC enforcement** — `require_role` dependency applied to admin-sensitive routes
  (data export/erasure, `/api/v1/ai/usage`, restaurant profile) with `test_rbac.py`.
- **Password policy at registration** — minimum 8 chars incl. letters + digits.
- Argon2id variant pinned explicitly (`argon2__type="ID"`).

### Changed
- **AI documentation reconciled with shipped code** across the doc set (architecture,
  AI governance, ADR 0005, both trust centers, control-evidence matrix, threat model,
  compliance matrix, engineering standards, FAQ): the LLM is now documented as used in
  **two** non-computing roles — WhatsApp free-text **and** a grounded reasoning/narration
  layer over the deterministic analytics — with the "LLM never computes" invariant and the
  grounding-redaction control stated explicitly, plus the Groq→Anthropic Claude tiered
  upgrade path.

### Notes
- Full backend test suite: **206 passing** *(at the time of that entry; see the 2026-08-04 entry for the current figure)*.

## Prior (from git history)

- `79908e8` — AIOps: `GET /api/v1/ai/usage` (token spend, agent latency, grounding).
- `638a61a` — `/api/v1` versioning + JWT session revocation (`token_version`).
- `29f188b` — Fail-closed startup config guard + green test suite.
- `cb97fae` — Stock-alert tests pinned to deterministic service hours.
- `4362786` — DB integrity constraints + disaster-recovery runbook.

## Conventions

- Group entries under Added / Changed / Fixed / Security.
- Reference the commit or PR. Move "Unreleased" to a dated version on release.

_Owner: Engineering · Contact: leviiiaikenya@gmail.com_
