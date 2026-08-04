# Leviii AI — Operations & Reliability

| | |
|---|---|
| **Reference** | LAI-OPS-001 |
| **Classification** | Confidential — shared under NDA |
| **Audience** | Engineers, SRE, technical due diligence |
| **Version** | 1.0 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose & scope

How the platform is run: monitoring, logging, backup/restore, secret rotation, deployment,
maintenance windows, and the reliability targets (SLOs/SLIs, RTO/RPO). Targets are grounded
in the SLA (LAI-SLA-001) and BCP (LAI-BCP-001). **Measured actuals** (MTTR, MTTD,
error-budget burn, capacity) are marked **TBD — to be measured**; the method is defined so
the numbers can be filled in from production data rather than guessed.

---

## 1. Monitoring & alerting

- **Error + performance monitoring:** Sentry (`backend/main.py`), 20% trace sample, enabled
  when `SENTRY_DSN` is set. Captures exceptions with limited request context.
- **AI observability:** `GET /api/v1/ai/usage` (`backend/routers/ai.py`) — LLM token spend
  by model, per-agent latency (p50/p95), success rate, grounding trust rate.
- **Health endpoints (monitor targets):** `GET /health` (liveness), `GET /health/db`
  (database reachability), and `GET /health/notifications` (outbound alert chain —
  503 when nothing can be delivered, 200 with a detail body when degraded).
- **Uptime monitoring:** **NOT YET WIRED (operator action).** The health endpoints above
  exist and are ready to be polled, but no external monitor is currently subscribed to
  them and nothing pages anyone. Until an external monitor is configured
  (see [external-hardening-checklist.md](external-hardening-checklist.md) §5), incident
  detection is manual. Correcting an earlier version of this section, which stated
  monitoring was "continuous per SLA §04" — that describes the intended state, not the
  built one, and it is an SLA-backed claim that could not be evidenced.
- **Alerting rota / on-call:** **TBD (operational decision)** — define channel (WhatsApp
  direct line is used today for SEV-1 per SLA) and escalation. Document who is paged and how.

> ⚠ **Do not quote the SLA's 15-minute SEV-1 / 24-7 / "automatic alerting" numbers to a
> client until an external monitor is actually polling the endpoints above.** Speak to
> intent, not to a signed number. Tracked as E1 in
> [sales/legal-reconciliation.md](sales/legal-reconciliation.md).

## 2. Logging

| Log type | Source | Notes |
|---|---|---|
| Application errors | Sentry | Diagnostics + limited request context |
| Access logs | Railway platform | Request-level |
| AI-action audit | `AgentAuditLog` (append-only) | What changed, why, who approved |
| Auth events | `last_login_at`, lockout counters | Staff-activity + brute-force signals |
| Owner alerts | `notifications` (in-app feed) + `agent_messages` (WhatsApp/SMS attempts) | Every operational alert raised — see below |

**Owner alert delivery.** Operational alerts (critical/depleted stock, late supplier,
failed M-Pesa settlement, slow day, morning briefing, repeated agent failure) are written
to the `notifications` table *first and unconditionally*, then forwarded to WhatsApp/SMS
on a best-effort basis. In-app delivery has no external dependency, so a deployment with
no Twilio account still surfaces every alert in the dashboard bell. `agent_messages`
records the outcome of each wire attempt; `GET /health/notifications` reports the recent
failure rate over both.

Retention: audit log is currently append-only (no auto-purge) — reconcile the DPA "90-day
rolling" wording or add a purge job (tracked in [tech-debt-register.md](tech-debt-register.md)).

## 3. Backup & restore

- **Database:** Neon WAL + daily snapshots; **point-in-time restore** to any second within
  the retention window. Procedure in `backend/DISASTER_RECOVERY.md`.
- **Code:** GitHub is the source of truth; Railway/Vercel redeploy any prior commit.
- **Config:** environment variables documented securely offline; nothing lives only in a
  local environment.
- **Restore drill:** BCP schedules a bi-annual simulated failover on staging (LAI-BCP-001
  §07). Last drill: **TBD — record on first execution.**

## 4. Secret rotation

- Secrets are environment variables only; `.env` is git-ignored; a fail-closed startup guard
  refuses to boot in production if `SECRET_KEY` (or an M-Pesa callback token, when M-Pesa is
  configured) is missing (`backend/startup_checks.py`).
- **JWT key rotation:** rotating `SECRET_KEY` invalidates all tokens (acceptable — 8h
  expiry). For targeted revocation without a global key change, bump a user's
  `token_version` (`/logout-all`).
- **Rotation cadence:** **TBD (policy)** — recommend documented quarterly rotation of
  provider keys/tokens.

## 5. Deployment & maintenance

- **Deploy:** merge to `master` → CI green → Railway (API) + Vercel (frontend). See
  [Engineering Standards](engineering-standards.md).
- **Maintenance windows:** 02:00–04:00 EAT, ≤2 hours/month, ≥24h notice (SLA §03).
- **Status page:** planned (`status.leviii.ai`); until live, incident updates go via WhatsApp
  + email (BCP §06).

## 6. Reliability targets

### SLOs (from SLA §03 — contractual)

| Service | Monthly uptime SLO |
|---|---|
| Core POS / KDS | 99.5% |
| API Backend | 99.5% |
| Dashboard & Analytics | 99.5% |
| AI Intelligence Engine | 99.0% |
| WhatsApp Brain | 99.0% |

**Downtime definition:** total inaccessibility or >50% error rate for >5 consecutive minutes
(SLA §03). **Error budget** = 1 − SLO (e.g. 0.5%/month ≈ 3h39m for a 99.5% service).

### SLIs (measurement method)

| SLI | How measured | Current value |
|---|---|---|
| Availability | successful / total requests over 5-min windows | TBD — instrument |
| Latency | API p50/p95 (Sentry traces; AI via `/ai/usage`) | Partially available |
| Error rate | 5xx / total | TBD — from Sentry/Railway |
| AI success rate | per-agent success (`/ai/usage`) | Available per tenant |

### RTO / RPO (from BCP §02)

| Service | RTO | RPO |
|---|---|---|
| Core POS / KDS | 15 min | ~0 (real-time replication) |
| API Backend | 15 min | ~0 (auto-restart) |
| Database | 30 min | ≤5 min (Neon WAL) |
| AI Intelligence | 1 hour | none (read-only) |
| WhatsApp Brain | 2 hours | none (queued) |
| Full platform | ≤2 hours | ≤5 min |

### Operational metrics (to be measured — not fabricated)

| Metric | Definition | Value |
|---|---|---|
| MTTD (mean time to detect) | incident start → detection | **TBD — measure from incident log** |
| MTTR (mean time to recover) | detection → service restored | **TBD** |
| Error-budget burn | budget consumed / month | **TBD — once SLIs instrumented** |
| Capacity headroom | peak load vs provisioned | **TBD — load characterisation** |

## Open items

- Instrument availability/error-rate SLIs and backfill the TBD tables.
- Define on-call/alerting rota.
- Record backup-restore drill results and set secret-rotation cadence.

> The operator-facing, tick-box version of the backup drill, alerting/uptime, and
> branch-protection actions lives in
> [external-hardening-checklist.md](external-hardening-checklist.md) (Phase 3b).

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial ops+reliability; SLO/RTO from SLA/BCP, actuals TBD |
| 1.1 | 2026-08-04 | Engineering | §1 corrected: uptime monitoring is **not** wired (the previous "continuous per SLA §04" wording described intent, not the build) and now names the three health endpoints available as monitor targets, including the new `/health/notifications`. Added the in-app owner-alert channel to §2. |
