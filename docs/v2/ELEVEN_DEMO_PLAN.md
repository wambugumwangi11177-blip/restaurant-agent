# Eleven demo readiness

Eleven remains unprovisioned. The 23 October request authorizes implementation of the gaps in the presentation, including the staff screens that the original v2 spec deferred. Work stays on local databases; no deployment or production writes.

1. Align owner health tiles with the presentation and distinguish delivery-channel price options from ordinary capped price raises.
2. Build a role-checked entry workspace: expenses, blind cash counts, receiving deliveries with invoice images, and accountant exports. Reuse ledger and purchasing engines. Protect attachments by tenant and restaurant.
3. Add explicit recipe yield and buying-unit conversion with additive migration, validation, and a single raw-usage expression used by stock calculations. Existing recipes default to 100% yield and existing units default to a factor of one.
4. Expose prep quantities, market list and combo calculations using existing tested functions; add a shift view with cash, M-Pesa and cancelled sales, and label stock evidence that cannot be attributed to a shift.
5. Test tenant/role boundaries, conversion and yield examples, input errors and screen interactions; run regression checks and production build, migrate only the local demo, and verify the running app. Record remaining real-data dependencies.

Acceptance: staff entries feed the existing owner numbers; repeated in-flight submissions cannot double-post; blind counts hide expected cash; no invented numbers or unexplained aggregate-to-shift attribution; all screens reachable; Eleven's till and real statement validation remain explicit onboarding dependencies.

## Completed follow-through requested by “FINISH”

Implemented forecast-to-purchase drafts, statement and bounded-count shift checks, owner-set scheduled prices with quoted checkout, per-dish measured learning used in simulations/recommendations, price ladder, reviewed menu trimming, priced Star–Puzzle candidates, ABC counting calendar, branch control comparisons and observed per-change monthly results. Staff entries now include counts/waste/issues/bills, a scoped offline queue, quick audited reversals, accountant P&L/expense review and receipt access. Acceptance and exact evidence: [ELEVEN_ACCEPTANCE.md](ELEVEN_ACCEPTANCE.md). Only the actual Eleven onboarding inputs and the documented evidence/interpretation boundaries remain; Eleven is deliberately unprovisioned.
