# Directive 001 — Kernel (Phase 0)

The SOP for the Company OS foundation: what exists, how to run and operate it, and the live status of Phase 0's done gates. Update this file whenever something is learned (CLAUDE.md, "self-anneal").

## Purpose
The Kernel is the part every department depends on:
- identity and roles
- workspace isolation
- core records and links
- events and an append-only audit trail
- company memory with citations
- the agent runtime and its approval gate
- feedback and evals
- WhatsApp and email channels
- data-subject rights

Departments are built on top of it, one at a time (directive 000). None of them start until the gates below that need the founder are closed.

## What exists (map)
| Concern | Code |
|---|---|
| Config and production guard | `backend/app/config.py` |
| Tables (one migration: `alembic/versions/0001_kernel.py`) | `backend/app/kernel/models.py` |
| Login, MFA, sessions, members | `backend/app/security.py`, `backend/app/api/auth.py` |
| Workspace isolation | `backend/app/kernel/tenancy.py` |
| Permissions (roles: founder, staff, contractor, advisor) | `backend/app/kernel/rbac.py` |
| Records and links, with audit and events on every write | `backend/app/kernel/records.py` |
| Audit (append-only, PII-free) | `backend/app/kernel/audit.py` |
| Events | `backend/app/kernel/events.py` |
| Company memory | `backend/app/kernel/memory/` |
| Tools and the approval gate | `backend/app/kernel/agents/tools.py`, `backend/app/kernel/approvals.py` |
| Agent runtime, LLM providers, spend cap | `backend/app/kernel/agents/runtime.py`, `llm.py`, `spend.py` |
| Built-in agents (`echo`, `status`, `memory_qa`) | `backend/app/kernel/agents/builtin_agents.py`; SOPs in `directives/agents/` |
| WhatsApp and email | `backend/app/kernel/channels/`, `backend/app/api/webhooks.py` |
| Export and erasure | `backend/app/kernel/privacy.py` |
| Web shell | `frontend/` |

## Run it locally
1. Start Postgres 16. Create a database and role that match `DATABASE_URL`. The default is `postgresql+psycopg2://cos:cos@localhost:5432/cos_dev`.
2. Set up the backend:
   `cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt`
3. Create the tables: `alembic upgrade head`.
4. Create your workspace and founder account. There is no public sign-up.
   `python ../execution/bootstrap_workspace.py --slug <company> --name "<Company>" --email <you> --full-name "<You>" --phone 07XXXXXXXX`
   It prompts for a password: at least 12 characters, with upper case, lower case and a digit.
5. Start the API: `uvicorn app.main:app --reload`. The API docs are at http://localhost:8000/docs (off in production).
6. Start the web shell: `cd frontend && npm install && npm run dev`, then open http://localhost:3000. The `BACKEND_URL` default is http://localhost:8000.

`dev.sh` at the company-os root does steps 3, 5 and 6 in one go.

## Operate it
- **Add company documents to memory.** Use the Memory page (paste text or upload `.md`/`.txt`), or
  `python ../execution/ingest_documents.py --workspace <slug> <folder-or-files>`.
  PDF and DOCX extraction is not built yet; convert those to text first.
- **Ask questions.** Use the Agents page and run `memory_qa`, or WhatsApp `ask <question>`.
  - Without an LLM key it returns the best-matching passages instead of an answer.
  - With a key, it answers with a numbered citation for each claim.
- **Approvals.** Anything that leaves the company (email, WhatsApp to non-members) waits in the Approvals page. Approve, edit and approve, or reject with a reason. A rejection without a reason is refused, because the reason is what the system learns from.
- **Autonomy.** Approvals → Policies. Turn on auto-approval for a tool only after its streak of human approvals with no edits reaches the threshold (default 20). Any edit or rejection resets the streak.
- **Data-subject requests.** Export or erase a person with `GET /api/v1/privacy/people/{id}/export` and `POST .../erase`, founder only. Whether a request must be honoured is a legal call; the OS only executes it.
- **Spend.** `GET /api/v1/ops/status` shows today's LLM spend against `DAILY_LLM_SPEND_CAP_USD`.

## Evals (the learning loop)
- **Retrieval** (deterministic, free) runs in CI on every push.
  - Cases: `evals/retrieval/kernel_docs.jsonl`.
  - Floor: `evals/retrieval/baseline.json`.
  - Runner: `execution/run_evals.py`.
  - Test: `backend/tests/test_evals.py`, which also proves the gate fails when retrieval is deliberately broken.
- **Your company's own eval set** covers your real documents and questions.
  - Put 20 or more lines in `evals/retrieval/company_docs.jsonl`, using the same format as the kernel file.
  - Run `python execution/run_evals.py --workspace <slug> --cases evals/retrieval/company_docs.jsonl` against your live memory.
  - Phase 0's memory gate needs at least 16 of 20 correct.
- **Turning feedback into eval cases.** `python execution/export_feedback_evals.py --workspace <slug>` writes every rejection, edit and "unhelpful" run to `.tmp/feedback_cases.jsonl`, for review and promotion into the eval set.
- LLM answer-quality evals cost money per run. Run them on demand only, with the founder's approval (CLAUDE.md: paid tokens need a check first).

## WhatsApp setup (needs the founder's Twilio account)
1. In Twilio, turn on the WhatsApp Sandbox or an approved sender.
2. Set the environment variables:
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
   - `TWILIO_WHATSAPP_FROM=whatsapp:+<sender>`
   - `PUBLIC_BASE_URL=https://<your-api-host>`, exactly as Twilio calls it, because the signature check uses it.
