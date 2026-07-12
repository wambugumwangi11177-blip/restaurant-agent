# Record of Processing Activities (RoPA)

> Engineering-maintained record of what personal data restaurant-agent processes,
> why, and how it's protected. Aligned with Kenya Data Protection Act 2019 (Art.
> 25 accountability) and GDPR Art. 30. Companion to
> [compliance-matrix.md](../compliance-matrix.md); does not supersede it.
> **Legal review required before external publication.**

**Controller:** the restaurant (tenant). **Processor:** restaurant-agent platform.
**Last updated:** 2026-07-12.

## Processing activities

| # | Activity | Data subjects | Personal data | Purpose | Lawful basis | Retention |
|---|---|---|---|---|---|---|
| 1 | Order taking / POS | Diners | Name, phone, order history | Fulfil orders | Contract / legitimate interest | Kept for tax integrity; PII scrubbed on erasure (orders retained, de-identified) |
| 2 | Payments (M-Pesa) | Diners | Phone, M-Pesa receipt code, amount | Settle payment | Contract / legal obligation | As tax records require |
| 3 | Reservations | Diners | Name, phone, email, party details | Manage bookings | Contract | Until fulfilled + reasonable window |
| 4 | WhatsApp messaging | Diners, owner | Phone, message content | Notifications, marketing (consented) | Consent (marketing), legitimate interest (operational) | Opt-out honoured immediately; consent + opt-out state stored |
| 5 | Marketing campaigns | Consented diners | Phone, name, spend segment | Promotions, win-back | **Consent** (explicit, opt-out any time) | Until opt-out |
| 6 | Staff/owner accounts | Owners, staff | Email, password hash (Argon2id), role, MFA secret, login timestamps | Authentication, access control | Contract | Life of account |
| 7 | AI narration / orchestrator | Diners (indirect) | Aggregated figures only; free-text PII scrubbed before any LLM call | Business insights | Legitimate interest | Not retained by us; see sub-processors |
| 8 | Product analytics | Owners, staff | User id, event name, feature usage | Improve product | Legitimate interest | Windowed |
| 9 | Audit / agent logs | Owners, staff | Actor, action, data sources | Security, accountability | Legal obligation / legitimate interest | Retention policy TBD (see compliance-matrix) |

## Sub-processors

| Sub-processor | Purpose | Data shared | Safeguard |
|---|---|---|---|
| Groq / Anthropic (LLM) | AI narration & orchestrator | Aggregated figures; **PII regex-scrubbed** (phones, M-Pesa codes, PIN/ID) before send — see `backend/ai/pii_scrub.py` | Data-minimisation; no raw customer free-text; number-grounding |
| Twilio | WhatsApp delivery | Recipient phone, message | DPA with Twilio |
| Safaricom Daraja (M-Pesa) | Payments | Phone, amount | Regulated payment rails |
| Railway / Neon | Hosting / database | All at-rest data | Provider encryption at rest; access controls |
| Vercel | Frontend hosting / CDN | None at rest (SSR/CSR) | — |
| Sentry (optional) | Error monitoring | Correlation IDs, stack traces (PII-minimised) | Sampling; DSN-gated |

## Technical & organisational measures (summary)

- **Access control:** RBAC (`require_role`), tenant isolation, JWT with revocation, optional TOTP MFA.
- **Data minimisation to third parties:** PII scrubbed before any LLM call.
- **Data subject rights:** erasure endpoint (`POST /data/erase-customer`), consent + global opt-out.
- **In transit:** TLS terminated at the edge (Railway/Vercel). **At rest:** provider-managed encryption.
- **Auditability:** immutable `AgentAuditLog`; correlation-ID-tagged structured logs.

## Open items

- Confirm signed DPAs on file with each sub-processor (owner/legal action).
- Finalise audit-log and analytics retention windows (see [compliance-matrix.md](../compliance-matrix.md)).
