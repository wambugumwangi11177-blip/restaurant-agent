# Vibanda production review — 20 September 2026

## Verdict

**Not ready for an unconditional owner handover.** The application has a substantial tested foundation, but a successful deployment and HTTP 200 responses do not establish that the owner receives correct advice or that an approval does the requested work. This review found reproducible defects beyond the two reported interface symptoms.

The review covers deployed `master` commit `82754b575f3e1135cb16982fa754eb5cbc2e2416`, its latest changes, owner-facing data paths, existing tests, and a separate inspection of candidate branch `claude/agent-different-work-ppl204` at `179ecc2`. It is not a penetration-test certification, a line-by-line verification of every module, or a claim that no other bugs exist.

## Deployment evidence

- Railway `restaurant-agent-backend/backend-api` is running `82754b5`. Recent logs contain successful overview, reports, authentication and AI-chat requests. Those logs do not establish which tenant made each request or whether the rendered answers were correct.
- Railway source configuration has `checkSuites: false`: a failed CI run does not prevent that deployment. The latest master CI run `35445763465` failed its Bandit job; pytest, frontend, dependency audit and secret scanning succeeded. Container scanning is configured non-blocking, so the job's success is not proof of a clean image.
- Bandit's failure was SHA-1 used for a non-security attention-card identifier. The fix explicitly marks that use non-security, preserving stable existing card keys. This was a release-gate failure, not evidence of a password-hashing vulnerability.
- Other Railway services still publish failed deployment statuses against the same commit. Identify and retire obsolete deployment hooks deliberately; do not confuse them with the working backend.
- Vercel project discovery worked, but deployment inspection returned an authorization error for `mbuguss-projects`. The old documented frontend URL returned 404 at `/vibanda`. The user identified a different Nova `.app` frontend; its exact URL and authenticated browser verification are still required. No live Home redirect was reproduced.

## Reproduced defects and isolated fixes

| Finding | Evidence and owner impact | Change prepared |
|---|---|---|
| Chat forces page movement | `frontend/src/app/vibanda/os/page.tsx` calls `scrollIntoView` whenever a question is added | Removed forced scrolling; component test checks question submission and answer completion |
| Chat waits for unrelated advice | Every question calls `/ai/chat`, then `/ai/strategy`; the latter uses a general strategy pipeline | Removed the second call; answer and next steps now come from the question-specific response |
| Failed chat can give reassuring fallback advice | Browser-side overview fallback claims healthy stock or no urgent issues without the requested analysis | Replaced with an explicit failure message; bounded request timeout; follow-up history now includes previous answers |
| Home converts unavailable metrics into positive claims | Backend sends `unavailable_metrics`, but UI renders kitchen “On pace”, “No delays reported”, and “No waitlist” | Home respects those unavailable fields, fixes period labels and stops describing a low-stock threshold as a stockout forecast |
| Revenue card contradicts itself | A zero pace forecast displays “No sales” even when recorded revenue exists | Distinguishes missing forecast from no recorded paid sales |
| Menu answers fail with real classifications | Adapter applies `len()` to numeric `summary.stars`; new real-data regression raises `TypeError` on the baseline | Reads named rows from `matrix`, checks recorded sales before classifying the answer |
| Profit answers hide real opportunities | Adapter reads `leaks` instead of `profit_leaks`; real seeded data returns “No significant profit leaks” despite a leak | Uses actual output fields and labels monetary opportunity as modelled, not guaranteed recovery |
| Labor answers lose data | Adapter reads nonexistent top-level cost percentage instead of `summary.labor_pct` | Uses the nested summary, preserves zero and checks usable input data |
| Kitchen answers falsely report success | Adapter reads `stations` instead of `station_performance`; no measurements produce “on pace” | Uses the real contract and reports missing measurements as unavailable |
| Macsoft retries are not idempotent | Four identical deliveries produce insert/skip/insert/skip; an old applied version replay supersedes the new marker | Applied-version lookup ignores skip events; previously applied versions stay skipped without changing current version |
| Decision-save errors disappear | Rejected POST leaves an unhandled rejection, with no clear feedback | Keeps card visible, disables pending buttons and shows a save error; clarifies that recording a decision does not execute it |

