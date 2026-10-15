# LEVIII v2 — Progress log

Newest sprint first. Spec: [`SPEC.md`](SPEC.md). Gate: `make -C docs/v2 gate`.

> **STOP note:** none. (Written here, at the top, only if a STOP condition in SPEC §0.2 fires.)

---

## Open for the owner (decisions the build cannot make for you)

1. **Beef variance percentage (§7 #7).** Engine: gap ÷ expected = 33.3%. Client guide: gap ÷ used = 25%. Same 10 kg, same flag. Pick the denominator before the guide and the screen disagree; until you do, owner screens will say "10 kg missing" with no percentage.
2. **Four worked examples have no engine and no sprint** (§7 #4 target-margin price, #10 combo, #11 prep with cooked yield, #12 market list). They are strict-xfail goldens. Proposal: a small pure-function module `owner/kitchen.py` + `owner/menu_math.py` after P6 (no UI), or drop them from the client guide. Also #4 is internally inconsistent: rounded to whole KES (578 → 53,400) while #3 rounds to the KES 5 step (580 → 54,000).
3. **§7 #15 decision score.** The risk term 0.8 cannot occur (risk is 1–5 → 1.0/.75/.5/.25/0). A real decision scores 81.75 → priority 82, not 82.5.

## Sprint log (newest first)

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
