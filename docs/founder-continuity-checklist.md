# Founder-continuity checklist (Stage 0, weeks 0-6)

Source: "Automate the routine work, not the founder" report (2026-10). Goal:
the one live restaurant stays well served for 2-4 weeks with the founder
unreachable. Items marked **[code]** are done in this repo; the rest need the
founder, an advocate or dashboard access and cannot be done by an agent.

Exit test: a named second person can pay a supplier, roll back a deploy and
restore the database without the founder.

## Governance and money (confirm each with a Kenyan advocate / KRA tax agent)
- [ ] Second, trusted non-executive director who can give the second signature
      (Safaricom changes Paybill administrators only on a board resolution with two signatories + CR12 under 90 days old)
- [ ] Article letting a nominee / personal representative appoint a director (unverified for Kenyan model articles)
- [ ] Will covering the shares + power of attorney
- [ ] Beneficial-ownership register current (penalty KES 500,000 + 50,000/day)
- [ ] Company bank account + Paybill only; tiered payment mandate
- [ ] Outsourced accountant + tax agent; eTIMS invoices ("no eTIMS invoice, no payment")
- [ ] Register with ODPC; client DPA with sub-processor list (LLM + cloud vendors), no-training clause, AI-limitations clause (allergen/medical to humans)

## Access
- [ ] Company password manager with emergency access; hardware keys for two people
- [ ] Second owner on GitHub org, Railway, Vercel, Neon, OpenRouter/Anthropic, domain registrar, billing card
- [ ] CI uses an org-owned API key, not a personal `claude setup-token`
- [ ] Railway tokens scoped to project/environment; no account token in any agent environment

## Data and delivery
- [ ] Postgres PITR enabled; nightly dump to a different provider/account (secrets in `backup.yml`, see `backend/DISASTER_RECOVERY.md` §1)
- [ ] One production restore drill run and RTO/RPO recorded (DR doc §2)
- [ ] GitHub Team branch protection requiring a human merge approval on private repo
- [ ] External uptime monitor + Sentry; alerts to a phone someone watches
- [x] **[code]** Model-ID audit: retiring `claude-haiku-4-5-20251001` default replaced with `claude-haiku-5-5`; `temperature` no longer sent to Claude 4.7+ (`backend/ai/llm_client.py`)
- [x] **[code]** Operator runbook: rollback, key rotation, token hygiene, who to call (`backend/DISASTER_RECOVERY.md` §6)

Also check the Railway env vars `ANTHROPIC_MODEL_LOW/MEDIUM/HIGH`: they override
the code defaults, so a pinned retiring id there will still fail.
