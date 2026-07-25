# Leviii AI — Compliance Matrix

| | |
|---|---|
| **Reference** | LAI-COMP-001 |
| **Classification** | Confidential — shared under NDA |
| **Audience** | Auditors, DPO, enterprise procurement |
| **Version** | 1.0 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Data Protection / Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose & scope

Maps Leviii AI's controls to KDPA 2019 and the OWASP Top 10, and consolidates data
classification, retention, and the sub-processor register into one reviewer-facing view.
Each control links to evidence in the [Control Evidence Matrix](trust/control-evidence-matrix.md)
or the legal pack.

## 1. Kenya Data Protection Act 2019 mapping

| KDPA obligation | Where satisfied |
|---|---|
| Controller/Processor roles | DPA §01 (client = controller; Leviii AI = processor) |
| Lawful processing / consent | Customer data on consent; PP §02–03; AUP §04 (WhatsApp consent) |
| Data-subject rights (access, rectification, erasure, portability, object, withdraw) | DPA §03; erasure + CSV export implemented (`backend/routers/export.py`) |
| Data minimisation | No card data (M-Pesa reference only); no sensitive data collected (DPA §02) |
| Security safeguards | SEC-001 controls; [Control Evidence Matrix](trust/control-evidence-matrix.md) |
| Breach notification | DPA §06 / IRP: 72h client notice; ODPC filing where required |
| Sub-processor transparency | Sub-Processor List (LAI-SUB-001); §4 below |
| Retention limitation | §3 below; DPA §04 |

## 2. OWASP Top 10 mapping (evidence-backed)

| Risk | Control | Evidence |
|---|---|---|
| Broken Access Control | Tenant isolation + IDOR suite; `require_role` on admin routes | `test_tenant_isolation.py`, `test_rbac.py` |
| Cryptographic Failures | TLS in transit; AES-256 at rest (Neon); Argon2id | `security_headers.py`, provider |
| Injection | ORM parameterization; Pydantic; Bandit | `routers/*.py`, CI `sast` |
| Insecure Design | Threat model; human-in-loop AI | [threat-model.md](security/threat-model.md) |
| Security Misconfiguration | Security headers; fail-closed startup guard | `middleware/security_headers.py`, `startup_checks.py` |
| Vulnerable Components | pip-audit + npm audit (CI) | `.github/workflows/ci.yml` |
| Identification & Auth Failures | Argon2id; rate-limit + lockout; JWT revocation; password policy | `auth.py`, `routers/auth.py`, `test_auth_security.py` |
| Software/Data Integrity | Alembic migrations; DB CHECK/UNIQUE/FK constraints | `alembic/versions/016...` |
| Logging & Monitoring Failures | Sentry; append-only AI audit log; access logs | `main.py`, `models.py` |
| SSRF | No user-controlled outbound URL fetch surface identified | code review |

## 3. Data classification & retention

### Classification

| Class | Examples | Handling |
|---|---|---|
| Sensitive (special category) | **None collected** | N/A (DPA §02) |
| Personal (PII) | Staff email; customer name/phone | Encrypted at rest; access-controlled; erasable |
| Credential | Argon2id password hashes | Irreversible; never logged |
| Financial/operational | Orders, payments (M-Pesa ref), inventory | Retained for tax/audit integrity |
| System | Logs, metrics, audit | Operational use |

### Retention

| Data | Retention | Basis |
|---|---|---|
| Active account data | Duration of subscription | DPA §04 |
| Post-termination | 30 days → permanent deletion | DPA §04 / SLA §08 |
| Backups | 30 days rolling (Neon) | BCP §04 |
| Customer PII on erasure | Scrubbed; financial record retained | DPA §03; KRA note |
| AI-action audit log | 90-day rolling — daily purge job (`audit_log_purge`, `backend/main.py`) hard-deletes rows older than 90 days | DPA §04 |
| Aggregated analytics | Anonymised, indefinite | DPA §04 |

## 4. Sub-processor register (from LAI-SUB-001)

| Sub-processor | Purpose | Location | Assurance |
|---|---|---|---|
| Neon | Database | US East | SOC 2 Type II |
| Railway | API compute | US West | SOC 2 Type II |
| Vercel | Frontend/CDN | Global | SOC 2 Type II |
| Sentry | Error monitoring | US | SOC 2 Type II |
| Twilio | WhatsApp delivery | US | SOC 2 Type II |
| Groq | LLM — WhatsApp free-text + grounded analytics narration | US | Per provider terms (no training) |
| Anthropic | LLM — same two roles (Claude), **conditional/planned upgrade** activated when `ANTHROPIC_API_KEY` is set | US | Per provider terms (no training) |
| Safaricom (M-Pesa Daraja) | Payments | Kenya | PCI-DSS / CBK-licensed |

Feature integrations (Twilio/LLM/M-Pesa) are per-tenant; no data is sent to an inactive
integration. The LLM provider is configuration-driven — Groq today; Anthropic (Claude)
becomes an **active** sub-processor only once its key is configured, at which point this row
moves from planned to active. 30-day notice before adding a sub-processor.

## 5. Audit checklist (reviewer self-serve)

- [ ] Controls exist & evidenced → [Control Evidence Matrix](trust/control-evidence-matrix.md)
- [ ] Tenant isolation tested → `test_tenant_isolation.py`
- [ ] Auth hardening tested → `test_auth_security.py`, `test_rbac.py`
- [ ] Dependency + SAST scanning blocking in CI → `.github/workflows/ci.yml`
- [ ] Breach process defined → IRP (LAI-IRP-001) / DPA §06
- [ ] Retention & erasure defined + implemented → §3, `routers/export.py`
- [ ] Sub-processors disclosed → §4 / LAI-SUB-001

## Note on certification

Leviii AI Technologies is **not itself** SOC 2 / ISO 27001 certified; those certifications
are held by the infrastructure sub-processors above. Leviii AI's own controls are documented
and evidence-backed rather than third-party attested.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Data Protection / Engineering | Initial compliance matrix |
