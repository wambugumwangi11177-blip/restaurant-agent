# Documentation Roadmap — Status & Plan of Record

| | |
|---|---|
| **Reference** | LAI-ROADMAP-001 |
| **Classification** | Internal |
| **Version** | 1.1 |
| **Last Updated** | 2026-08-04 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose

Tracks the 12-phase Documentation Roadmap v2.0 against reality. This is a **living
document**: each row records the current state and where the work lives, so anyone can see
what exists, what is in progress, and what still needs input.

**Guiding rule:** every document is grounded in the codebase or the existing legal pack.
Where a claim would require operational data we cannot yet measure (real MTTR, capacity
figures, historical postmortems), the document states the target and marks the actual value
**TBD — to be measured**, rather than inventing a number. Honesty is the product.

## Status legend

**Done** · **Partial** (structure + grounded content, some TBDs) · **Planned** (not started)

## Phase status

| Phase | Topic | Status | Artifact(s) |
|---|---|---|---|
| 1 | Documentation Accuracy | Done | [legal-doc-redlines.md](legal-doc-redlines.md) — over-claim fixes, consistency, R-12 metadata standard |
| 2 | Verification & Evidence | Done | [control-evidence-matrix.md](control-evidence-matrix.md) |
| 3 | Engineering Governance | Done | [../engineering-standards.md](../engineering-standards.md) |
| 4 | Architecture Documentation | Done | [../architecture.md](../architecture.md) |
| 5 | Operational Documentation | Partial | [../operations-and-reliability.md](../operations-and-reliability.md) — backup/deploy grounded; health endpoints documented as monitor targets. **External uptime polling + paging still not wired** (D14, gates the SLA); alerting rota TBD |
| 6 | AI Documentation | Done | [../ai-governance.md](../ai-governance.md) |
| 7 | Security Documentation | Partial | [../security/threat-model.md](../security/threat-model.md) (threat model + risk register + SDLC in eng-standards); external pen-test summary Planned |
| 8 | Reliability Documentation | Partial | [../operations-and-reliability.md](../operations-and-reliability.md) — SLO/RTO/RPO grounded from SLA/BCP; MTTR/MTTD/error-budget actuals TBD |
| 9 | Compliance Documentation | Done | [../compliance-matrix.md](../compliance-matrix.md) |
| 10 | Customer Trust Documentation | Partial | [trust-center-technical.md](trust-center-technical.md), [trust-center-client.md](trust-center-client.md), [../faq.md](../faq.md); onboarding/admin/user guides Planned |
| 11 | Document Quality | Partial | Metadata standard (R-12) applied to all new docs; retro-apply to the 12 legal docs pending (redlines) |
| 12 | Living Documentation | Partial | [../adr/](../adr/), [../CHANGELOG.md](../CHANGELOG.md), [../tech-debt-register.md](../tech-debt-register.md); postmortem archive starts at first incident |

## What still needs YOUR input (cannot be grounded from code)

These are deliberately left as TBD rather than fabricated:

1. **Reliability actuals** — real MTTR/MTTD, error-budget burn, and capacity/throughput
   numbers require production measurement. Method is defined in
   `operations-and-reliability.md`; plug in numbers once measured.
2. **Alerting rota / on-call** — who is paged and how (PagerDuty/phone/WhatsApp) is an
   operational decision.
3. **External penetration test** — a "Pen Test Summary" (Phase 7) should only be published
   once an external test is actually performed. Automated controls (pip-audit, Bandit, IDOR
   suite) are documented today.
4. **Customer guides** (onboarding/admin/user, Phase 10) — best written against the live UI;
   flagged for a docs pass with screenshots.
5. **Legal-pack metadata (Phase 11)** — owner/revision-history blocks must be applied at the
   external source of the 12 legal docs (see redlines R-12); their source files are not in
   this repo.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial 12-phase status + plan of record |
| 1.1 | 2026-08-04 | Engineering | Phase 5 re-stated: health endpoints now exist as monitor targets, but external polling/paging is still unwired (D14) — the previous docs implied monitoring was in place |
