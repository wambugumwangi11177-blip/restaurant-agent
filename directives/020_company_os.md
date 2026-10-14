# 020 — Company OS Kernel

Goal: agents run the routine work of the company; humans keep every decision that
moves money, makes a promise, contacts a new party or deletes data. Source: the
founder-independence report (Stage 1). Code: `backend/ai/company_os/`,
`backend/routers/company_os.py`, tables `company_proposals`, `company_tool_autonomy`.

## Rules
- Agents act ONLY through `kernel.propose(...)`. No agent calls a tool directly.
- Tiers: READ and INTERNAL run immediately (INTERNAL is always recorded); EXTERNAL
  waits as a Proposal until the tool earns autonomy; RESTRICTED always waits.
- Autonomy is earned per tool: 20 consecutive approvals with no edit. An edit, a
  rejection or a failure resets the streak and demotes the tool.
- Kill switch: `FEATURE_COMPANY_OS_AUTONOMY=false` => everything with a side effect
  waits (draft-only). `FEATURE_COMPANY_OS` (default off) enables the daily cycle.
- Drafts are templated from recorded facts. Any future LLM-drafted text must treat
  customer messages as untrusted data and still go through `propose`.

## Operating
- Daily cycle 05:30 UTC (`main._run_company_os_cycle`); manual: `POST /company-os/run`.
- Review queue: `GET /company-os/proposals?status=pending`; approve (optionally with
  `edited_payload`) or reject; `GET /company-os/status` shows streaks/autonomy.
- All endpoints are SUPERADMIN only.

## Adding an agent tool
1. `@kernel.register("name", tier)` in `tools.py`. Default to EXTERNAL when a
   customer sees the result; RESTRICTED for money, deletion, new contacts, policy.
2. Have an agent in `agents.py` call `kernel.propose`. Add a test.
3. Never register a tool that moves money as anything below RESTRICTED.

## Learnings / open items
- Tools today: `scorecard_digest` (INTERNAL), `client_checkin` (EXTERNAL, in-app).
- Not built: outbound WhatsApp/email check-ins, billing reminders, a UI for the
  approval queue (API only), LLM-drafted messages.
