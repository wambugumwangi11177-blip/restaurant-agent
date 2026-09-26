# Company OS — Build Plan (one department at a time)

> **Directive 000: the master plan for Company OS.** Written 2026-09-26, reviewed the same day (see *Review*), and approved by the founder for autonomous execution of Phase 0.
> Phase 0 status and the live done-gate checklist are in `directives/001_kernel.md`.
> Location: this folder is developed inside `restaurant-agent/company-os/` until the dedicated `company-os` GitHub repo exists. The GitHub integration could not create repositories (HTTP 403). Move it with full history using `git subtree split --prefix=company-os` (steps in `README.md`).


## Context
You are a solo founder running a Kenya-based software startup. The first product is `restaurant-agent`, with Vibanda as the live client and a MacSoft integration. The mission is broader: customized software that helps businesses and people run their day-to-day. You want an internal **Company OS**: a team of agents plus interactive business software, connected to every department from legal to operations. It should run your own company first and later be sellable to other businesses.

This plan sets out how to build it without hallucinated parts. We build one department at a time, and each department must pass a written "done" gate before the next one starts.

### Ground truths this plan is built on
- **I cannot train myself on your data.** [Certain] Model weights don't change from use. In this plan, "the OS learns" means three concrete, inspectable mechanisms:
  1. **Company memory.** Documents, decisions and records are stored in Postgres and searched with Postgres full-text search, every hit carrying a citation, and every agent reads from it before acting. Vector search (pgvector) plugs in behind the same interface once an embedding provider is chosen (see Review, correction 3).
  2. **Feedback log.** Every agent output gets approved, edited or rejected by you, and the reason is stored.
  3. **Eval sets.** Your corrections become test cases, and prompts or tools change only if the evals still pass.

  Real ML models (for example deal-win probability or churn) are added only once a department has at least a few hundred labelled records. [Likely] That threshold is a rule of thumb, not a law.
- **Your repo already records one failed "do everything" AI roadmap.** Directive 012 cut federated learning, zero-knowledge proofs and similar work as "theater". This plan follows the same rule: nothing ships that doesn't run end-to-end on real data.
- **The existing architecture principle carries over unchanged** (ADR 0001, 0005). Business logic is deterministic Python. An LLM is used only to interpret free text and plan tool calls. Agents propose; deterministic code executes.
- **Agents never take irreversible or outward-facing actions without your approval.** That covers sending email or WhatsApp to clients, signing, paying, filing, and deleting. Autonomy is widened per action only after its approval log shows 20 or more consecutive un-edited approvals.

## Where it lives and what it's built with
- **New repo: `company-os`** (your choice). You create it on GitHub and add it to the session, or authorize me to create it. Its first commit copies `CLAUDE.md`, the `directives/`+`execution/` layout, `.gitleaks.toml` and the CI (Bandit, gitleaks, pytest, `next build`) from `restaurant-agent`.
- **Stack: the same as restaurant-agent,** so one person maintains one skill set. That means FastAPI, SQLAlchemy 2 and Alembic on the backend, Postgres with **pgvector** (Neon or Railway, both already in use), Next.js 16 with Tailwind on the frontend, WhatsApp through Twilio, and email.
- **Code to copy and adapt from restaurant-agent** (copy, not a cross-repo import, because the two products must deploy independently):
  - `backend/ai/llm_client.py`: provider-agnostic client. The provider order in code is OpenRouter (your chosen gateway since 2026-09-12), then Anthropic, then Groq, with graceful degradation when no key is set. It has `chat_with_tools` and `model_for_tier`.
  - `backend/auth.py`: Argon2id, TOTP MFA, `token_version` revocation, `require_role`.
  - `backend/events/bus.py`: event bus. Also directive 019's rule: **never emit a dead event**.
  - `backend/ai/spend_cap.py`, `pii_scrub.py`, `backend/feature_flags.py`, `observer_mode.py`, `alerting.py`, `logging_config.py`, `rate_limit.py`.
  - `docs/adr/*` and `docs/engineering-standards.md` as the starting standards set.
- **Multi-tenant from day one.** Every row carries a `workspace_id`, using the query-layer isolation pattern from ADR 0004. Your company is workspace #1. This is the one "future-ready" decision that is cheap now and very expensive to retrofit later. Nothing else gets built for hypothetical future customers.

## Build status (updated 2026-09-26)
Every phase's **software** is built, tested (real Postgres) and in the web UI. Every **done gate** below is about real use, and stays open until the founder uses it. Code cannot close those gates, and they are not reported as closed.

