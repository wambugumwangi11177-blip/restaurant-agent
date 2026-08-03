# Technical Debt & Known Issues Register

| | |
|---|---|
| **Reference** | LAI-DEBT-001 |
| **Classification** | Internal |
| **Version** | 1.2 |
| **Last Updated** | 2026-08-03 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

Tracked, honest list of known gaps. Each links to where it's discussed. Priority: **P1**
(security/correctness) · **P2** (accuracy/consistency) · **P3** (polish).

| ID | Item | Pri | Detail | Source |
|---|---|---|---|---|
| D1 | RBAC coverage: declare roles explicitly | P2 | **Re-scoped 2026-08-03 after a route-by-route audit.** The original remedy ("STAFF = POS/KDS only") is wrong for this product: orders, reservations, and inventory receive/adjust are legitimate floor work that STAFF must reach, so gating them to ADMIN would break the POS. Actual state: menu/inventory create-update-delete, and all of `ai`/`analytics`/`billing`/`enterprise`/`export` **are** ADMIN-gated; the remaining routes use bare `get_current_user`, i.e. any-authenticated-user. The real gap is that this is *implicit* — a new route defaults to "everyone" rather than failing closed. Remedy: declare `require_role(STAFF, ADMIN)` explicitly on floor routes so intent is readable and a future role tier (see D23) has a seam to slot into. The one concrete abuse path found — anonymous stock write-offs — is closed (see CHANGELOG 2026-08-03) | [threat-model.md](security/threat-model.md) R1; [ADR 0006](adr/0006-rbac-via-require-role-dependency.md) |
| D2 | Audit-log retention vs DPA wording | P2 | `AgentAuditLog` is append-only with no purge; DPA §04 says "90-day rolling" — implement purge or reconcile wording | [compliance-matrix.md](compliance-matrix.md) §3; redline R-06 |
| D3 | Request schemas allow extra fields | P2 | Add `extra="forbid"` to make "strict validation" literal | [control-evidence-matrix.md](trust/control-evidence-matrix.md) §3 |
| D4 | Multi-restaurant tenant scoping | P2 | `get_or_create_restaurant` returns the first restaurant; add explicit selection for multi-restaurant tenants | [ADR 0004](adr/0004-query-layer-tenant-isolation.md) |
| D5 | Coverage floor not gated | P3 | Set `--cov-fail-under` once baseline coverage characterised | [engineering-standards.md](engineering-standards.md) §2 |
| D6 | Branch protection unverified | P2 | Confirm/enable required-PR + required-CI on `master` in GitHub settings | [engineering-standards.md](engineering-standards.md) §1 |
| D8 | Reliability SLIs not instrumented | P2 | Availability/error-rate SLIs + MTTR/MTTD/error-budget actuals TBD | [operations-and-reliability.md](operations-and-reliability.md) §6 |
| D9 | On-call / alerting rota undefined | P2 | Define paging channel + escalation | [operations-and-reliability.md](operations-and-reliability.md) §1 |
| D10 | No external penetration test | P2 | Commission external test; publish summary (don't imply one until performed) | [threat-model.md](security/threat-model.md) R7 |
| D11 | Starlette CVEs pending fastapi major | P3 | 5 advisories require starlette ≥1.0 (fastapi pins <1.0); tracked, ignored by id with reason | `.github/workflows/ci.yml` |
| D12 | Legal-pack metadata not applied | P2 | Apply owner/revision-history (R-12) at the external source of the 12 legal docs | [legal-doc-redlines.md](trust/legal-doc-redlines.md) R-12 |
| D13 | Pydantic v1-style `class Config` | P3 | Migrate to `ConfigDict` (deprecation warnings) | `backend/schemas.py` |
| D14 | AI/LLM spend has no enforced cap | P2 | `/ai/*`/`/analytics/*` meter tokens via `TokenUsage` but never block on cost; a runaway loop or shared admin credential could run unbounded LLM spend | `backend/ai/cost_model.py`; `backend/routers/ai.py` |
| D15 | POS has no offline order queue | P2 | Directive 006 specs "queue requests if internet fails"; `sw.js` explicitly skips all non-GET and `/api` requests, and the cart is unpersisted `useState` — an order typed during an outage is lost | [006_pos_kds.md](../directives/006_pos_kds.md); `frontend/public/sw.js` |
| D16 | No shared-device staff PIN attribution | P3 | POS tablets are logged in once per shift with no way to attribute which staff member rang up an order without a full re-login | `backend/models.py` User |
| D17 | Frontend has zero test coverage | P2 | No jest/vitest installed; `frontend-ci` only builds + typechecks; core money logic (cart, formatters) is unverified by any automated test | `frontend/package.json`; `.github/workflows/ci.yml` |
| D18 | No staff account deactivation | P1 | `User` has no `is_active` column and no deactivate endpoint; a departing employee's credentials remain valid indefinitely | `backend/models.py`; `backend/routers/auth.py` |
| D19 | POS order form swallows failed submissions silently | P2 | `pos/page.tsx` catch block only `console.error`s — the waiter gets zero feedback when an order fails to submit | `frontend/src/app/dashboard/pos/page.tsx` |
| D20 | Near-zero frontend accessibility | P2 | 1 `aria-*` attribute in the whole app; modal close is a non-semantic `<div onClick>`; no a11y lint/test tooling | `frontend/src/components/ai/DecisionCard.tsx`; `frontend/src/app/dashboard/marketing/page.tsx` |
| D21 | No code splitting on an 11-section dashboard | P3 | Zero `dynamic()`/`React.lazy` anywhere — full bundle loads upfront | `frontend/src/app/dashboard/` |
| D22 | No frontend error boundary | P2 | No `error.tsx`/`global-error.tsx` under `frontend/src/app` — an uncaught render error shows an unbranded default screen | `frontend/src/app/` |
| D23 | No read-only/view-only oversight role | P3 | Only SUPERADMIN/ADMIN/STAFF exist — an owner who wants to check numbers without edit risk has no tier for that | `backend/models.py` Role enum |
| D24 | No dynamic content/query caching layer | P3 | Every request hits the DB directly; blocked on Redis provisioning (same root cause as external-hardening-checklist.md #6) | `backend/rate_limit.py` |
| D25 | No auto-scaling configuration | P3 | `railway.json`/`render.yaml` define a single fixed-size service, no replica/scaling block | `backend/railway.json`; `backend/render.yaml` |
| D26 | AI cost not broken out per feature | P3 | `/ai/usage` shows aggregate spend by model, not per-feature-per-tenant — harder to see which capability drives cost | `backend/ai/cost_model.py`; `backend/routers/ai.py` |

## How this list is used
- New debt is added here when discovered; items are removed when resolved (with a CHANGELOG
  entry). Security items (P1) are reviewed after every SEV-1.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial register consolidated from all trust docs |
| 1.1 | 2026-08-02 | Engineering | Added D14–D26 from a platform audit graded against a generic + construction + EdTech SaaS checklist; removed D7 (found already resolved 2026-07-11, row never cleaned up); added D27 (blocking npm audit gate found red, discovered while adding frontend test scaffolding for D17) |
| 1.2 | 2026-08-03 | Engineering | Removed D27 (resolved — Next 16.2.12 + postcss/sharp `overrides`, gate green with build/typecheck/tests passing). Re-scoped D1 from P1 to P2 after a route-by-route audit showed its original remedy would break the POS; the one concrete abuse path it implied (anonymous stock write-offs) is fixed |
