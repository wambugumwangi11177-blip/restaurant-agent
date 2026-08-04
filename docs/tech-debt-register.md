# Technical Debt & Known Issues Register

| | |
|---|---|
| **Reference** | LAI-DEBT-001 |
| **Classification** | Internal |
| **Version** | 1.1 |
| **Last Updated** | 2026-08-04 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

Tracked, honest list of known gaps. Each links to where it's discussed. Priority: **P1**
(security/correctness) · **P2** (accuracy/consistency) · **P3** (polish).

| ID | Item | Pri | Detail | Source |
|---|---|---|---|---|
| D1 | RBAC coverage incomplete | P1 | `require_role` gates admin-sensitive routes; extend to all operational routes so "STAFF = POS/KDS only" is literally true | [threat-model.md](security/threat-model.md) R1; [ADR 0006](adr/0006-rbac-via-require-role-dependency.md) |
| D2 | Audit-log retention vs DPA wording | P2 | `AgentAuditLog` is append-only with no purge; DPA §04 says "90-day rolling" — implement purge or reconcile wording | [compliance-matrix.md](compliance-matrix.md) §3; redline R-06 |
| ~~D3~~ | ~~Request schemas allow extra fields~~ | — | **RESOLVED** — `StrictModel` sets `extra="forbid"` and is the base for every request/response schema (23 uses in `backend/schemas.py`); an unexpected field now 422s instead of being silently dropped. Closes threat-model R6 | verified 2026-08-04 against `backend/schemas.py:6-13` |
| D4 | Multi-restaurant tenant scoping | P2 | `get_or_create_restaurant` returns the first restaurant; add explicit selection for multi-restaurant tenants | [ADR 0004](adr/0004-query-layer-tenant-isolation.md) |
| D5 | Coverage floor not gated | P3 | Set `--cov-fail-under` once baseline coverage characterised | [engineering-standards.md](engineering-standards.md) §2 |
| D6 | Branch protection unverified | P2 | Confirm/enable required-PR + required-CI on `master` in GitHub settings | [engineering-standards.md](engineering-standards.md) §1 |
| ~~D7~~ | ~~`npm audit` non-blocking~~ | — | **RESOLVED** — blocking at `--audit-level=high` since 2026-07-11; only `container-scan` still carries `continue-on-error` | verified 2026-08-04 against `.github/workflows/ci.yml` |
| D8 | Reliability SLIs not instrumented | P2 | Availability/error-rate SLIs + MTTR/MTTD/error-budget actuals TBD | [operations-and-reliability.md](operations-and-reliability.md) §6 |
| D9 | On-call / alerting rota undefined | P2 | Define paging channel + escalation | [operations-and-reliability.md](operations-and-reliability.md) §1 |
| D10 | No external penetration test | P2 | Commission external test; publish summary (don't imply one until performed) | [threat-model.md](security/threat-model.md) R7 |
| D11 | Starlette CVEs pending fastapi major | P3 | 5 advisories require starlette ≥1.0 (fastapi pins <1.0); tracked, ignored by id with reason | `.github/workflows/ci.yml` |
| D12 | Legal-pack metadata not applied | P2 | Apply owner/revision-history (R-12) at the external source of the 12 legal docs | [legal-doc-redlines.md](trust/legal-doc-redlines.md) R-12 |
| D13 | Pydantic v1-style `class Config` | P3 | Migrate to `ConfigDict` (deprecation warnings) | `backend/schemas.py` |
| D14 | External uptime monitoring not wired | **P1** | Health endpoints (`/health`, `/health/db`, `/health/notifications`) exist and are ready to poll, but nothing subscribes to them and nothing pages. Until this is done the SLA's response-time commitments cannot be evidenced — **hold SLA-001 / BCP-001** | [operations-and-reliability.md](operations-and-reliability.md) §1; [legal-reconciliation.md](sales/legal-reconciliation.md) E1 |
| D15 | Twilio not provisioned | P2 | No messaging account configured, so WhatsApp/SMS forwarding is inert. In-app notifications cover owner alerts meanwhile; customer-facing sends (winback, reservation reminders, order confirmations) have **no** in-app equivalent and simply do not happen | `backend/notifications_health.py`; run `execution/verify_notifications.py` |
| D16 | Notification feed has no retention policy | P3 | `notifications` is append-only and grows with every alert; add a purge/archive once volume justifies it (same shape as D2) | `backend/alembic/versions/025_add_notifications.py` |
| D17 | Frontend still calls legacy unversioned routes | P3 | Auth (own prefix) and the notification bell use `/api/v1/*`; every other call — `/orders/`, `/menu/`, `/inventory/`, `/reservations/`, all `/ai/*` — still hits the legacy unversioned mount. Finish the migration, then drop that mount | `backend/main.py` (dual mount) |

## How this list is used
- New debt is added here when discovered; items are removed when resolved (with a CHANGELOG
  entry). Security items (P1) are reviewed after every SEV-1.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial register consolidated from all trust docs |
| 1.1 | 2026-08-04 | Engineering | Re-verified every item against the code. D3 and D7 were already resolved and are struck through. Added D14 (external monitoring not wired — now P1, it gates the SLA), D15 (Twilio not provisioned), D16 (notification retention), D17 (frontend still on legacy routes). |
