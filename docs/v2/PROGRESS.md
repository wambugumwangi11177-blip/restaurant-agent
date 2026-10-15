# LEVIII v2 — Progress log

Newest sprint first. Spec: [`SPEC.md`](SPEC.md). Gate: `make -C docs/v2 gate`.

> **STOP note:** none. (Written here, at the top, only if a STOP condition in SPEC §0.2 fires.)

---

## Open for the owner (decisions the build cannot make for you)

1. **Beef variance percentage (§7 #7).** Engine: gap ÷ expected = 33.3%. Client guide: gap ÷ used = 25%. Same 10 kg, same flag. Pick the denominator before the guide and the screen disagree; until you do, owner screens will say "10 kg missing" with no percentage.
2. **Four worked examples have no engine and no sprint** (§7 #4 target-margin price, #10 combo, #11 prep with cooked yield, #12 market list). They are strict-xfail goldens. Proposal: a small pure-function module `owner/kitchen.py` + `owner/menu_math.py` after P6 (no UI), or drop them from the client guide. Also #4 is internally inconsistent: rounded to whole KES (578 → 53,400) while #3 rounds to the KES 5 step (580 → 54,000).
3. **§7 #15 decision score.** The risk term 0.8 cannot occur (risk is 1–5 → 1.0/.75/.5/.25/0). A real decision scores 81.75 → priority 82, not 82.5.

## Sprint log (newest first)

### S1.4 Owner API skeleton — done

**Plan.** Goal: one owner API that composes today's engine output into the Home / Area / Report / Ask shape the owner shell will render, with an honest data state on every block, so P2 can run the demo on it and P4 can draw it. Files: `owner/{states,areas,home,reports,ask,registry}.py`, `routers/owner.py` (+`GET /owner/home?period=today|7d|30d`, `GET /owner/area/{key}`, `GET /owner/report/{daily|weekly|monthly|yearly}`, `POST /owner/ask`), a numeric `impact_cents_month` on the legacy decision cards, `execution/codemap.py` (the candidates resolved), tests `tests/test_owner_api.py` (72) and `tests/evals/test_e5_coverage.py` (8).

- **Composition only.** Every number is an existing engine's output reshaped: cents → KES at the edge, system words → owner words (§3.4), a `state`/`as_of`/`assumption` on each block (`owner/states.py`: live · as_entered · learning · stale · not_from_pos · no_data · unavailable). An engine that raises yields an `unavailable` block with a plain reason — never a 500, never the exception text (tested by making the profit engine explode).
- **One engine run per request** (`OwnerContext.cached`) and a SAVEPOINT around every block, so one failing engine cannot poison the session for the next.
- **Area == Home block.** `/owner/area/{key}` returns exactly the dict Home embeds (tested for all six areas); `costing_you_money` is exactly the first five ids of `/overview/today`'s attention list; `/owner/report/*` sales/orders/top dishes equal `/reports/*` to the unit; `/owner/ask` returns the `ai_ask` handler's finding unchanged (it is a delegate).
- **Owner-only, tenant-isolated, observer-blocked.** Every endpoint 403 for the six non-owner staff roles, 401 unauthenticated, and a second tenant's owner sees none of the first tenant's dishes/suppliers on any endpoint; forging `active_restaurant_id` does not cross tenants; `/api/v1/owner/*` is inside the observer-mode boundary.
- **What is deliberately NOT built here** (each is an honest `unavailable` block with its reason, and E5 lists it): P&L, costs covered, bills, licences, expense spikes (P3), M-Pesa match (P6), cash-gap patterns beyond the 28-day learning clock, the "LEVIII's read" note, and Ask's why / what-if / what-should-I-do / compare forms (S5.1). Reports carry sales and best sellers; every other section the plan names is `planned: true`.
- **Ranking.** `costing_you_money` today is the legacy order (operational facts first, then decisions by score). Only decision-layer cards carry a KES figure (`kes_month`); the stock-gap / cash-gap / till-gap / delivery-gap cards stay `null` until S4.3 extends the adapters. A card without a number says so; none is invented.

**What the first run of the tests found (and fixed in the same commit).**
1. A fresh tenant's areas read **live**: the static "ask the simulator" pointer and the till-connection status counted as measurements. Both are now `info` blocks that never decide an area's state — a fresh tenant's six areas are `no_data`.
2. The cash-patterns block said "learning, day 0 of 28" on a restaurant with no cash counts (it counted order history, not counts). It is now `no_data` until the first count, `learning day n of 28` after, then an honest `unavailable` (the detector is not built).
3. `pulse.money_match.cash` had a `state` but no `as_of` — the "every block has both" test caught it.
4. The E5 orphan check found four Home blocks no engine owned (`cash.patterns`, `permits.licences`, `coming_up.licences`, `permits.till_connection`); the first three were assigned (cash / money-planned), the last is a data-connection fact registered in `NOT_ENGINE_BLOCKS` with its reason.

**Registry (`owner/registry.py`).** 23 entries = exactly the figure 1.3 rows (a test compares the keys with `execution/codemap.py::ENGINES`). Each says owner name, area, Home zone, Home block paths, Ask topics, report sections, inputs, settings read, status (built / planned + sprint), and written exemptions (4, capped at 6 by a test). Every declared setting must be a real settings key, every Ask topic a real handler, every report section in `PLAN`; a test shows every owner setting is read by some engine except four that belong to S3.1/S5.3 (`prime_cost_target_pct`, quiet hours, `licence_warning_days`). The S0.2 candidates are resolved: `ops_manager` = Home health tiles, `creative` = "LEVIII's read", `enterprise` = compare-branches form (S5.1), and `graph` / `home_specialists` / `order_stock` / `ops_manager` / `creative` / `enterprise` are now classified in `execution/codemap.py::INFRASTRUCTURE` with reasons (`CANDIDATES` is empty; `registry.NOT_ENGINES` carries the same reasons and a test keeps both in step).

**E5 (coverage).** Run against the real composed Home of the golden restaurant, not against the registry's own claims. **23 engines · 21 built · 1 complete on all three surfaces · 26 open gaps** (Ask: 8, reports: 18) — full table in [`e5-coverage.md`](e5-coverage.md), regenerated by `make evals`. The gap list is an allow-list in the test that may only shrink (a new gap fails; a closed gap must be deleted; P4's exit is empty). Home itself has **no gap for any built engine**. Not checked by E5 (S2.1 owns it): that the demo produces *non-empty* output from every engine.

**Code-map shift.** Backend modules 151 → 157, routes 170 → 174; the candidate section of `coverage.md` is now empty.

**Gate.** backend **1082 passed, 1 skipped** (1010 + 72; 373 s) · evals **36 passed / 9 xfailed** (E2 28/9 unchanged, E5 8) · vitest 55 · tsc clean · lint ratchet OK (15E/4W) · `next build` OK · E6 not run (due by P4). **Timing, recorded not tuned:** `GET /owner/home` on the golden restaurant (1,442 orders, 8 dishes) = **~1.1 s, 16 KiB**; a 120-day, 2-branch demo will be larger — S2.1 must measure it, and if Home is over ~3 s the engines' repeated order scans are the place to look (the memoisation in `OwnerContext` already removes the duplicates it can).

**Deviations from the plan I wrote earlier this sprint:** no separate `owner/context.py` (the context class lives in `states.py` beside the state helpers it uses); Ask's `form` is always `what` until S5.1.

### S1.3 Defect fixes — done

**Plan.** Goal: remove the verified defects before they get surfaced on the new owner screens. A regression test per defect, written first (`tests/test_s13_defects.py`, 23 tests). **Evidence they bite:** run against the pre-fix source (source stashed, tests kept) 17 of 23 fail; the other 6 are "behaviour unchanged" checks (2026 holidays, neutral year, data files well-formed, ROI key, stored score stays while learning). Fixes restored, all 23 pass.

| Defect | Fix | Notes / honest limits |
|---|---|---|
| **D1** receipt flood | `_detect_payment_mismatches` flags only orders with `mpesa_checkout_request_id` set (LEVIII's own STK push); POS-fed orders are never flagged. Home gets **one** summary card ("Check M-Pesa payment evidence for N orders", KSh total) instead of one per order. | **Nothing in this repository writes `mpesa_checkout_request_id` today** (no STK push is built; only the column and migration exist), so in practice this rule fires on nothing until that path exists. That is the safe direction (the old behaviour flooded Home); it is not "detection working". The P6 statement match (door 3) is what will actually verify M-Pesa money. |
| **D3** supplier reliability | `_analyse_supplier` no longer writes. Below 3 closed orders (on time + late) a supplier is **"learning"**: `reliability_score: null`, label LEARNING, `closed_orders`, `at_risk` false, no recommendation; summary excludes them (`avg_reliability_pct` null when none measured). The stored `Supplier.reliability_score` is now refreshed at **PO close** (`receive_purchase_order`) once ≥ 3 orders closed — the write path that the read used to be. The tiered auto-approval's "3 closed orders" is now the same constant. | `on_purchase_order_late` (event handler) still subtracts 5 on a late delivery — a legitimate write path, left alone. `PARTIAL` is still neither on-time nor late (as before). |
| **D10** overtime cost | overtime hours × the shift's own hourly rate (cost ÷ hours) — a 10 h shift at KES 125/h: 2 h = KES 250, not the whole KES 1,250 shift. | No overtime premium (1.5×) is modelled; the spec says hours × rate. |
| **D12** holidays | `backend/data/ke_holidays_<year>.json` (2026 moved verbatim, 2027 added). A year with no file is neutral and logged once. Sunday holidays also observed on the Monday (2027: 11 Oct, 13 Dec, 27 Dec). | **2027 file is computed, not copied from a gazette — verify before relying on it** (Easter 28 Mar; Eids approximate). **2027 school-term breaks are deliberately empty** (calendar not verifiable; an invented window would lift forecasts for no reason). 2026 output unchanged. |
| **D15** | profit key `till_price_gap` (+ `portion_drift` alias, same rows, one release); recommendation type `till_price_gap`; copy is a signal ("Check the till…"), no "staff may be…". ROI reads the new key. | The old dashboard (`ProfitFull.tsx`, `roi/page.tsx`) still reads the alias; P4 moves the UI. |
| **D16** price rounding | `_round_price` (nearest) and `_round_price_up` (REPRICE, delivery price) round to the owner's `price_step_kes` (default KES 5): cost 26,000 cents → **43,500**. Float guard on the ceiling. A SURGE/STIMULATE whose rounded price equals today's price is no longer emitted. | Behaviour change beyond the spec: the delivery gap price now rounds **up** (it was nearest), so it can never undershoot the floor. |
| **D17** (found in S0.2) | `func.date()` over UTC replaced by Python bucketing with the new `time_utils.eat_date` in `ai/labor` (daily revenue) and `ai/fraud` (void-spike baseline). | **Not fixed:** the three `func.date` uses in `ai/whatsapp/brain.py` (daily briefing comparisons) — outside the engine registry; logged here. |

**E2 flipped in the same commit.** `test_ex03_…` now asserts KES 435 / KES 10,500 (was 433.50 / 10,050, recorded in the docstring); the strict-xfail "after D16" test is gone; ex05 asserts the alias equals `till_price_gap`. E2 is now **28 passed / 9 strict-xfail** (the D16 "today" and "after" tests merged into one live test). Four existing tests changed because the old behaviour was the defect: two fraud/cash tests and the Home test now give the order an STK checkout id (and assert one summary card + the POS-fed order ignored); the cost-610 floor test pins the original step 50 and the new default.

**Gate.** backend **1010 passed, 1 skipped** (987 + 23; 336 s) · E2 **28 passed / 9 xfailed** · vitest 55 · tsc clean · lint ratchet OK (15E/4W) · `next build` OK.

**Planted scenarios P15/P16** (supplier with one delivery must not show 100%; POS orders without receipts must not flood Home) are the S2.2 guards for D3/D1; they are asserted there once the demo generator exists.

### S1.2 Constants → settings — done

**Plan.** Goal: every business threshold an engine used to hard-code is now the owner's setting, read from one place, so changing a setting changes the engine (and the same number is used everywhere). Files: `owner/settings.py` (+`resolve`, fail-safe `get_settings`), `ai/{profit,pricing,menu_engineer,cash_reconciliation,stock_custody,simulation,labor,decisions}`, `routers/stock_custody.py`, `ai/orchestrator/executive.py`; tests `tests/test_settings_drive_engines.py` (24) + three existing test files that imported the removed constants.

**How engines receive settings.** `engine(db, rid, ..., settings=None)`. Passed explicitly (owner API, previews) it is used as is; `None` → `owner.settings.resolve` → the restaurant's saved row, else the defaults. **Deviation from the spec's wording ("`None` → defaults"):** resolving the saved row when nothing is passed means every existing caller (Home, OS, reports, WhatsApp, the old dashboard, the strategist) honours an owner's saved choice with no further edits — otherwise a setting would silently do nothing everywhere except the new API. Tenants with no row get the defaults, so existing callers and tests are unchanged. `get_settings` is fail-safe (SAVEPOINT + log + defaults) so code running before migration 051 can never take an engine down.

**Removed module constants** (a test now asserts they are gone): profit `HEALTHY_FOOD_COST_MAX/HEALTHY_MARGIN_MIN/CRITICAL_MARGIN_FLOOR/DELIVERY_COMMISSIONS`; pricing `MIN_MARGIN_PCT/MAX_FOOD_COST_PCT/DELIVERY_COMMISSIONS` and the inline 55 / 10 / 1.30 / 15; menu `POPULARITY_INDEX/FOOD_COST_CEILING_PCT/FOOD_COST_FLOOR_PCT`; cash `DRAWER_TOLERANCE_*`; custody `VARIANCE_THRESHOLD`; simulation `BASE_ELASTICITY`; labour `HEALTHY_LABOR_PCT_MAX/OVERTIME_HOURS_DAILY`. The duplicated delivery commissions (profit vs pricing — D11) are now one setting per platform.

**D11 food-cost unification (the one documented number change).** Menu engine scored food cost on a 25–40% band; profit and pricing used 35. All three now use `food_cost_target_pct` (default 35); the menu score's band is `(target − 10) … target`, i.e. 25–35% by default. Effect: a menu averaging 32% scores lower than before (cost component (35−32)/10 = 0.30 instead of (40−32)/15 = 0.53). No E2 golden touches the menu engine, so E2 is unchanged (28 passed / 10 xfailed); no existing menu test pinned the old band.

**Kept as module constants on purpose** (not owner choices in SPEC fig 3.2; named and commented): decision weights 0.45/0.25/0.15/0.15 and the KES 100,000 impact reference; velocity thresholds (surge 1.30, slow 0.60, 5 orders, 14 days, 7-day cooldown); the elasticity clamp −1.2…−0.4; twin damping 0.3; supplier reliability 85. New named constants this sprint: `FOOD_COST_WARNING_BAND_PTS = 5` (profit: WARNING is up to 5 points over the owner's ceiling; was the inline 40) and `FOOD_COST_BAND_PTS = 10` (menu score band). **Still inline in engines and not settings** (listed so nobody assumes they moved): profit drift > 5%, leak severity < 30%, daypart < 45%, channel < 30%, MoM < −10%; menu `ceiling+10` / `+5` priority bands; labour overtime > 20 h and day labour > 40%.

**Gate.** backend **987 passed, 1 skipped** (963 + 24 new; 340 s) · **E2 unchanged: 28 passed / 10 xfailed** · vitest 55 · tsc clean · lint ratchet OK · `next build` OK. Three existing tests imported the removed constants and now read `DEFAULTS` instead (`test_pricing_reprice_floor`, `test_menu_engineering_math`, `test_cash_reconciliation`); S1.1's "defaults equal the constants" test became "defaults are the spec table" because the constants no longer exist.

**What the tests prove.** One test per engine that *changing a setting changes its output*, explicit and saved: margin floor/target (profit leak line, leak price, REPRICE target, simulator floor, decisions), food-cost target (profit status + recommendation, STIMULATE offer gate, menu score), commissions (profit per plate 170 → 140 at 30%, pricing delivery gap price), max raise (surge 15% → 10%), offer size/lift, popular cut-off (a 40-unit dish flips Star/Plowhorse → Puzzle/Dog), cash tolerance in KES and in % (520 short is flagged at 350, forgiven at 600 or at 2%), missing-stock flag (33.3% flagged at 3/10, not at 40; saved 5% gap forgiven at a saved 10%; the variance-report endpoint shows the owner's line), price sensitivity (elasticity −0.58 → −0.83), overtime start and wages target. Mutation-style evidence that E2 still guards the numbers: E2 28/10 unchanged.

### S1.1 Settings — done

**Plan.** Goal: one settings service every engine will read (S1.2), editable by the owner, audited. Files: `models.py` (+`RestaurantSettings`, `RestaurantSettingsAudit`), `alembic/versions/051_add_restaurant_settings.py`, `owner/settings.py`, `routers/owner.py`, `main.py` (mount), `observer_mode.py`, `tests/test_owner_settings.py` (77 tests). Design decisions:
- **Defaults and ranges live once** (`owner/settings.py`: `DEFAULTS`, `FIELDS`); the PUT body model is generated from `FIELDS`, so FastAPI's 422 and the service's check cannot disagree. 22 settings, exactly the SPEC fig 3.2 table (defaults and ranges transcribed from it).
- **A complete row is always written** (no NULL-means-default), so a later change of a default never silently moves an owner's number; "no row" is the "owner has not chosen yet" state onboarding needs (`chosen: false`).
- **Money is cents inside, KES at the edge** (`cash_tolerance_cents` ↔ `cash_tolerance_kes`, `price_step_cents` ↔ `price_step_kes`).
- **Cross-field rule:** margin floor ≤ margin target (422 naming both). The spec lists the two ranges separately; a floor above the target would make every dish "priced too low", so I added the rule.
- **Owner-only** for read *and* write (`require_staff_role(OWNER)`; ADMIN/SUPERADMIN pass; every other role 403; a staff user with no role gets the existing `staff_role_unassigned`). Spec says owner-only; managers will read thresholds through the owner API payloads (`assumption`) in later sprints, not this endpoint.
- **No `restaurant_id` in the API at all** — the restaurant is the caller's own (`routers/deps.get_restaurant_or_none`, tenant-checked), so there is no id to forge. Tested, including a forged `active_restaurant_id`.
- **Not included as settings:** the analytic tuning constants (SURGE 1.30 / SLOW 0.60 thresholds, 5-order and 14-day minimums, 7-day cooldown, 2.5σ void spike, ...). SPEC fig 3.2 does not list them as owner choices; they stay module constants (named, commented) and are not "business rules" in the D11 sense.

**Found while building (a real hole, fixed).** `observer_mode.py` fails closed for `/overview`, `/reports`, `/ai` in the read-only Macsoft deployment because those figures come from local tables. A new `/owner/*` prefix is not in that list, so it would have **bypassed that boundary**. `/owner` is now in `_LOCAL_FACT_ENDPOINTS` (blocked for every method), with a test. Consequence to be aware of: while `observer_mode` is on, the owner API is unavailable by design; the MacSoft mirror must write rows (door 1) before it can feed the spine.

**Gate.** backend **963 passed, 1 skipped** (886 + 77 new in `test_owner_settings.py`; 320 s) · evals 28 passed / 10 xfailed (unchanged) · vitest 55 · tsc clean · lint ratchet OK · `next build` OK · E6 not yet. Tests cover: defaults pinned to today's constants; 40 out-of-range payloads → 422 and nothing written; inclusive bounds; unknown/mistyped fields; floor ≤ target; audit rows (and none for a no-op); history; owner/admin/superadmin allowed, six other staff roles + unassigned + anonymous refused; two-tenant isolation incl. a forged `active_restaurant_id`; per-restaurant rows for a chain; observer-mode boundary; migration up/down/up and offline PostgreSQL DDL.

**Migration 051** — additive (2 tables, no existing table touched). Guarded for the Dockerfile's `create_all()`-first deploy; idempotent; reversible. **I read the offline PostgreSQL DDL** (`alembic upgrade 050_creative_takes:051_restaurant_settings --sql`): correct types, `UNIQUE(restaurant_id)`, `ON DELETE CASCADE` to restaurants, `ON DELETE SET NULL` to users, lookup index. Reading the downgrade DDL exposed a bug (offline downgrade emitted nothing because the existence guard assumed "absent"); fixed (`_exists(..., offline=...)`) and now asserted. Nothing was run against any real database.

### S0.3 Golden fixtures + E2 characterisation — done

**Plan.** Goal: pin what today's engines say for the §7 worked examples *before* anything changes, so later sprints change numbers only on purpose. Files: `backend/tests/fixtures/golden_restaurant.py`, `backend/tests/evals/test_e2_money_goldens.py`. Design decisions (the spec's "one week, 8 dishes" fixture cannot be literal — §7's numbers cannot coexist in one week: 400 chips at KES 270 alone is KES 108,000, more than the KES 100,000 weekly sales of example #1):
- One shared **skeleton** (tenant, restaurant, 4 staff roles, supplier, 8 dishes with recipes and costs) plus **one seeder per worked example**. Each test gets a fresh DB (existing `db_session`), so scenarios never contaminate each other. Everything is seeded relative to `utcnow()` (42 modules import `utcnow` by value, so a global clock patch is not possible; relative offsets make results time-independent).
- Examples today's engines can answer are asserted **live**, with today's exact numbers (incl. today's wrong D16 answer, KES 433.50). Examples owned by later sprints are **strict xfail** with the owning sprint in the reason, so they fail loudly the moment the feature lands without the eval being flipped. Examples no sprint owns (#4, #10, #11, #12) are strict xfail with reason "unowned" and are escalated in the final report.
- A pure-arithmetic class re-derives all 16 spec results independently (exact integer / `Fraction` maths) so a typo in the spec cannot hide.

**Changed.** `backend/tests/fixtures/golden_restaurant.py` (skeleton + 8 seeders: chicken reprice, chips below menu, burger delivery, beef variance, handover, cash drawers, P&L week ± price rise); `backend/tests/evals/test_e2_money_goldens.py`.

**E2 result: 28 passed, 10 xfailed (strict), 0 failed.** Live characterisation of today's engines: #1 (sales 100,000 · ingredients 32,000 · gross 68,000 · wages 25,000), #2 (food 30.5% · wages 23.8%), #3 (**today KES 433.50 / 10,050 — the D16 answer**), #5 (25,714), #6 (170 vs 320 + Glovo delivery gap needs KES 800), #7 (10 kg; **engine says 33.3%, spec says 25%**), #8 (520 short flagged, 150 short not; one alert), handover (40 declared vs 38 → disputed), #15, #16. Pending, strict xfail with owning sprint: #1b/#2b/#13 → S3.2, #9/#14 → S3.3, #3-after-fix → S1.3. **Unowned (no sprint builds them): #4 target-margin price, #10 combo, #11 prep yield, #12 market list** — decision needed (see "Open for the owner" below).

**Evidence the evals bite.** Mutation check: applying the D16 fix (`ceil … / 500`) turns `test_ex03_…today…` red (`43500 != 43350`) *and* flips the strict xfail to XPASS(strict) = red. Reverted.

**Gate.** backend **886 passed, 1 skipped** (298 s) · evals **28 passed, 10 xfailed** · vitest 55 · tsc clean · lint ratchet OK (15E/4W) · `next build` OK · E6 not yet.

**Surprising.** 42 modules import `utcnow` by value, so the pre-flight idea of one global clock seam is not possible without touching all of them; fixtures use fixed offsets from a single `now` instead (numbers do not depend on the date the test runs).


### S0.2 Code map script — done

**Plan.** Goal: a code-derived map so "what is wired where" stops being a claim. Files: `execution/codemap.py`, `docs/v2/{codemap.json,coverage.md,figure_1_3.json}`, `backend/tests/test_codemap.py`, `docs/v2/Makefile` (`map` target, run first in `gate`). Tests: 6 structural tests.

**Method.** Python AST import graph (module-level *and* lazy in-function imports; dispatch tables like `_HANDLERS = {...}` and `from .x import y` re-exports are followed); TypeScript import graph (`@/` and relative); route table from `@router.<verb>` decorators; a surface = frontend entry files → every string literal that matches a route → handler analysed at *function* granularity (stops at engine modules and at hub modules that import everything). `python3 execution/codemap.py --why <surface> <engine>` prints the exact chain behind any dot. File-scoped rules (human-verified) cover what imports cannot show: calls that only read connection state (`STATUS_ONLY`) and the forecast panel that renders only when the source is verified (`CONDITIONAL_FILES`).

**Result.** 148 backend modules / 563 imports (167 lazy) · 231 frontend files / 485 imports · 167 routes. `codemap.py --compare-spec`: **127 of 132 cells of figure 1.3 reproduce from code.** The 5 that differ — the code wins, and none changes money maths:

| Cell | Spec fig 1.3 | Code | Why |
|---|---|---|---|
| Sales summary × Old dash | ● | ○ | `overview._summarize` is not called by `/dashboard`; its sales numbers come from `/ai/dashboard` (`ops_manager`). Same fact, different function. |
| Data quality × Home | ◐ | ○ | `ai.data_quality` is imported only by `/ai/data-quality` and the WhatsApp brain. Home never reaches it. |
| Goal mode × Old dash | ◐ | ● | `/ai/strategy` reaches `ai.orchestrator.strategist` directly; "partial" is a UX condition the graph cannot see. |
| Custody × Demo, Data quality × Demo | ≈ | ○ | `demo_scenario.py` has no variance/handover/data-quality maths (keyword evidence). |

Also found: 10 `backend/ai` modules are real analysis but not rows of figure 1.3 (`ops_manager`, `creative`, `home_specialists`, `graph`, `enterprise.*`, `order_stock`) — listed as **candidates** in `coverage.md`; S1.4's registry must register each or write down why not. Any *unclassified* `ai.*` module now fails a test (mutation-checked: adding `ai/zz_new_engine.py` made it fail).

**Gate.** backend **886 passed, 1 skipped** (880 baseline + 6 new) · vitest 55 · tsc clean · lint ratchet OK · build OK.

**Discovered, not in SPEC §1.5 (add to a later sprint, not fixed now).**
- **D17** — `func.date()` over naive-UTC columns, which SPEC §0.3 forbids (the day boundary drifts after 21:00 UTC): `ai/labor/intelligence.py:72,78`, `ai/fraud/detection.py:114,124`, `ai/whatsapp/brain.py:98,109,1045`. Fix alongside S1.3 or when each engine is next touched.
- `ai/labor/intelligence.py` and the S0.3 characterisation: overtime cost is the whole shift's cost (that *is* D10), confirmed by reading the code.

### S0.1 Baseline — done

**Plan.** Goal: a reproducible gate and recorded baseline before any behaviour changes. Files: `docs/v2/{SPEC.md,PROGRESS.md,Makefile,eslint-baseline.json}`, `execution/lint_ratchet.py`, `CLAUDE.md` (+ its mirror `GEMINI.md`). Tests added: none (infrastructure only).

**Changed.**
- `docs/v2/SPEC.md` copied from the recovered upload; `docs/v2/Makefile` with `test`, `fe`, `evals`, `e6`, `gate` (E1 backend, E1 frontend incl. `next build`, evals, E6 stub that says loudly it did not run).
- `execution/lint_ratchet.py` + `docs/v2/eslint-baseline.json`: eslint was not clean (15E/4W in 16 files), so "lint clean" is enforced as "no file gets worse".
- `CLAUDE.md` gets a "v2 build" section (existing text untouched). `GEMINI.md` is a byte-identical mirror of `CLAUDE.md` by the file's own statement, so it got the identical append; `AGENTS.md` does not exist in this repo.

**Gate (`make -C docs/v2 gate`, run end to end).** backend **880 passed, 1 skipped** (256 s) · vitest **6 files / 55 tests** · `tsc --noEmit` clean · eslint ratchet OK (15E/4W = baseline) · `next build` OK · evals: none yet · E6: not yet (due P4). Reproduces the baseline table below.

**Surprising.** (1) Truncated upload and missing `local_dev.db` (see pre-flight §0). (2) eslint baseline not clean. (3) Two spec §7 examples are not reproducible by the engine as written (#7 percentage denominator, #15 risk term) plus an internal rounding inconsistency (#4) — all recorded in pre-flight §0 and handled in S0.3.

---

## Pre-flight (answered before the first line of code, per SPEC §8)

### 0. Working facts that differ from the kickoff text

| Spec says | Reality in this session | Choice |
|---|---|---|
| Commit on branch `v2-build` | The session is bound to branch `ccr-fc67b65b-k9czx3` and pushing anywhere else needs explicit permission. | All sprint commits go on `ccr-fc67b65b-k9czx3` (same role as `v2-build`; never merged to main). Commit prefix `v2(Sx.y):` is unchanged. |
| Raw material includes `local_dev.db` | `backend/local_dev.db` is gitignored and **not present** in this container. | Build a local SQLite DB from the repo's own seed/generator code (`backend/seed_vibanda.py`, `execution/seed_local_dev_db.py`, and the S2.1 generator). Tests use per-test throwaway SQLite files, as today. |
| `figures/*.png` ship with the spec | The uploaded `LEVIII-v2-docs.zip` is **truncated** (327,680 bytes, no central directory). Recovered with CRC check: `SPEC.md`, `figures/settings.png`, `figures/ref_shift.png`. `figures/evals.png` was cut off; the other figures were never in the file. | `SPEC.md` is byte-identical to what was recovered; the PDF carries every figure, so no information is lost. Broken image links inside `SPEC.md` are expected. |
| Lint is clean (E1: "tsc, lint, build clean") | `eslint` baseline is **15 errors, 4 warnings** (spec said lint "not run"). | E1 lint rule becomes a ratchet: **no new eslint errors/warnings versus the recorded baseline**. Fixing the 15 is out of scope unless a sprint touches that file. |
| §7 #7: beef variance "25%" | `ai/stock_custody.py` computes `abs(actual − expected) / expected` = 10/30 = **33.3%**. The spec's 25% is gap ÷ *actual used* (10/40). kg gap (10) and the flag (>3%) agree; only the percentage differs. | Keep the engine's definition (gap ÷ expected). E2 asserts 10 kg, flagged, 33.3%, and carries a note. Owner copy will say "10 kg missing", not a percentage, until the denominator is decided. **Needs the owner's call** (client guide currently says 25%). Not a money-maths change (kg and KES value are identical), so not a STOP. |
| §7 #15: decision score 82.5 | Risk is a 1..5 ordinal → risk term ∈ {1, .75, .5, .25, 0}. The spec's 0.8 is not reachable. Engine returns `round(score*100)` (banker's rounding) so 82.5 → 82. | E2 asserts the weighted-sum arithmetic from the engine's own weights (= 82.5) plus an engine-produced decision at risk 2 (81.75 → 82). Flagged as a spec illustration, not an engine golden. |
| §7 #4: "260 / 0.45 = 577.8 → 578" | #3 rounds *up to the KES 5 step* (435) but #4 rounds to whole KES (578). With the 5-step it would be KES 580 → (580−400)×300 = **54,000**, not 53,400. #4 is "never pitched" (no engine emits a target-margin price today). | E2 asserts #4 as the raw arithmetic as written (578; 53,400) and notes the 5-step variant (580; 54,000). When/if a target-margin price is built it must pick one rule. |

### 1. What a top engineer would do on a brownfield codebase like this that the spec does not spell out

1. **Treat the spec as a hypothesis and re-verify it against the code before building on it.** Three discrepancies were found in the first hour (table above). Every sprint starts by re-reading the named files; disagreements are logged here, not silently absorbed.
2. **Characterise before changing.** S0.3 goldens pin today's behaviour (including today's wrong answer for D16: KES 433.50). When a sprint changes a golden it does so in the same commit, with a note saying why.
3. **Freeze the clock.** Several engines anchor to `utcnow()` (custody variance, drawer report, fraud) while others anchor to `analysis_anchor()` (latest orders). Goldens and the demo generator must inject a fixed "now" or they will rot. I will add one clock seam (monkeypatching `time_utils.utcnow`) rather than sprinkling `freezegun`-style hacks.
4. **Strangler with a parallel-run diff.** Before deleting `demo_scenario.py` or any old path, a test runs old and new side by side on the same data and diffs the owner-visible numbers. Deletion happens in one commit with the evals green (as the spec says).
5. **Migrations are the dangerous part.** Production is Postgres, tests are SQLite. For every migration: (a) `test_alembic_single_head` stays green, (b) upgrade → downgrade → upgrade on SQLite, (c) render the Postgres DDL offline with `alembic upgrade --sql` and read it, (d) additive only (new tables/columns with defaults; no destructive change). Nothing is ever run against `DATABASE_URL`.
6. **Money correctness by construction.** New money code is integer cents end to end; percentages are computed at the edge from integers; one rounding helper with tests. No `float` accumulation of money.
7. **Backwards-compatible renames.** `portion_drift` → `till_price_gap` keeps the old key as a deprecated alias for one release (spec). Same rule for any payload field the existing frontend reads.
8. **Performance budget.** `/owner/home` fans out to ~15 engines, each scanning 30-day windows. I will measure on the 120-day/2-branch demo data, record timings in this file, and share one pre-loaded query result per request where engines allow it, instead of discovering it in production.
9. **Tenant isolation as a first-class test.** One shared parametrised helper that creates two tenants and asserts every new endpoint returns nothing across the boundary (spec §0.3 demands a test per endpoint).
10. **Ratchets over big-bang cleanups.** Lint, coverage and the "—" placeholder count are ratcheted (can only improve) instead of rewriting unrelated code.
11. **Small reversible commits; refactor and behaviour change never in the same commit.**
12. **Keep a dead-code list from the code map** (modules with no inbound edges) but do not delete anything the spec does not name.
13. **Environment honesty.** CI runs Python 3.12; this box runs 3.13. Anything version-sensitive is noted. CI only runs on PRs/`main`/`review/**`, so pushing this branch alone does **not** produce a CI result; I will not open a PR unasked.

### 2. Raw material I will work from (not summaries)

- **Code, read in full before each sprint:** `backend/routers/{overview,reports,ai_ask,demo,deps}.py`, `backend/ai/{home_specialists,decisions/*,profit,pricing,menu_engineer,stock_custody,cash_reconciliation,fraud,labor,supply_chain,simulation,revenue_forecaster,inventory_predictor,reorder,reasoning/*}`, `backend/models.py`, `backend/alembic/versions/*` (head 050), `backend/demo_scenario.py`, `frontend/src/{lib,app,components}` named in Appendix A.
- **Tests as executable specification:** the 880 existing backend tests (esp. `test_overview*`, `test_decisions_ranking`, `test_pricing_*`, `test_stock_custody_and_staff_roles`, `test_cash_reconciliation`, `test_fraud_detection`, `test_demo_*`, `test_reasoning_grounding`, `test_tenant_isolation`) and the 55 vitest tests.
- **Data:** per-test SQLite fixtures; a locally generated SQLite DB (since `local_dev.db` is absent); the S0.3 golden restaurant; the S2.1 generated demo tenant. Never production.
- **Measured baseline:** the numbers recorded below, produced by running the suites here, not copied from the spec.
- **The code graph:** `execution/codemap.py` (S0.2) output, regenerated from source, not the stale `graphify-out/` that `CLAUDE.md` mentions (it is not in the repo).

### 3. Methods and tools per phase

| Phase | Methods | Tools |
|---|---|---|
| P0 baseline & map | Run suites, record numbers; AST + regex import graph; characterisation (golden) tests with a frozen clock | `pytest`, `vitest`, `tsc`, `eslint`, `next build`, Python `ast`, `make` |
| P1 one spine | TDD (eval first, watch it fail for the right reason); settings as typed columns + defaults object injected into engines (`settings=None` keeps old callers working); one regression test per defect; additive migration 051 | `pytest`, `alembic` (SQLite + offline Postgres SQL), SQLAlchemy |
| P2 demo | Deterministic seeded generator (`random.Random(seed)`, dates relative to a passed-in `today`); planted scenarios asserted by engine output (E4); parallel-run diff vs `demo_scenario.py` before deletion | `pytest`, ORM writes, `execution/reseed_demo.py` |
| P3 money | Integer-cent P&L; worked examples as goldens; missing-data states (`as_entered`) | `pytest`, `openpyxl`, `reportlab` |
| P4 Home v2 | Chart kit as small typed SVG components with explicit empty/learning states; contract-first (API payload fixtures drive component tests); mobile-first at 390 px | `vitest` + testing-library, **Playwright** with the pre-installed Chromium (E6), `tsc`, `eslint` |
| P5 OS & reports | Deterministic answers composed from the same owner API blocks; grounding verifier on every narrated sentence | `pytest`, `ai/reasoning/grounding.py` |
| P6 M-Pesa | Parser behind an interface, fixture designed from public format descriptions, property tests for matching windows/grouping | `pytest` |

### 4. What, other than me or the owner, shows each sprint is right

Independent, automated, fails loudly: **E1** full regression (880+ backend, 55+ vitest, `tsc`, eslint ratchet, `next build`) · **E2** money goldens (every §7 example to the cent, as characterisation first) · **E3** grounding (planted wrong number must be dropped) · **E4** planted demo scenarios P1–P16 detected by the named engine and present in the named block · **E5** registry coverage (every engine on Home, in OS, in ≥ 1 report) · **E6** Playwright owner tasks at 390 px and 1440 px with a console-error check. Plus, per sprint:

| Sprint | Extra independent checks |
|---|---|
| S0.1 | `make gate` reproduces the recorded baseline numbers |
| S0.2 | `codemap` output diffed against the spec's figure 1.3 rows; a test that fails if an engine in `backend/ai/` is missing from the matrix |
| S0.3 | E2 characterisation green on unmodified code; the same file is later used to prove D16 changes only the documented number |
| S1.1 | Tenant-isolation + bounds-validation tests; migration up/down/up + offline Postgres DDL |
| S1.2 | "Change one setting → engine output changes" test per engine; E2 unchanged except the documented food-cost unification |
| S1.3 | One regression test per defect D1/D3/D10/D12/D15/D16 (D16: cost 26,000 cents → 43,500) |
| S1.4 | `/owner/home` contract test on a fresh tenant and on the golden fixture; E5 report produced |
| S2.x | E4 for P1–P7, P11–P16; determinism test (same seed → identical rows); parallel-run diff against `demo_scenario.py` |
| S3.x | E2 §7 #1, #2, #9, #13, #14 exactly; export totals equal `/owner/report/monthly` |
| S4.x | E5 all entries; E6 at both widths; vitest per chart component; no-"—" test on live data |
| S5.x | OS five-forms test per area; E3 grounding |
| S6.x | E4 for P8; parser fixture round-trip |

I will also run the existing `test_alembic_single_head`, `test_tenant_isolation`, `test_db_guard` and `test_reasoning_grounding` suites as part of E1, since they guard exactly the things this build is most likely to break.

---

## Baseline (S0.1) — measured in this session at commit `4fe7ae5`

Environment: Python 3.13.16 (venv outside the repo, deps from `backend/requirements.txt`), Node 22.22.0 / npm 10.9.4, Linux, 4 vCPU. No `.env`, no `DATABASE_URL`, no `FEATURE_*` flags set (tests default to in-memory/throwaway SQLite; LLM calls off).

| Check | Result | Matches SPEC §1? |
|---|---|---|
| Backend `pytest` | **880 passed, 1 skipped**, 618 warnings, 304.7 s | yes (880 / 1) |
| Frontend `vitest run` | **6 files, 55 tests passed**, 13.6 s | yes |
| `tsc --noEmit` | clean (0 errors), 11 s | yes |
| `eslint` | **15 errors, 4 warnings in 16 files** | **no — spec said "not run"**; now a ratchet (`execution/lint_ratchet.py`, `docs/v2/eslint-baseline.json`) |
| `next build` | succeeds (all routes compile), 27.5 s | n/a (spec: not run) |
| Alembic head | `050_add_creative_takes.py` | yes |

Reproduce: `PY=/path/to/venv/bin/python make -C docs/v2 gate` (E1 + evals; evals dir is empty until S0.3).

Environment note: `pip install -r backend/requirements.txt` fails against the system Debian `setuptools` for `py-vapid`/`http-ece` (`install_layout`); a fresh venv installs cleanly. CI on Python 3.12 is unaffected. Use a venv.
