# Demo Restaurant showcase

Demo is a separate tenant with a Home / OS / Reports shell under `/demo`.
The new `/api/v1/demo/*` routes require both the configured Demo owner email
(`DEMO_RESTAURANT_OWNER_EMAIL`, default `owner@demo-restaurant.example`) and the
Demo tenant and selected restaurant. Naming another tenant Demo does not grant access.

`backend/demo_scenario.py` holds one deterministic scenario: 56 daily summaries,
six dishes and three opportunities. These are process-memory Python values,
never inserted as orders, menu items, inventory or payments. Every screen labels
them as illustrative. Existing operational APIs and Vibanda's source gates remain
separate. No schema migration is needed; the existing Alembic head remains 050.

## What works

- Home totals, all 20 area evidence views, period reports and OS explanations.
- Seven-day weekday-mean revenue projections; the range describes sample
  variation, not a calibrated probability or guaranteed outcome.
- A price/demand simulator recalculates food contribution without changing prices.
- Potential savings show quantities, rates and assumptions. They are not realised
  savings, and no subscription ROI ratio is claimed without a subscription cost.
- Attention acknowledgement and "set aside" stay in the browser for the session
  (`sessionStorage`, key `demo-home-decisions-v1`), so a reload or a trip to another page does not
  undo them; nothing is written to the server. External messaging, purchasing,
  roster changes and other business actions are not executed by the demo.
- Reports state how many sample days are available; yearly does not invent a year.

## Creative layer and cost

`FEATURE_DEMO_CREATIVE=true` enables optional Demo writing only. It still respects
`FEATURE_AI_NARRATION`; it does not enable automatic creative calls for Vibanda.
The existing narrator handles provider selection (OpenRouter when configured),
PII scrubbing, spend limits and token metering. Numeric grounding filters the
response. Normal browsing and normal OS explanations do not call a model.

Creative results are cached for 30 minutes, scoped by tenant, restaurant, day,
scenario version and request. The process cache is bounded to 128 entries;
failures cool down for two minutes. It resets on deployment. Normal token-usage
audit rows still exist; there is no synthetic business-data growth. The current
single-worker deployment makes single-flight caching effective. Multiple replicas
would require a shared cache to avoid repeated provider calls.

## Validation

Run backend `tests/test_demo_showcase.py` plus tenant, creative and Demo source
regressions, frontend `tests/demo-restaurant.test.tsx`, TypeScript, lint and build.
Verify the live `/demo` route after publishing: a successful build alone does not
prove that the domain points to it. The previous frontend alias target was
`frontend-32mhjc4zz-mbuguss-projects.vercel.app`.

## Deployment identity (verified 2026-09-30)

The active Railway workspace is **Wambugu's Projects**, project
`123c19bf-5b77-4e1f-833d-511ad9bdd733`, production environment
`cbac60cf-c680-45bd-aa25-ec7d6b3f64ed`, service
`69a12624-1820-4c4e-9305-9cdf57f088b4` (`restaurant-agent`). API:
`https://restaurant-agent-production-653f.up.railway.app`.
The older Mbuguss project `3080e9f0-01dc-42c0-b6bb-8280b746f5e0` is not this
deployment. Verify account and project identity before changing configuration.
Frontend remains the Vercel `frontend` project with the
`https://vibandavillage.vercel.app` alias; Demo signs in to its separate tenant.

## Owner experience (2026-09-30)

- Every area page explains itself in plain words first: "In plain words", what needs attention, what
  we suggest and why, then the evidence table. All text is built from the scenario values, never typed.
- **Stock is built from recipes** (`RECIPES` in `demo_scenario.py`): each ingredient traces to a menu
  dish. Usage per day comes from the recipes and today's sales.
- **Modules learn from expected sales.** Each coming day is scaled from the weekday sales forecast
  (same dish mix as today). That gives per-ingredient run-out day and order quantity, plus kitchen plates,
  suggested headcount, expected guests, and a supplier-grouped order list on Purchasing.
- Forecast days each carry a plain-language reason (tap a day; no OS trip needed).
- Home ends with an ideas box: data-checked ideas first, then AI ideas. No creative toggle anywhere.
- OS: prompted questions grouped by part of the restaurant; the deterministic answer appears at once and
  an AI idea is added underneath when ready (hidden if unavailable).
- Reports: charts, plain sections, PDF download (`GET /api/v1/demo/reports/{period}/pdf`, ReportLab) and print.

### One source for each figure

Figures that appear in more than one place are constants at the top of `demo_scenario.py`
(`ORDERS_TODAY`, the channel mix, `OVERTIME_HOURS`, `LUNCH_PEOPLE`, `BOOKING_SLOTS`,
`PURCHASE_ORDERS`, ...) and everything reads them, so Home, the area pages and the OS cannot disagree.
Tests change a constant and check every place follows. An alert that another card already says better
is tagged `repeat_of=<id>` where it is defined, and Home shows the other card once. `/ideas` reports
`checked` as the number of areas it actually read, and shows one idea per area before any area's second.

### Answers to the prompted questions

Each of the prompted OS questions has its own answer in `backend/demo_answers.py`, written as plain
sentences whose every figure is computed from the scenario (never typed). A question is matched by its
exact wording, not by keywords, so an answer cannot be about the wrong ingredient, dish or day; typing a
prompted question in full still reaches its own area. Any other typed question keeps the general answer
for its area. A test reads `frontend/src/lib/demoQuestions.ts` and fails if a question has no answer, an
answer has no question, or two questions in one area get the same text. When the AI is on, it is given the
calculated answer (`calculated_answer` in its evidence) and asked to keep its figures.

### AI reliability

Reasoning models (the default free Nemotron) burn a small token budget "thinking" and can print their planning.
Creative calls therefore send `reasoning: {effort: none}` on OpenRouter (retried without it if a model rejects
the field), get a larger token budget, and must finish with a `FINAL:` line; `creative_final`/`creative_ideas`
refuse anything else. Web research for the ideas box is off; set `DEMO_IDEAS_WEB=true` (OpenRouter only,
about $0.007 per uncached search) to enable it.

### Deploying the frontend

Pushing to `master` deploys the backend (Railway). The frontend is **not** deployed by Git for the live domain:
Git pushes only create Previews in a different Vercel project. From `frontend/` run `vercel deploy --prod --yes`
(built in Vercel's cloud), then `vercel alias set <new-deployment-url> vibandavillage.vercel.app`. Test in CI first
by pushing a `review/**` branch.
