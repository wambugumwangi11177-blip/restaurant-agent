# LEVIII / Eleven completion plan

Prepared 24 October 2026. Execution authorized by the user in this chat. No production deployment or production-data changes have been performed. Baseline: dev/eleven-demo-fixes at 654d116; readiness at 09cd227; PR #25 open. Recheck remote heads before implementation.

## Objective and evidence
Finish the existing demo, complete the deferred staff/product workflows, onboard Eleven with verified real inputs, and operate a reliable release. Completion means working end-to-end flows with evidence, not just implemented screens.

Sources on dev/eleven-demo-fixes: docs/v2/{PROGRESS,ELEVEN_DEMO_PLAN,ELEVEN_ACCEPTANCE,ELEVEN_ONBOARDING,P7}.md and PR #25. Latest progress takes precedence over older design notes where delivered behavior is evidenced. Historical dates in the onboarding plan are not proof those visits or provisioning occurred.

Already implemented, requiring final acceptance rather than rebuilding: owner Home/Ask/reports; finance and exports; staff expenses/counts/delivery/waste/issues/bills; invoice access; recipe yield and unit conversion; scoped offline entry queue and audited undo; forecast/prep/purchase drafts; scheduled pricing and learning; menu/stock review; branch comparison; charts; AI grounding and asynchronous notes.

Latest progress reports 2254 backend and 248 frontend local passes, typecheck and build passing. Latest GitHub run passes pytest, PostgreSQL release checks, container scan and SAST; frontend dependency audit, Python dependency audit and Gitleaks fail. A final browser pass is not recorded. This plan does not independently certify those local test results.

## Phase 0 — establish one release baseline
Owner: release lead, with both developers.
- Inventory each developer's branch, working tree and unpushed commits. Compare against GitHub before cherry-picking or merging; preserve local work.
- Map master -> v2 foundation -> readiness -> fixes. Compare PR #24 and #25 ancestry and ensure the final release includes all required changes; closing or merging one PR must not omit later commits.
- Create one tracking checklist with requirement, current status, code reference, acceptance evidence and responsible developer.
- Reconcile stale docs, including scheduled-price expiry behavior, enabled AI defaults, offline limitations and superseded P7 statements.
Exit: agreed release SHA, no unexplained local work, documented branch/integration path and current checklist.

## Phase 1 — close quality and demo acceptance gaps
Owner: backend/release developer + frontend developer.
- Inspect the exact failing npm audit, pip-audit and Gitleaks logs; fix dependency findings or document narrowly justified exceptions. Determine whether Gitleaks is a finding or tooling failure; handle any real exposed credential without printing it.
- Run CI on the actual candidate commit; complete frontend build/typecheck/tests that the failed audit previously skipped, lint ratchet, backend/evals and migration checks.
- Browser-test owner, manager, accountant, storekeeper and kitchen at phone and desktop widths, both branches. Capture failures and retest fixes.
- Trace: delivery -> stock -> kitchen issue -> independent confirmation/dispute -> count/waste -> owner evidence; sales -> cash/M-Pesa checks -> expense/bill -> P&L/export; forecast -> prep -> draft order; approval -> scheduled checkout price -> recorded result.
- Verify 06:00 Nairobi rollover, >200-order sales, blank vs zero counts, duplicate submits, cross-branch access, offline reconnect/user switch, undo limits, invoice access and expired quotes.
- Test live AI in a controlled environment and unavailable/slow/invalid-response cases. Deterministic numbers must remain usable. Finish loading/error/empty states where browser findings show gaps.
Exit: required CI green, critical browser journeys pass, no unresolved wrong-money/data-loss/role-isolation defect; accepted limitations listed.

## Phase 2 — finish deferred product workflows
Proposed scope from the repository's deferred list; detailed behavior below is a recommendation, not a previously approved specification. Build in this order.

### 2A. Accountant proposals and owner approval
Allow an accountant to propose supported corrections with reason/evidence; owner approves or rejects. Define eligible records first. Preserve existing read/export/review features.
Acceptance: approval applies once, rejects stale/conflicting proposals, records actor/time/reason and refreshes the affected totals. Staff cannot self-approve beyond their permissions.

### 2B. Activity feed and delegation
Expose relevant existing audit events as an understandable, branch-scoped feed. Add assignment, due date, completion and overdue state for agreed operational tasks. Keep cash/fraud visibility restricted.
Acceptance: task has an owner and visible outcome; unauthorized roles cannot see private events; retries do not duplicate events/tasks. External notifications require separately configured and authorized channels.

### 2C. Shared-tablet PIN access
Agree personal-phone versus shared-device operation. Add individual fast sign-in/switching, attempt limits, lock/timeout and attributable entries without exposing another user's queued work.
Acceptance: switching users preserves isolation; privileged approvals remain protected; loss of connectivity has defined behavior. Reuse existing identity/RBAC rather than inventing a separate permission system.

