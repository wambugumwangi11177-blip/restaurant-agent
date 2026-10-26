# One owner experience — 25 October 2026

## Client contract

Reviewed the complete 48-page `Eleven on LEVIII` guide, with visual inspection of its screen diagrams. Its central contract is three input doors, one record set, shared engines, one Home, six areas, Ask LEVIII, Reports and rationed alerts. The earlier restoration made the historical scenario reachable but left two Homes and two independent numerical worlds. That approach is superseded by this integration.

## Active app

- `/home` is the only Home. All `/demo` and `/vibanda` bookmarks resolve into the same owner shell and appropriate area. No operational-versus-showcase Home switch remains.
- Home, Ask, Reports, Plan & improve and Team entries share a navigation, selected branch and visual system. Desktop sidebar, mobile bottom navigation, properly sized action controls, a clear sales pulse, status words and one generated-data notice replace the loose links and duplicate shells.
- All 109 historical question prompts are available in the canonical Ask screen. `owner/question_catalog.py` retains only topic routing, never scenario figures. Actual answers use `OwnerContext` and the existing operational engines. Sales answers use the Home/report summary and forecast blocks with explicit periods.
- `/api/v1/demo/*` is now a compatibility API backed by the owner services. The historical scenario router is not mounted by `main.app`. Its old implementation and scenario tests are preserved in an isolated historical test harness. There is no active read path from the new workspace to `demo_scenario` or `demo_answers`.
- Both branches use the same generated operational database. No new database or tenant was made, no existing records were reseeded, and no migration is required. Eleven onboarding will replace inputs and tenant configuration, not require a separate copy of the product.
- The short AI budget reservation transaction from the previous branch remains; newer dependency versions remain.

## Consistency repairs and additions

A real discrepancy was found: seven daily bars included seven calendar dates, while the weekly total covered a rolling 168 hours. `time_utils.reporting_days` now sets one Nairobi calendar window (including today, up to now) for overview and report periods. The current-day chart excludes future-dated transactions. A boundary regression includes an early sale on the first calendar date and excludes the eighth day and a future sale. Comparisons labelled seven complete days remain complete-day comparisons.

Home's pulse and Sales & Dishes share their seven-day trend calculation within a request. Pending period changes retain the previous data's own label and show that the view is updating. Monthly P&L remains the calendar month, not a rolling 30 days; its dates and completeness remain visible.

Daily, weekly, monthly and yearly PDF report downloads now use the exact owner report payload. The separate accountant P&L export remains. Generated monthly samples were rendered and visually reviewed. Report download errors are visible and retryable.

## Verification

- 249 frontend tests pass. Production build and TypeScript pass. ESLint ratchet remains its existing 14 errors/four warnings, with no new issues.
- 170 affected backend owner/API/P&L/role/workspace/Eleven/stock checks pass. 103 additional route/window checks and nine focused unified checks pass, covering aliases, tenant isolation, report PDF, calendar boundaries and expense propagation. These runs overlap; they are not summed as unique test counts.
- Live checks ran on both generated branches: Home daily and weekly sales match Reports and Ask; monthly P&L lines match Home, Money area, monthly report and accountant endpoint; old demo API values match the current owner API. Generated report downloads are valid PDFs. The initial live run is recorded under `.tmp/unified-live*`; calendar-window changes were then explicitly regression-tested and rechecked.
- A disposable-database expense of KES 123.45 was entered through the team expense API. It reduced both other costs and what was kept by exactly KES 123.45 across Home, the report and accountant P&L, without reseeding or refreshing a data copy.
- Browser QA covers the unified 1440-pixel desktop and narrow layouts, redirects and working navigation. The verified production build is running locally on port 3000. Evidence and command logs are under `.tmp/unified-*`.

## Honest limits

This is a generated-data demonstration, not an actual Eleven feed. No deployment or production writes were made. Real Eleven POS/statement compatibility still needs their samples, recipes, stock and staff configuration. Optional AI/provider messaging remains off locally. Missing statement coverage and missing boundary counts remain explicitly incomplete, never zero loss. The existing lint baseline is not lint-clean. No universal claim of zero bugs is made; checks establish the paths listed above.

The requested `graphify update .` cannot run because graphify is not installed on this host; no graph was present at task start.
