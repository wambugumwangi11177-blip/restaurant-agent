# Directive 110 — Productize (selling the OS to other businesses)

Directive 000 says to start this phase only after departments 1–6 have run your own company for 60 or more days. The **mechanics are built**; turning them on is your decision.

**Built:**
- **Per-workspace plan:** `plan`, `seat_limit`, `monthly_agent_run_limit`, and `enabled_departments` (null means all). These are enforced:
  - adding a member past the seat limit returns 402
  - an agent run past the monthly limit returns 402
  - a disabled department's records, reports, jobs and navigation disappear (404)
- **Platform admins:** emails in `PLATFORM_ADMIN_EMAILS`, **with two-factor enabled**. They create workspaces and set plans at `/api/v1/platform/workspaces`. A workspace's own founder can see usage but cannot raise its limits.
- **Self-serve signup:** `POST /api/v1/signup`, **off** unless `ALLOW_SIGNUP=true`.
  - Signups get the "trial" plan, with `SIGNUP_SEAT_LIMIT`, `SIGNUP_MONTHLY_AGENT_RUN_LIMIT` and `SIGNUP_DEPARTMENTS`.
  - Limited to 5 signups per IP per hour (in memory, per process).
  - It refuses emails that already have an account, so nobody can attach a workspace to someone else's account.
- **Usage:** `GET /api/v1/workspace/usage` (seats, runs this month, LLM spend), also shown in Settings.

**NOT built, and why:** **billing.** Charging customers needs two decisions only you can make:
- the payment provider: for example M-Pesa (Daraja) for Kenyan SMEs, or a card processor
- the prices

Until then, plans are set manually by a platform admin, and limits are enforced regardless.

**Also needed before opening signup:**
- terms of service and a privacy notice from your lawyer
- a data-processing agreement for customer workspaces (you become their processor)
- a per-IP rate limiter that is shared across processes, if you run more than one web process