3. Set the sandbox or sender's "When a message comes in" webhook to `POST https://<your-api-host>/api/v1/webhooks/whatsapp`.
4. Put your phone number on your member profile (bootstrap `--phone`, or `PATCH /api/v1/members/{id}`).
5. WhatsApp `status` and you should get the summary back.

Unknown numbers are recorded and get no reply. Retried deliveries are ignored.

## Deploy (needs the founder's accounts; not done by the build)
- **Backend and Postgres on Railway**, matching restaurant-agent. There is a Dockerfile in `backend/`.
  - Set `ENV=production`, `DATABASE_URL`, `JWT_SECRET` (32+ random characters), `PUBLIC_BASE_URL`, `CORS_ORIGINS`, plus the LLM, Twilio and SMTP keys.
  - The app refuses to boot in production with a default secret, a localhost database or a non-https base URL.
  - Run `alembic upgrade head` as the release command.
- **Frontend on Vercel**: root directory `company-os/frontend`, with the env `BACKEND_URL=https://<api-host>`.
- **Database role (hardening)**: run the app as a role that does not own the tables. That blocks `TRUNCATE` on the audit log as well as the `UPDATE`/`DELETE` the trigger already blocks.

## Backups and restore drill
- `execution/backup_db.sh` writes a `pg_dump -Fc` file to `.tmp/backups/`.
- `execution/restore_drill.sh <dump>` restores it into a scratch database and compares per-table row counts with the source.
- A drill against the local dev database is recorded in `RUNBOOK.md`. Production backups and a production drill need the founder's Railway access; the steps are in `RUNBOOK.md`.

## Phase 0 done gates — status
| Gate | Status |
|---|---|
| RBAC tests pass; no cross-workspace reads | ✅ `tests/test_tenancy_rbac.py`, `test_auth.py` |
| Core records: CRUD, migration, tests | ✅ `tests/test_records_audit.py`; migration round-trips up and down |
| An audit row for each write path | ✅ records, links, members, auth, proposals, documents, privacy (tests) |
| Echo agent end-to-end, visible in the run log | ✅ `tests/test_agents.py::test_echo_run_is_recorded` |
| External call without approval refused | ✅ `tests/test_approvals.py` (forged, tampered, cross-workspace, replay) |
| Retrieval eval, kernel corpus | ✅ gated in CI (see `baseline.json` for the measured score) |
| Retrieval eval on **your** documents (20 Q/A, ≥16) | ⏳ **Needs the founder:** real documents and questions |
| CI fails when retrieval quality drops | ✅ `tests/test_evals.py::test_gate_fails_when_retrieval_breaks` |
| WhatsApp `status` returns a real answer | ✅ in tests with signed requests. ⏳ **Needs the founder:** a live check with a Twilio account |
| Nightly backup and a restore drill | ✅ scripts, plus a local drill in RUNBOOK.md. ⏳ **Needs the founder:** production schedule and drill |
| Spend dashboard | ✅ `/api/v1/ops/status` and the Home page |
| Error alerting | ⚠️ Partial. A failed approved action notifies founders; logs are JSON with request ids. ⏳ **Needs the founder:** an uptime and exception monitor on `/health` (Railway healthcheck plus any uptime service) |
| Web shell | ✅ Approvals, Records, Memory, Agents, Audit, Settings. Verified with a headless-browser end-to-end run (desktop and 375 px mobile, no horizontal overflow) |
| Deployed | ⏳ **Needs the founder's** Railway and Vercel accounts |

## Known limitations (deliberate, Phase 0)
- Memory is full-text only: synonyms and paraphrases can miss (ADR 0003).
- Only `.md` and `.txt` upload is supported.
- No per-IP rate limit on login; per-account lockout is in place. Add rate limiting before exposing the API publicly beyond the founder's team.
- The WhatsApp `ask` command answers in the background when an LLM is configured. If Twilio sending isn't configured, the answer is recorded on the run but not delivered.
- Event subscribers run in-process, in the same transaction. Fine at this scale; move to a queue only when measured load requires it.

## Learnings log
- 2026-09-26: The GitHub integration can't create repositories (403), so this is built inside restaurant-agent (ADR 0007).
- 2026-09-26: `email-validator` rejects reserved TLDs such as `.test`, so test fixtures use `example.com`.
- 2026-09-26: Twilio's docs site is blocked from the build sandbox. The WhatsApp signature code was verified against the official `twilio-python` `RequestValidator` instead. A signature "example" recalled from memory was wrong, which shows why anything security-related gets checked against a primary source.
- 2026-09-26: A browser end-to-end run (Playwright, headless Chromium) found three web-shell bugs that the unit tests could not see. All are fixed.
  1. Overlapping list requests could land out of order and overwrite newer results (Approvals filter, Records search). Lists now drop superseded responses.
  2. After approving, the outcome wasn't shown. There is now a result banner that says executed or failed, with the error.
  3. Pages showed "nothing here" before their data had loaded; Home even contradicted its own status count. Every list now shows "Loading…" until its data arrives.

  Rule for future pages: `null` means not loaded yet, `[]` means actually empty.
- 2026-09-26: `pkill -f <pattern>` / `pgrep -f` also match the shell running the command whenever the pattern appears in that command line. Stop dev servers by process name (`next-server`) or by PID.
