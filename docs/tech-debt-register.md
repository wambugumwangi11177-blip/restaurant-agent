# Technical Debt & Known Issues Register

| | |
|---|---|
| **Reference** | LAI-DEBT-001 |
| **Classification** | Internal |
| **Version** | 1.2 |
| **Last Updated** | 2026-07-21 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

Tracked, honest list of known gaps. Each links to where it's discussed. Priority: **P1**
(security/correctness) · **P2** (accuracy/consistency) · **P3** (polish).

| ID | Item | Pri | Detail | Source |
|---|---|---|---|---|
| D1 | RBAC coverage incomplete | P1 | `require_role` gates admin-sensitive routes; extend to all operational routes so "STAFF = POS/KDS only" is literally true | [threat-model.md](security/threat-model.md) R1; [ADR 0006](adr/0006-rbac-via-require-role-dependency.md) |
| D2 | Audit-log retention vs DPA wording | P2 | `AgentAuditLog` is append-only with no purge; DPA §04 says "90-day rolling" — implement purge or reconcile wording | [compliance-matrix.md](compliance-matrix.md) §3; redline R-06 |
| D3 | Request schemas allow extra fields | P2 | Add `extra="forbid"` to make "strict validation" literal | [control-evidence-matrix.md](trust/control-evidence-matrix.md) §3 |
| D4 | Multi-restaurant tenant scoping | P2 | `get_or_create_restaurant` returns the first restaurant; add explicit selection for multi-restaurant tenants | [ADR 0004](adr/0004-query-layer-tenant-isolation.md) |
| D5 | Coverage floor not gated | P3 | Set `--cov-fail-under` once baseline coverage characterised | [engineering-standards.md](engineering-standards.md) §2 |
| D6 | Branch protection unverified | P2 | Confirm/enable required-PR + required-CI on `master` in GitHub settings | [engineering-standards.md](engineering-standards.md) §1 |
| D7 | `npm audit` non-blocking | P3 | Make blocking after baseline triage | `.github/workflows/ci.yml` |
| D8 | Reliability SLIs not instrumented | P2 | Availability/error-rate SLIs + MTTR/MTTD/error-budget actuals TBD | [operations-and-reliability.md](operations-and-reliability.md) §6 |
| D9 | On-call / alerting rota undefined | P2 | Define paging channel + escalation | [operations-and-reliability.md](operations-and-reliability.md) §1 |
| D10 | No external penetration test | P2 | Commission external test; publish summary (don't imply one until performed) | [threat-model.md](security/threat-model.md) R7 |
| D11 | Starlette CVEs pending fastapi major | P3 | 5 advisories require starlette ≥1.0 (fastapi pins <1.0); tracked, ignored by id with reason | `.github/workflows/ci.yml` |
| D12 | Legal-pack metadata not applied | P2 | Apply owner/revision-history (R-12) at the external source of the 12 legal docs | [legal-doc-redlines.md](trust/legal-doc-redlines.md) R-12 |
| D13 | Pydantic v1-style `class Config` | P3 | Migrate to `ConfigDict` (deprecation warnings) | `backend/schemas.py` |
| D16 | No Manager-facing strategy review UI / no historical review list | P3 | Fixed alongside D15 (see CHANGELOG 2026-07-21): the weekly review notification now correctly deep-links to `/dashboard/ai` — but that page is Owner-only, so a Manager notified of a review still has nowhere to read it, and there's no structured "past reviews" list anywhere (only a 5000-char truncated text blob in `AgentAuditLog`/`MemoryEvent`). Real remaining product gap, not a routing bug. | `frontend/src/components/ai/StrategyAgent.tsx`; `frontend/src/app/dashboard/ai/page.tsx` |

## How this list is used
- New debt is added here when discovered; items are removed when resolved (with a CHANGELOG
  entry). Security items (P1) are reviewed after every SEV-1.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial register consolidated from all trust docs |
| 1.1 | 2026-07-21 | Engineering | Added D14/D15 — two live-reproduced strategist-agent bugs (empty-output turn exhaustion; notification deep-link to the wrong page) found during multi-role staff + AI reasoning layer testing on the Lavy showcase data |
| 1.2 | 2026-07-21 | Engineering | D14 and D15 fixed and verified (45 tests + one live re-run — see CHANGELOG.md), removed from the open list. Renumbered the remaining, distinct product gap D15 surfaced (no Manager strategy UI, no review history) as D16 |
