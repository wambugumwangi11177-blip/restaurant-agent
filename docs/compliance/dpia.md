# Data Protection Impact Assessment (DPIA)

> Screening + assessment of privacy risk for restaurant-agent. Kenya DPA 2019
> (Art. 31) / GDPR Art. 35 style. Companion to [ropa.md](ropa.md) and
> [../security/threat-model.md](../security/threat-model.md). **Legal review
> required.** Last updated 2026-07-12.

## 1. Is a DPIA warranted?

Yes (precautionary). Triggers present: processing of personal data at some scale,
automated messaging to individuals, use of a third-party LLM, and payment data.
Not present: special-category data, systematic large-scale monitoring, or solely
automated decisions with legal effect (AI outputs are advisory; money-moving
actions require human approval).

## 2. Data flows

Diner → WhatsApp/POS → backend (Postgres) → [aggregation] → LLM (scrubbed) →
owner. Payments: diner → M-Pesa → webhook → backend. See [ropa.md](ropa.md).

## 3. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation | Residual |
|---|---|---|---|---|
| PII leakage to LLM sub-processor | Med | Med | Regex PII scrub (phones/M-Pesa/PIN/ID) before every LLM call; no raw customer free-text on the narration path; number-grounding | Low |
| Unauthorised access (staff → management data) | Med | High | RBAC enforced on all management/money routes; tenant isolation; optional MFA | Low |
| Credential compromise | Low | High | Argon2id, strong-password policy, lockout, JWT revocation, MFA available | Low |
| Marketing without consent | Low | Med | Consent captured at checkout; global opt-out honoured immediately; sends owner-triggered | Low |
| Data loss | Med | High | Managed backups (verify + restore drill — see external checklist) | Med→Low once drill done |
| Over-retention | Med | Med | Erasure endpoint; retention windows being finalised | Med |
| Injection / unexpected fields | Low | Med | Strict schemas (`extra=forbid`), ORM (no raw SQL), rate limiting, body-size limit | Low |

## 4. Necessity & proportionality

Each activity in the RoPA has a lawful basis and is limited to what the purpose
needs. LLM use is bounded to interpretation over already-computed figures; it
performs no math and executes no data changes without human approval.

## 5. Conclusion

Residual risk is **low-to-medium**, with the two remaining medium items (restore
drill, retention windows) tracked in
[external-hardening-checklist.md](../external-hardening-checklist.md) and the
compliance matrix. No high residual risks that would require prior consultation
with the regulator. **Re-run this DPIA** on any change that adds special-category
data, a new sub-processor, or automated decisions with legal effect.