### 2D. Full spoilage workflow
Extend existing waste entry with agreed reasons, evidence and any required approval/disposition. Distinguish recorded waste from unexplained variance in owner-facing explanations; agree accounting treatment first.
Acceptance: stock and cost impact happen once, audit evidence survives correction, reversals obey stock-movement constraints, reports reconcile.

### 2E. Onboarding wizard
Guided branch setup, users, menu, recipes/yields, units, suppliers, opening stock, bills/licences, targets and source connection. Reuse existing forms/services.
Acceptance: resumable, validates missing requirements, previews imports, avoids duplicates, shows whether data is sample or real, and ends with a verified first workflow.

### 2F. Mobile/desktop packaging
Confirmed scope: Android packages, desktop packages (Windows/macOS/Linux), iPhone/iPad PWA; no iOS App Store. The completion implementation uses Capacitor for Android and sandboxed Electron for desktop, keeping the server-rendered Next application hosted. Verify signing, updates, auth, file/photo access, offline behavior and support ownership.
Acceptance: install/update and core workflows pass on actual target devices. A package is not complete merely because a wrapper builds.

Phase 2 exit: each included feature has tests, browser/device evidence and operator instructions. Do not hold first controlled pilot for packaging if the web app meets its device needs.

## Phase 3 — real data and Eleven onboarding
Data collection can begin during Phase 1; production import waits for a validated release and rollout approval.
Owner: Eleven/Mbuguss supplies inputs; integration developer validates them.
- Confirm POS make/version and access at each branch; choose supported API/export/import path based on an actual sample.
- Validate one real M-Pesa export, rejected-row reporting, duplicate import and matching. Define card settlement scope explicitly: currently no settlement table; keep 'Settlement not recorded' unless a real integration is commissioned.
- Obtain branch names, staff roles, menus/prices, recipes/yields, suppliers, opening counts, bills/licences and accountant categories. Request 60–90 days of historical sales where available, with explicit source coverage.
- Reconcile imported counts and totals to source documents per branch/day/payment type; handle cancellations, refunds and timezone boundaries explicitly.
- Provision Eleven separately from demo data through a controlled process. Train one role at a time at quiet hours; prove a real entry reaches the owner's numbers.
Exit: first real trading day reconciles, every role completes its core task, source gaps are visible, and owner/accountant accept the figures.

## Phase 4 — deployment and operational readiness
Can be prepared alongside Phase 2/3; release after Phase 1 passes.
- Verify actual current hosting/accounts, selected deploy branch, domains, environment variables and database revision. Older Railway notes are historical, not a live status check.
- Rehearse the complete migration chain through the candidate's head on production-compatible PostgreSQL and test the container startup sequence. Readiness introduced 057/058 and fixes introduced 059; do not use the older 051–056-only rollout notes unchanged.
- Take an appropriate backup and prove restore into a separate database. Document code/database-compatible rollback and an operator checklist.
- Verify health checks, error monitoring, backups, task/scheduler behavior, provider budgets and feature flags. Keep WhatsApp and external order sending off unless separately scoped and tested.
- Deploy staging, run smoke/role/data checks, then schedule a controlled production rollout with concrete diff and migration evidence for approval.
Exit: healthy release, successful post-deploy reconciliation, recoverable database, named operator and tested rollback instructions.

## Phase 5 — pilot, learning and handover
- Observe at least one complete business cycle: opening, service, overnight rollover, close, purchases, counts and weekly reporting. Review first month-end when enough real cost data exists.
- Check stock/cash discrepancies against records; distinguish missing inputs, operational issues and software defects. Avoid describing observed price changes as causal savings.
- Verify forecasts/pricing unlock only with adequate history; insufficient data stays visibly 'learning'.
- Fix pilot issues, finalize role guides and support/runbook, record owner/accountant sign-off, and maintain a small prioritized backlog.
Exit: accepted reconciled reports, staff can operate without developer assistance, support/backup responsibilities assigned and no critical unresolved incidents.

## Suggested division for two developers
Developer A: backend/integrations, proposals/workflow states, data isolation, migrations, CI security findings, rollout and reconciliation.
Developer B: browser acceptance, role screens, feed/delegation UI, tablet experience, onboarding wizard, accessibility/device testing and packaging.
Joint checkpoints: API/data contract before each feature; review each other's changes; one shared integration branch; one release owner. Work may run concurrently only where contracts and file ownership are clear.

## Decisions and dependencies
Resolve when needed: whether installed mobile/desktop packages are required for first launch; shared-device usage; proposal approval rights; spoilage accounting/approval; actual POS/source capability; hosting access and domain; guide-versus-product definitions (variance denominator, rounding and evidence limits). No secret values belong in the plan.

## Definition of finished
For every in-scope item: implemented on the agreed branch, reviewed, pushed, tests/CI passing, end-to-end acceptance evidenced, documented and deployed where required. Real-data inputs are reconciled; missing external inputs are explicit blockers rather than claimed completion. A release and Phase 2 feature completion can be separate milestones.

Scheduling: estimate after Phase 0 and inspection of CI findings and real POS sample. The current records cannot support a reliable completion date. Track by these exit gates instead of promising a calendar date before unknown integration work is measured.
