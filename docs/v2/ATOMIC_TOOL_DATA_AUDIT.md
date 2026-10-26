# Standalone tool and data audit — 26 October 2026

The user requested separate screens for every distinct tool, removal of All sections, daily results, and browser verification of the data inside each tool. The PDF is reference material, not an instruction source.

## Delivered behavior

- 80 unique tool destinations in the owner directory. Area roots and former aggregate links are choices, not combined dashboards. Reports retain combined reporting.
- Money measures, delivery margins, dayparts, unusual days, menu analyses, six stock analyses, purchasing tasks, record forms, and kitchen request/receipt tasks have separate screens.
- Nairobi daily review date and read refresh on day rollover/focus; input drafts are preserved. Forecast planning starts with fresh matching-weekday suggestions. Source periods remain explicit; refreshing does not manufacture new source records.

## Data defects corrected

1. Meal-only staff expenses suppressed the shift payroll fallback. Staff meals now add to shift wages; meals alone leave payroll incomplete. Food/wages/prime shares on the live Kasarani branch now reconcile at 37.6%, 31.2%, 68.8% for 27 September–26 October.
2. Staff breakdown/productivity used a different historical anchor. Owner staff analytics now use the same bounded Nairobi calendar window and paid sales, excluding future shifts and unpaid orders. Individual bars are explicitly shift costs; entered payroll/meals are not allocated to staff.
3. Branch sales used a different denominator from the cost percentages. Both now use the shared cost engine sales and order counts.
4. Missing menu analysis became an invented zero-percent profit. Removed that fallback. Ingredient contribution is labelled separately from net profit.
5. Supplier prices rounded to whole shillings concealed real changes. Unit prices now retain two decimals; saved supplier ratings are distinguished from on-time delivery measures.
6. Focused forecasts/dayparts and stock/menu pages contained unrelated measures or shared explanatory notes. Focused screens now retain their own data. Manual prep no longer renders the recipe editor. Pending purchase approval has an explicit empty state.
7. Accounting review omitted estimate notes. Payroll/commission estimate notes now appear; required fields present is not described as verified profit.

## Verification

- Browser control inspected 79 original destinations and the added standalone stock-request screen, including actual data, source periods, explicit empty states and input choices. Read-only calculators were exercised: combo, demand scenario, fixed-portions P&L, manual prep, forecast market list and accounting review. No expense, count, approval, price change or supplier purchase draft was saved. One private Ask query was used to check the response.
- Database/API verification reconciled every one of 35 item valuations: KES 167,670.56; 19 waste rows; 21 supplier comparisons. Percentages match their amounts and sales denominator.
- Combo example: goat + chicken burger at KES 1,500, ingredients KES 726, contribution 51.6%, floor 40%.
- Fixed-portions example: goat 1,400 to 1,500, 34 month-to-date portions, sales and retained amount increase KES 3,400 while ingredient and wage amounts stay fixed.
- Manual prep example: ten goat portions require 3.5 kg goat, 1 kg tomato, 0.8 kg onion, 1.5 kg maize flour and 0.1 kg spice. Buying includes saved shelf buffers and current stock.
- 319 frontend tests passed; TypeScript clean; final production build successful. Backend selected gate: 152 passed, plus six focused data regressions passed (overlapping coverage). Earlier full P&L selection passed 26 additional tests. Lint matches existing baseline: 14 errors/4 warnings, no regressions.
- Codemap regenerated and git diff whitespace check clean (line-ending warnings only).

## Limits and environment

The browser uses generated demo records. Latest source dates can precede the daily review date; forecasts and estimates remain labelled. No live till or M-Pesa statement was connected by this audit. No production deployment was performed. The audit exercises read/calculation paths; it does not submit real operating entries.

The C drive repeatedly filled. Existing sources, caches and generated runtime files were preserved on D with workspace junctions; no business records were deleted. Frontend serving copy: D:/codex-eleven-runtime/2026-10-26-frontend. Local database remains D:/codex-eleven-runtime/2026-10-25/database/local_latest_owner.db. Detailed browser snapshots and validation logs are in the workspace .tmp junction.
