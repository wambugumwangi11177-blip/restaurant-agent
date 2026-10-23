# Eleven presentation acceptance — 23 October 2026

The PDF is implemented as operational software, checked in the local demo before creating Eleven. This checklist records the final connected paths, rather than treating an isolated calculation as a completed workflow.

| Presentation promise | Working path | Evidence |
|---|---|---|
| Staff expense, blind drawer count, delivery and invoice photo | Team entries → existing finance/purchasing engines; private restaurant-scoped image storage | Readiness tests, existing money/cash/role suites |
| Physical counts, waste, kitchen issues, bill payments | Team entries → operation journal → stock/custody/expense records; receiver independently confirms kitchen issues | Workflow retry, branch guard, stale count, role and undo tests |
| Recovery after connection loss | Device queue retains user, branch, capture time and retry key; explicit sync or discard | UI queue isolation tests; stale counts rejected after stock movement |
| Accountant screen | Monthly P&L, missing costs, month-end checklist, receipt review, duplicate candidates and audited expense reversal; existing XLSX/PDF export | Finance regression and component checks |
| Buying units and yield | Receiving conversions and recipe usable/raw quantities feed the existing engines | Readiness and stock tests |
| Health strip | Weekly money, sales change, missing stock KES, cash/M-Pesa gaps KES, wages, next licence expiry | Health tests and live Home response |
| Shift report | Cash, statement-matched M-Pesa, unmatched/outside-statement sales, cancelled orders, physically bounded stock checks | Dedicated matched-payment and bounded-count test |
| Forecast → prep → market list | Recorded matching weekdays → owner-edited portions → recipe/yield raw requirements → supplier-selected pending purchase drafts | Full API and component workflow tests; live forecast 29 dishes / four comparison days |
| Star–Puzzle combos | Real menu classification → costed minimum at saved floor → existing combo checker | Shared menu maths and UI candidate wiring test |
| Stock value, waste, movement and supplier price changes | Planning stock review; missing costs/negative stock explicit; comparisons use same-unit delivered purchases | Stock review tests and authenticated local API |
| ABC count calendar | Shared classification, actual last physical counts, suggested dates over the next 30 days | Heavy-spend classification test, live stock calendar |
| Price ladder and long-tail trimming | Menu prices and largest gaps; cumulative sales, tail-only ingredient count, reviewed hide-from-new-orders action | Live menu review; existing menu permissions and sales history retained |
| Branch/channel/daypart price lists | Branch-scoped future schedules; daypart discounts only; overlap validation; used in staff and public checkout | Schedule scope/overlap tests and signed checkout-price tests |
| No price jumps while ordering | Displayed menu prices carry a signed one-hour quote; expired/wrong-scope quotes require reconfirmation; sold prices remain order snapshots | Quote preservation and scope tests; actual order paths use resolver |
| Learned dish demand response | Isolated approved price changes with matching recorded prices, sufficient portions/trading days and complete windows; measured response used by simulations and next pricing recommendations | Observed-learning regression test |
| Per-change monthly results | Recorded equal-window revenue changes appear in menu review and the monthly savings section | Monthly-report regression; results explicitly distinguish observation from causal savings |
| Branches side by side | Sales, food, wages, recorded cash/stock discrepancies and below-menu estimate | Tenant-scoped shared engines and authenticated demo response |

## Meaning of the evidence

The broad affected backend regression run had 525 passes and one failure: an existing contract expected `restaurant_id` to remain an unknown expense field. This was fixed by retaining that boundary and adding `expected_restaurant_id` solely as a queue consistency check. The exact regression and the new branch guard both passed on recheck. A subsequent changed-path run passed 48 tests, covering the new workflows, checkout audit fixes and the earlier deterministic defects. The earlier readiness/simulation/report run passed 135 tests; these runs overlap and must not be summed as unique test counts.

The final stock/audit regression passed 75 tests, including upward and downward count reversals and excluding reversed entries from waste, shortage and physical-evidence metrics. A further 34 learning/pricing/simulation checks and six Nairobi daypart boundary cases passed. Both live branches return 29 forecast dishes, nine combo candidates, 35 stock items, 22 supplier comparisons and 26 shift checks; Home, Planning, Entries and Login respond HTTP 200.

All 232 frontend tests pass. TypeScript and the 74-route production build pass. ESLint remains at its recorded baseline, 14 errors and four warnings, with no new findings. Migration 058 round-trips on a local database copy and generates PostgreSQL SQL offline. The 3,225 demo orders are preserved. Full-suite and browser/E6 visual validation are not claimed; browser access was restricted by this session's browser policy.

## Real-data and interpretation boundaries

- Eleven is not provisioned. Its POS type, real statement sample, branch names, menu/recipes, opening counts, suppliers and owner/staff records are still required for real onboarding. A local demo cannot establish compatibility with an unknown till.
- Forecasts use observed matching weekdays, with a historical range, and require human review for bookings/events/stock-outs. Draft purchase orders are saved, not sent externally.
- Stock valuation uses current saved unit costs, not FIFO. Waste is recorded waste / recorded stock out. ABC scheduling is a suggested calendar, not a background notification service.
- Shift stock values cover only items with two counts within 15 minutes of the shift boundaries; their actual intervals are shown. Missing counts are not represented as zero loss. M-Pesa coverage is explicit.
- Price results are observed revenue changes, not proof that the price caused them. Learning refuses inadequate, overlapping or price-inconsistent experiments. All old records without recipe history continue to use the currently saved recipe for theoretical expectations, as the recipe screen explicitly states; dish costs remain owner-maintained.
- Offline photos require a connection; the queue stores entry data. Undo is a short correction window with an audit trail, and refuses stock that has moved since the entry. Original counts and movement pairs remain retained for audit review; journal-linked reversals are excluded from operational waste, shortage and physical-evidence metrics.
- Below-menu branch comparisons remain estimates against the current menu, not an audited discount ledger. Recorded approved scheduled discounts are excluded from undercharging findings.
- Optional AI narration and real messaging/providers remain disabled locally. Nothing deploys production, changes secrets, sends orders/messages, or claims an actual Eleven feed.