All six new backend defect tests failed on the original behavior: four owner-answer tests and two ingestion-retry tests. These are behavior regressions, not just assertions that routes return 200.

## Remaining release blockers

1. **Attention actions are not a completed operational workflow.** `routers/overview.py::decide` inserts `AttentionDecision`; it does not approve a purchase order, apply a price or queue a source-system change. Decide whether each card is advisory acknowledgement or an executable action. Use an explicit entity/action identifier, role check, idempotency key, audit record and visible outcome for executable actions. Preserve the agreed read-only Macsoft boundary.
2. **“Later” suppresses cards indefinitely, and suppression is tenant-wide.** `_attention_cards` filters all previously decided keys without time bounds. The key hashes agent/action text, not restaurant identity; `AttentionDecision` has no restaurant field. Same-text cards in sibling restaurants can affect one another. Add restaurant-scoped decision storage and an explicit snooze expiry, with migrations and repeat-request tests. Do not blindly migrate ambiguous old records to every branch.
3. **Home does not cover every relevant capability.** The six decision adapters are pricing, inventory, supply chain, menu, labor and marketing. Kitchen, profit leaks, fraud/cash reconciliation, reservation issues, and ingestion freshness do not have equivalent direct adapters. Adapter exceptions are logged then omitted; an empty feed can conceal a failed analysis. Return per-domain states: available, insufficient data, stale, failed, disabled, or not applicable.
4. **Chat adapters still contain contract and question-specificity gaps.** Bookings reads fields inconsistent with `reservation_optimizer` (`no_show_analysis`/`revenue_impact`), while pricing reads `item`/`name` instead of `item_name`. Module routing alone does not answer “who is booked tonight?” or “who worked most shifts this week?” Add real-output tests for every built-in question family, dates, rankings and named entities.
5. **Paid AI routes have inconsistent guardrails.** On deployed master, `/ai/chat` and narrated reports bypass the spend-cap/metering path used elsewhere; chat imports but does not apply a rate limiter. Free text/history goes to the provider without the existing PII scrubber. Record-controlled text enters the system prompt. Numeric grounding checks cannot establish semantic truth or stop all prompt injection. Apply consistent per-tenant limits, usage accounting, input/output constraints and minimal provider context.
6. **Data readiness cannot be inferred from zeros.** `PartHealth` still treats an empty low-stock list as “Healthy”, menu health as order count, and purchasing as a dash. Hardcoded prototype badges are not a data-provenance contract. Return source, freshness, coverage and integration status from the backend and show them consistently across Home, chat and reports.
7. **Macsoft receipt is not a complete data-to-owner tracer.** The webhook records `MirrorEvent` entries; Home reads domain tables such as `Order` and `InventoryItem`. Projection/mapping and reconciliation remain unproved. The mirror has a shared source slug and no explicit tenant/restaurant binding. Concurrent retries, same-version/different-payload conflicts and ordering of previously unseen old versions still need a source contract and PostgreSQL-backed guarantees. These can be designed/tested with synthetic contracts now; actual field mapping needs Macsoft's sample.
8. **Release and recovery evidence is incomplete.** Existing tests primarily use SQLite. PostgreSQL migration compatibility, concurrent updates, backup restore, browser login/navigation/scrolling on the actual frontend, deployment version alignment, and observed operational alerts remain handover gates. A scheduled backup job is not a demonstrated restore.

## Candidate branch: separate, not deployed

The newly pushed branch adds rate/spend checks, prompt delimiters, partial PII scrubbing, CI coverage gating, daily reporting facts and backfill tooling. These are relevant improvements, not yet protections in production.

Two specific review concerns remain:

- Adding `check_spend_cap()` does not meter these routes: they still call `llm_client.chat()` without recording `TokenUsage`. Usage from those calls can escape the cap's accounting. The new chat path scrubs card data, but question/history are still passed through. Test actual accumulated spend and captured outbound provider inputs, not only that a check function was called.
- Reporting fact reads test row coverage, not freshness. The branch's own cancellation test demonstrates that `verify()` detects a stale KSh 50 fact, but read paths do not call that verifier or invalidate affected days. Nightly refresh covers seven days; older corrections and changes between refreshes can yield stale owner figures. Use mutation-driven invalidation or a clearly enforced freshness/reconciliation policy before enabling this cache for financial reporting.