| Phase | Directive | Software | Done gate |
|---|---|---|---|
| 0 Kernel | 001 | ✅ | partly: see 001 (needs your documents, Twilio, deployment) |
| 1 Command Center | 101 | ✅ | ⏳ 10 working days of real briefs |
| 2 Sales | 102 | ✅ | ⏳ real pipeline imported |
| 3 Delivery | 103 | ✅ | ⏳ Vibanda status produced from the OS |
| 4 Support | 104 | ✅ | ⏳ your SLA policy plus 30 days |
| 5 Finance | 105 | ✅ (never moves money; no tax/FX rules built in) | ⏳ one month reconciled; accountant confirms tax |
| 6 Legal | 106 | ✅ (no legal rules built in) | ⏳ contracts in; lawyer reviews templates and register |
| 7 Marketing | 107 | ✅ | ⏳ Vibanda consent plus a published case study |
| 8 Product | 108 | ✅ | ⏳ next release planned from OS data |
| 9 People | 109 | ✅ | n/a until the first hire |
| 10 Productize | 110 | ✅ limits, plans, gated signup, usage · ❌ **billing** (needs your payment-provider and pricing decision) | ⏳ after 60+ days of your own use |

The founder authorized building all phases at once on 2026-09-26, overriding the plan's original "one gate before the next" pacing. The gates remain the definition of done.

---

## Review (2026-09-26): corrections and additions
This review checked the plan's claims against the restaurant-agent source and this machine's toolchain.

**Corrections (the earlier draft was wrong):**
1. *"Groq runs today."* Wrong. `llm_client.py` selects OpenRouter first, and `requirements.txt`'s comment is stale. Fixed above.
2. *"Google Calendar connector already exists."* Misleading. That connector belongs to the Claude session, not to deployable software. The OS needs its own OAuth client. Fixed above.
3. *"Embed into pgvector."* The plan had no embedding provider. OpenRouter, Groq and Anthropic are chat providers in this stack, and none is wired for embeddings. Anthropic itself offers no embedding model. The fix is **Postgres full-text search first**: deterministic, free, no new key, and testable. A `Retriever` interface lets vector or hybrid search be added once a key exists. Retrieval quality is measured by the eval set either way.

**Additions (the earlier draft was missing these):**
4. **Prompt-injection defense.** Ingested documents, emails and WhatsApp text are untrusted, and restaurant-agent already had a real injection attempt (directive 012). Untrusted text is delimited and labelled in every prompt. The tool gate is enforced in the runtime, not by the model, so injected text can never trigger an outward action without an approval.
5. **Modular-monolith boundary.** Each department is its own package (`app/departments/<name>/`), with its own models, routes, agents and directive. Departments talk only through Kernel services and events, never by importing each other. That rule is what keeps building one department from breaking another.
6. **Kenya Data Protection Act data rights from day one.** A person's data can be exported and erased per workspace. Erasure scrubs PII and keeps audit rows.
7. **Conventions.** Money is stored as integer minor units plus an ISO currency code (default KES). Timestamps are UTC in the database and shown in Africa/Nairobi.
8. **Config guard.** The app refuses to boot in production with default secrets. It degrades cleanly when LLM or Twilio keys are missing.
9. **Tests on real Postgres, not SQLite.** Full-text search, constraints and isolation must be tested on the engine production runs. CI uses a Postgres service container.
10. **Minimal web shell in Phase 0.** Approval inbox, records, memory search and audit log, because an approval gate you can't see is unusable.
11. **Deploy target.** Railway (backend + Postgres) and Vercel (frontend), matching restaurant-agent. Deployment needs your accounts, so it's documented, not performed.
12. **The "20 consecutive approvals" autonomy threshold is a design choice, not a fact.** It is stored per tool as a configurable value.

**Is this the best we can do?** For one founder, yes, with these corrections. [Likely] The alternatives are worse:
- Buying separate SaaS per department fragments your data, and there's no shared memory or approval gate.
- A microservices "OS" multiplies the operational load on one person.
- An LLM-first design with no deterministic core repeats directive 012's failure.

## Phase 0 — Kernel (build first; every department depends on it)
There is no department UI in this phase, just the minimal shell (item 10).

