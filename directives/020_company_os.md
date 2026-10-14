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

## Departments (`ai/company_os/departments/`)
Run daily in this order; a failing department is isolated and reported in the cycle result.
| Department | Agents | What it does | Gated actions (need approval until earned) |
|---|---|---|---|
| support | ack_agent, escalation_agent | Acknowledge tickets unanswered 24h; alert operator at 72h | `ticket_reply` |
| finance | collections_agent, unit_economics_agent | Remind overdue subscriptions weekly; monthly LLM cost per client | `billing_reminder` |
| customer_success | onboarding_agent, health_agent | Activation nudge (20 orders in 14 days); check-in for red-health restaurants | `activation_nudge`, `client_checkin` |
| engineering | model_watch_agent, reliability_agent | Warn 60 days before a configured model retires; alert on 5xx rate over 5% | none (alerts only) |
| compliance | calendar_agent | Quarterly restore drill, monthly model/ledger checks, July Finance Act, PAYE (`COMPANY_HAS_EMPLOYEES`), your own dates (`COMPANY_ANNUAL_DEADLINES='06-30:key:text;...'`) | none (alerts only) |
| executive | chief_of_staff | One daily brief: restaurant health, items awaiting you, by department | none |

`GET /company-os/departments` returns founder load (pending/failed by department): the number
that should fall over time.

## Learnings / open items
- Everything customer-facing is in-app only. No WhatsApp/email outbound, no UI for the queue.
- Sales and marketing have no department: there is no lead/pipeline data in this repo.
- Engineering cannot deploy, roll back or restore; those stay human (RESTRICTED by policy).
- Finance cannot collect money: no payment processor is wired (subscriptions are "manual").
