# Leviii AI — Threat Model & Risk Register

| | |
|---|---|
| **Reference** | LAI-THREAT-001 |
| **Classification** | Confidential — shared under NDA |
| **Audience** | Security engineers, auditors |
| **Version** | 1.0 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose & scope

A STRIDE-based threat model of the production platform, plus a risk register. Every "control"
below is cross-referenced to the [Control Evidence Matrix](../trust/control-evidence-matrix.md)
so a reviewer can confirm it exists in code. Scope: frontend, API, database, AI layer, and
the M-Pesa/Twilio/Groq integrations.

## Trust boundaries

1. Untrusted client ↔ Frontend (Vercel)
2. Frontend ↔ API (Bearer JWT over HTTPS)
3. API ↔ Database (ORM, tenant-scoped)
4. API ↔ third parties (Groq, Twilio, Safaricom) — per-tenant, minimum data
5. Tenant ↔ Tenant (isolation boundary — the highest-value boundary)

---

## STRIDE analysis

| # | Threat (STRIDE) | Vector | Control | Residual |
|---|---|---|---|---|
| T1 | **Spoofing** — credential stuffing / brute force | Repeated login attempts | Argon2id; per-IP rate limit 10/min→429; per-account lockout 5/15min; tested | Low |
| T2 | **Spoofing** — stolen/replayed token | Leaked JWT | 8h expiry; `token_version` revocation via `/logout-all` | Low–Med (no device binding) |
| T3 | **Tampering** — SQL injection | Malicious input | SQLAlchemy ORM parameterization; typed Pydantic bodies; Bandit SAST | Low |
| T4 | **Tampering** — CSV/formula injection in exports | Customer-supplied fields in CSV | `_csv_safe` neutralizes formula prefixes (`routers/export.py`) | Low |
| T5 | **Repudiation** — deny an AI action | Disputed change | Append-only `AgentAuditLog` (what/why/who) | Low |
| T6 | **Info disclosure** — cross-tenant (IDOR) | Enumerate another tenant's IDs | Query-layer `restaurant_id` scoping → 404; IDOR test suite in CI | Low |
| T7 | **Info disclosure** — privilege escalation | STAFF hits admin action | `require_role` on admin-sensitive routes (coverage expanding) | **Med — coverage incomplete** |
| T8 | **Info disclosure** — headers/transport | MITM, clickjacking, sniffing | TLS at edge; HSTS; `nosniff`; `X-Frame-Options: DENY` | Low |
| T9 | **Info disclosure** — secrets leakage | Secrets in code/logs | Env-only secrets; `.env` git-ignored; fail-closed startup guard | Low |
| T10 | **DoS** — request flooding | Volumetric abuse | SlowAPI rate limits; provider edge | Med (no WAF documented) |
| T11 | **DoS** — denial-of-messaging | Tenant A erases B's customer opt-out | Ownership pre-flight before phone-global opt-out (`routers/export.py`) | Low |
| T12 | **Elevation** — weak passwords | Guessable owner password | Registration policy (min-8, letters+digits) | Low–Med |
| T13 | **Supply chain** — vulnerable dependency | Known CVE pulled in | pip-audit (blocking) + npm audit; Bandit SAST | Low |
| T14 | **AI-specific** — prompt injection / data exfil via LLM | Malicious free-text to WhatsApp Brain | Two bounded LLM roles only: (a) unmatched WhatsApp free-text, (b) narration of a server-built deterministic payload (no raw user text). Structured commands deterministic; LLM computes nothing; narration grounded (unbacked numbers redacted); advisory-only, human-in-loop; no training on data | Med (LLM output still owner-reviewed) |

## Risk register

| ID | Risk | Likelihood | Impact | Rating | Treatment | Owner |
|---|---|---|---|---|---|---|
| R1 | Incomplete RBAC coverage lets STAFF reach non-POS routes | Med | Med | **Med** | Extend `require_role` to all operational routes (tech-debt) | Eng |
| R2 | Stolen JWT usable up to 8h | Low | Med | Med | `/logout-all` on suspicion; consider shorter expiry / device binding | Eng |
| R3 | No WAF / advanced DoS protection documented | Low | Med | Med | Rely on provider edge; evaluate WAF | Eng |
| R4 | Audit log has no retention/purge (DPA wording mismatch) | Med | Low | Low–Med | Add purge or reconcile DPA §04 wording | Eng |
| R5 | Multi-restaurant tenant resolves to first restaurant | Low | Low | Low | Explicit restaurant selection (tech-debt) | Eng |
| R6 | Request schemas accept unexpected fields | Low | Low | Low | Add `extra="forbid"` | Eng |
| R7 | No external penetration test yet | Med | Med | Med | Commission external pen test; publish summary | Eng/Mgmt |
| R8 | Reliance on a single provider per tier (Neon/Railway/Vercel) | Low | High | Med | Documented DR + rollback; provider SLAs | Eng |

## Security maturity (snapshot)

| Domain | Level | Note |
|---|---|---|
| AppSec (auth, input, headers) | Strong | Evidence-backed, tested |
| Tenant isolation | Strong | Enforced + IDOR suite |
| Supply chain | Strong | pip-audit + Bandit blocking |
| AuthZ (RBAC) | Developing | Enforced on admin surfaces; coverage expanding |
| Detection/response | Developing | Sentry + IRP; SLIs/rota TBD |
| Third-party assurance | Provider-level | SOC 2 via sub-processors; Leviii AI not itself certified |

## Assumptions & limitations

- Provider edge (Vercel/Railway) handles TLS and basic volumetric protection.
- This model reflects the codebase at 2026-07-11; re-review on major architectural change
  and after every SEV-1 (IRP §03).

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial STRIDE model + risk register |