| Part | What it is | Done when |
|---|---|---|
| Identity & roles | Users, workspaces, roles (Founder, Staff, Contractor, Advisor), MFA, audit of every login | RBAC tests pass. A user can't read another workspace's data (test enforced). |
| Core records | `Person`, `Organization`, `Document`, `Task`, `Decision`, `Note`, all linked by one polymorphic `links` table | CRUD API plus Alembic migration and tests |
| Event bus + audit log | Every create, update or approval emits an event and an append-only audit row (who, what, when, before/after) | Audit row verified in a test for each write path |
| Agent runtime | Agent = (directive file, allowed tools list, model tier, spend cap). Every run is logged as inputs, tool calls, output, tokens, cost and latency. | One echo agent runs end-to-end, and its run appears in the log |
| Approval inbox | Every agent proposal lands here: approve / edit / reject + reason. Nothing outward-facing bypasses it. | An outward-facing tool call without an approval ID is refused (test) |
| Company memory | Upload or ingest documents, chunk them, index them with Postgres full-text search (pgvector later, behind the same `Retriever` interface), then retrieve with citations. Answers without a citation are labelled "no source". | Retrieval eval: 20 hand-written Q/A pairs from your real docs, ≥ 16 cited correctly |
| Learning loop | The feedback log and eval runner (`execution/run_evals.py`). Retrieval quality is gated in CI on every push. It is deterministic and free, so it can run on every change. LLM answer-quality evals cost money per run, so they are run on demand with the founder's approval, never automatically. | CI fails when retrieval quality drops below the recorded baseline. A test proves this by deliberately breaking the retriever. |
| Channels | WhatsApp (Twilio) and email out, the in-app notification feed, and WhatsApp in for founder commands | You can WhatsApp "status" and get a real answer |
| Ops basics | Nightly backup plus one restore drill, error alerting, spend dashboard | Restore drill written up in `RUNBOOK.md` |

**Eval sets are only as good as your time.** [Certain] I can't invent the 20 Q/A pairs. They must come from your real documents.

---

## Department build order and why
The order is chosen for a solo founder with one live client: first **your own time**, then **revenue**, then **delivery**, then **protection**.

1. Founder Command Center → 2. Customers & Sales → 3. Delivery (projects) → 4. Support & Incidents → 5. Finance → 6. Legal & Compliance → 7. Marketing & Content → 8. Product & Roadmap → 9. People & HR (only when you hire) → 10. Productize the OS for outside customers.

Each department gets its own directive file (`directives/1xx_<dept>.md`) using this template: **purpose · records · agents (autonomous vs. approval-required actions) · integrations · reports · done gate · known edge cases**. The details below are that directive's first draft.

### 1. Founder Command Center
- **Purpose:** one screen and one WhatsApp thread that tell you what matters today.
- **Records:** Task, Decision (what, why, alternatives, revisit date), Goal/OKR, Meeting note.
- **Agents:**
  - *Chief of Staff*: builds the daily 07:00 EAT brief from events, tasks and calendar. It is read-only.
  - *Decision Recorder*: turns a voice note or chat message into a Decision draft that you approve.
- **Integrations:** Google Calendar through the app's own Google OAuth client (the Claude session's Calendar connector cannot be used by deployed software), and WhatsApp.
- **Done gate:** you use the brief for 10 consecutive working days, and each brief item links to its source record.

### 2. Customers & Sales (CRM)
- **Records:** Organization, Contact, Deal (stage, value in KES, next step, owner), Activity, Proposal.
- **Agents:**
  - *Lead Researcher*: public info to a draft company profile. Labelled unverified until you confirm it.
  - *Follow-up Drafter*: drafts only, and sends only after approval.
  - *Pipeline Reviewer*: weekly list of stale deals.
- **Seed data:** Vibanda plus every prospect you have now. Imported by a script, not typed in.
- **Done gate:** every live conversation is in the CRM, and no deal goes past 14 days without a next step.

### 3. Delivery / Projects (this is what a custom-software studio sells)
- **Records:** Project, Scope/SOW, Milestone, Requirement, Change request, Time entry, linked GitHub repo.
- **Agents:**
  - *Scoper*: client notes to a draft SOW with explicit assumptions and exclusions.
  - *Status Reporter*: weekly client update drafted from GitHub commits and milestones.
- **First real use:** model the restaurant-agent/Vibanda engagement here.
- **Done gate:** the Vibanda project status is produced from the OS, not written by hand.

### 4. Support & Incidents
- **Records:** Ticket, Incident, SLA, and a link to Project/Organization.
- **Agents:**
  - *Triage*: classifies, finds similar past tickets, drafts a reply.
  - *Incident Scribe*: builds the timeline from alerts and writes the postmortem draft.
