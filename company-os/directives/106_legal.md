# Directive 106 — Legal & Compliance (founder writes, advisors read)

**Not legal advice.** The OS contains no statute text, lawful-basis list, registration threshold or legal deadline. It organizes your lawyer's conclusions and reminds you of dates.

**Records:**
- contract: kind, status, dates, auto-renews, `notice_days`, value, attached document.
- obligation: `verified` defaults to false, with a `source_clause`.
- legal_template: `{{placeholders}}`, plus who reviewed it (`reviewed_by`) and when (`reviewed_on`).
- processing_activity: the data-processing register for the Kenya Data Protection Act 2019. Each entry records its role (controller or processor), purpose, categories, data subjects, lawful basis *as advised*, recipients, whether data crosses borders, retention, and who reviewed it.

**Rules** (enforced in code):
- The contract reader can only record an obligation whose `source_clause` is an **exact quote** from the attached contract text. Agent-extracted obligations stay **unverified** until a person verifies them.
- The template filler **refuses** a template with no recorded lawyer review. Editing a reviewed template's text **voids the review**.

**Agents:** contract_reader (LLM), template_filler (deterministic).

**Job:** `obligations_check` (daily) reports notice deadlines (end date minus notice days) within 30 days and obligations due within 7.

**Reports:** legal.renewals (parameter `days`), legal.obligations, legal.register.

**Done gate:** every signed contract is in, and every date is extracted and verified by the founder. Status: ⏳ open. It needs your contracts, and a lawyer's review of templates and of the register, including whether ODPC registration applies to you.