Do not merge the candidate branch solely because its included tests pass. Reconcile its overlapping changes with this patch explicitly.

## Home coverage map

| Area | Current owner surface | Required proof |
|---|---|---|
| Revenue/orders | Snapshot, pulse, seven-day trend | Same paid/cancelled/date/currency basis across Home, chat and reports |
| Pricing/menu | Ranked recommendations | Real-item adapter tests, missing-cost handling, honest evidence strength, review-to-action outcome |
| Stock/purchasing | Low-stock alerts and ranked suggestions | Quantities/units, received data freshness, scoped approval or explicit source-system handoff |
| Kitchen | Placeholder overview metrics and chat analysis | Recorded prep evidence; unknown must remain unknown |
| Staff | Schedule/cost snapshot and labor recommendations | Correct time window, roles and actual attendance coverage |
| Reservations/customers | Covers and marketing adapter | Booking status filtering, question-specific answers, consent and no-send-without-approval |
| Profit/cash/fraud | Backend capabilities, incomplete Home coverage | Seeded anomaly must become an owner-visible finding with traceable evidence |
| Integration/AI/reliability | Mostly logs/configuration | Stale feed, failed adapter, provider outage and budget exhaustion visible to owner/operator |

## Verification completed

- Original master baseline: **760 passed, 1 failed**. Push-dispatch test depended on real external DNS despite mocking delivery. Its DNS is now deterministic while retaining the real public-IP guard; production security was not weakened.
- Full backend suite after owner-answer fixes: **765 passed**. The later ingestion correction was separately verified against **41 ingestion/mirror/reconciliation tests**, including the two new retry cases.
- Frontend: **5 component interaction tests passed**, TypeScript checks passed, production build passed. Tests cover explicit Home navigation, unavailable kitchen state, failed decision persistence, no forced chat scrolling, one question-specific request, failure messaging and follow-up context. These do not replace a real mobile/browser test.
- Bandit: **0 medium/high findings** after marking the non-security hash correctly; low findings were not certified clean.
- npm audit after adding test dependencies: **0 reported vulnerabilities** at the time checked.
- Candidate branch: **17 targeted hardening/reporting tests passed**. Its PostgreSQL migration/backfill and production performance are not verified here.

## Practical tracer-bullet release sequence

1. **Login → Home:** actual Nova deployment, authenticated Vibanda owner, Home remains Home, correct tenant, reload/back/phone widths, no console errors.
2. **Known data → owner answer:** a small synthetic restaurant with hand-calculated totals, known low stock, one margin issue and missing kitchen measurements. Assert the exact Home/report/chat meaning, units and date boundaries.
3. **Question → visible answer:** suggested/custom/follow-up questions, no forced page jump, bounded wait, provider error and offline states, question-specific next action.
4. **Finding → recorded decision → outcome:** role denial, repeated click/retry, another restaurant, snooze expiry, audit trail and truthful distinction between acknowledgement and execution.
5. **Macsoft replay → projection → reconciliation → Home:** duplicate batch, correction, delayed/out-of-order delivery, malformed payload, crash/retry, count/value reconciliation and stale-feed warning. Run in an isolated database before the first live sample.
6. **Failure → recovery:** provider down, DB restart, bad release rollback and backup restore into a separate PostgreSQL instance. Verify restored totals and owner login.

Use risk-based gates, not a target number of tests. Financial totals, authorization, idempotency and destructive actions need exact assertions and adversarial cases. Layout changes need browser interaction checks at the owner's device sizes. Preserve a fixed evaluation set whenever prompts/models change. No benchmark or second AI review substitutes for these independent checks.

Security review references: [OWASP prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) and [OWASP excessive agency](https://genai.owasp.org/llmrisk/llm06-sensitive-information-disclosure/). Their practical implication here is to treat restaurant records and questions as untrusted input, limit model access, and enforce authorization outside the model.

No exact `A10` identifier was found in the searched code/docs. AIOps, deterministic analytics, orchestration, evaluation and feature flags do exist. Clarify which A10 artifact was intended before claiming that specific component was reviewed.