- **Integrations:** inbound WhatsApp/email, and restaurant-agent's existing alerting.
- **Done gate:** every client issue in a 30-day window is a ticket, and SLA breaches are alerted.

### 5. Finance
- **Records:** Invoice, Payment, Expense, Subscription (tools you pay for), Budget, Cash position.
- **Agents:**
  - *Bookkeeper*: categorizes expenses. You confirm every categorization.
  - *Collections Drafter*: overdue-invoice reminders, approval required.
  - *Runway Reporter*: monthly.
- **Kenya-specific points to confirm with your accountant before building** [Likely, verify]:
  - KRA eTIMS e-invoicing requirements
  - VAT registration threshold
  - M-Pesa (Daraja) payment reconciliation, which the restaurant product already touches
- **Hard rule:** the OS never moves money. It drafts and reconciles only.
- **Done gate:** one full month is closed in the OS and matches your bank/M-Pesa statements to the shilling.

### 6. Legal & Compliance
- **Records:** Contract (party, type, term, renewal/notice dates, obligations), Template, Policy, Data-processing register, Compliance task.
- **Agents:**
  - *Contract Reader*: extracts dates and obligations with a citation to the clause.
  - *Template Filler*: fills lawyer-approved templates only.
  - *Obligations Calendar*: reminders for renewals, notice periods and filings.
- **Kenya-specific points to confirm with a lawyer** [Likely, verify]:
  - Data Protection Act 2019 duties, including ODPC registration as controller/processor
  - DPA terms with restaurant clients
- **Hard rule:** agents never produce "legal advice" or a novel contract. A lawyer reviews every template once.
- **Done gate:** every signed contract is in, and every date is extracted and verified by you.

### 7. Marketing & Content
- **Records:** Campaign, Content piece, Channel, Case study.
- **Agents:** *Case-study Drafter* (from Delivery records and client-approved facts only), *Content Calendar*.
- **Done gate:** one published case study (Vibanda, with their written consent).

### 8. Product & Roadmap
- **Records:** Feature request (linked to Tickets and Deals), Roadmap item, Release note.
- **Agent:** *Signal Aggregator*, which ranks requests by linked revenue and ticket count. The ranking is deterministic; the LLM only summarizes.
- **Done gate:** the next restaurant-agent release is planned from OS data.

### 9. People & HR (deferred until your first hire or contractor)
- **Records:** Person, Contract, Onboarding checklist, Access grants.
- **Agent:** *Onboarding/Offboarding Checklist*. Offboarding revokes access through the Kernel.

### 10. Productize
Start this only after departments 1–6 have run your own company for 60 or more days. This phase covers packaging workspaces for other businesses: billing, onboarding, and per-tenant connectors. The multi-tenant Kernel from Phase 0 is what makes it possible.

---

## Pace (solo founder + Claude)
- **Weekly slice:** one shippable PR per week. Each PR has a migration, tests, a directive update, and a working screen or WhatsApp command.
- **Time estimates** [Guessing]: Kernel 4–6 weeks, then roughly 2–4 weeks per department. Real pace depends on your hours and on client work, which always wins.
- **Protect Vibanda:** restaurant-agent keeps priority. Work on the OS stops whenever a client-facing issue is open.

## What I need from you (no code can supply these)
1. Create the `company-os` GitHub repo, or approve me creating it, and add it to the session.
2. Choose Neon or Railway for Postgres, and an LLM provider key: Groq today, with Anthropic as the upgrade path already designed into `llm_client.py`.
3. Provide 10–20 real company documents for the memory eval set.
4. Confirm the Kenya tax and legal items with an accountant and a lawyer before building Finance and Legal.

## Verification (applies to every phase)
- The backend `pytest` suite and the frontend `tsc --noEmit` and `next build` pass in CI. Bandit and gitleaks are clean.
- `execution/run_evals.py` passes. Any eval regression blocks the merge.
- Tenant-isolation and approval-bypass tests exist and pass.
- An end-to-end demo is recorded against real (not seeded) records before a department's done gate is ticked in its directive.
- `graphify update .` is run after code changes, per CLAUDE.md.

## Immediately after approval
Start Phase 0 only. Scaffold the repo, copy the patterns listed above, and implement Identity plus Core records plus Audit as the first PR. Nothing from departments 1–10 is built until Phase 0's done gates pass.
