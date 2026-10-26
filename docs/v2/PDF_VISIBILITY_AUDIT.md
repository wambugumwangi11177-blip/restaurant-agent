# Client guide visibility audit — 25 October 2026

The client’s 48-page guide is the reference. This audit distinguishes visible application paths from diagrams explaining a process; a diagram is not automatically a claim that the demo has all necessary evidence or a live provider connection.

## Findings fixed

- Many charts existed only inside collapsed Home panels. Added six full area pages, stable section anchors, and an **Explore every tool** entry on Home plus the sidebar. The searchable directory maps tools to guide pages.
- Purchasing, Inventory and Menu links led through a dashboard layout that redirected demo owners Home. Added canonical owner routes reusing the existing permission-checked workspaces. Staff administration and kitchen receipt confirmation also have owner routes.
- Added the prime-cost dial and its editable saved target. The golden example now explicitly verifies 32% ingredients + 25% wages = 57% prime cost.
- Added the full price-impact P&L comparison, not just a food-contribution simulator. It uses actual paid portions in the calendar-month ledger, preserves ingredient/wage/other KES amounts, recalculates shares, labels its fixed-portions assumption, excludes cancelled/unpaid/foreign-branch orders, and changes no menu price. The separate demand-response simulator remains.
- Added complete settings and alert-feed pages. Quiet hours and urgent-push limits were backend settings with no obvious route from the owner workspace.
- Exposed recent sent/received handover evidence and pending confirmations. No-dispute no longer means all handovers matched. Made reorder draft quantities, suppliers and the working Purchasing link visible. Corrected the frontend reorder payload type to the existing API.

## Guide figure → application entry point

| Figure | Guide page | What the guide shows | Working entry point |
|---|---|---|---|
| A | 4 | The whole of LEVIII on one page | `/areas/permits` |
| B | 5 | Follow one shilling: a KES 1,200 M-Pesa sale | `/areas/permits` |
| 1.1 | 6 | Three doors, one translator, every number | `/areas/permits` |
| 1.2 | 7 | What breaks when a door fails | `/areas/permits` |
| 1.3 | 8 | Your team's own entry screens | `/entries` |
| 2.1 | 9 | Your P&L, top to bottom | `/areas/money` |
| 2.2 | 10 | Worked example as a waterfall (one week, KES) | `/areas/money` |
| 2.3 | 11 | Out of every KES 100, and the three formulas | `/areas/money` |
| 2.4 | 11 | The two numbers owners watch, on a dial | `/areas/money` |
| 2.5 | 12 | Raise the top dish's price, sell the same plates | `/areas/money#price-impact` |
| 2.6 | 12 | A price rise, line by line | `/areas/money#price-impact` |
| 3.1 | 13 | Six owner problems, solved | `/areas/store` |
| 3.2 | 14 | Stock moves in six steps, and each one can leak | `/areas/store` |
| 3.3 | 15 | Par level and reorder point, in one picture | `/purchasing` |
| 3.4 | 15 | How missing stock is worked out | `/areas/store` |
| 3.5 | 16 | Beef: from numbers to a responsible zone | `/areas/store` |
| 3.6 | 17 | Custody splits one restaurant into two zones | `/areas/store` |
| 3.7 | 17 | Custody: who answers for what (three cases) | `/areas/store` |
| 3.8 | 18 | A gap is not proof of theft | `/areas/store` |
| 3.9 | 18 | Recipes unlock the full picture | `/areas/store` |
| 3.10 | 19 | Units, yield and bar stock | `/entries` |
| 3.11 | 19 | Built for your storekeeper's speed | `/entries` |
| 4.1 | 20 | Four ways money comes in | `/areas/cash` |
| 4.2 | 21 | The three-way match | `/areas/cash` |
| 4.3 | 21 | How the three-way match catches a common trick | `/areas/cash` |
| 4.4 | 22 | How much difference is normal | `/areas/cash` |
| 4.5 | 22 | Which check catches which trick | `/areas/cash` |
| 4.6 | 23 | M-Pesa match: the four outcomes | `/areas/cash` |
| 5.1 | 24 | Intelligence turns data into decisions | `/areas/sales_dishes` |
| 5.2 | 24 | What each suggestion needs | `/areas/sales_dishes` |
| 5.3 | 25 | LEVIII learns before it advises | `/areas/sales_dishes` |
| 5.4 | 26 | Your dishes in four groups | `/areas/sales_dishes` |
| 5.5 | 27 | Which price idea fires, and when | `/areas/sales_dishes` |
| 5.6 | 27 | What to look at first | `/os` |
| 5.7 | 28 | Your settings, always visible | `/settings` |
| 6.1 | 29 | Break-even Clock: the moment today is paid for | `/areas/money#costs-covered` |
| 6.2 | 30 | Bill Radar: seeing the shortfall before it happens | `/areas/money#bills-coming-up` |
| 6.3 | 30 | Costs going up | `/areas/money#costs-going-up` |
| 6.4 | 31 | Shift report: every check, one row per shift | `/planning#shift-report` |
| 6.5 | 31 | Recurring patterns beat one bad night | `/areas/cash#recurring-patterns` |
| 6.6 | 32 | Star–Puzzle pairing, priced | `/planning#combo-checker` |
| 6.7 | 32 | Forecast as a range, and the day that fell out of it | `/areas/sales_dishes#next-7-days` |
| 6.8 | 33 | Why was Tuesday bad? | `/os` |
| 6.9 | 33 | Prep Planner and Market List | `/planning#forecast-planner` |
| 7.1 | 34 | Leak 1: dishes priced too low | `/areas/sales_dishes` |
| 7.2 | 34 | Leak 2: money given away at the till | `/areas/sales_dishes` |
| 7.3 | 35 | Leak 3: delivery dishes that barely earn | `/areas/sales_dishes` |
| 7.4 | 35 | Leak 4: weak hours | `/areas/sales_dishes` |
| 8.1 | 36 | Price differences: where the safe line sits | `/planning` |
| 8.2 | 36 | Learn real price sensitivity | `/planning` |
| 8.3 | 37 | Rank dishes by shillings, not percentages | `/areas/sales_dishes#what-each-dish-earns` |
| 8.4 | 37 | Price ladder check | `/planning` |
| 8.5 | 38 | Menu trimming: the long tail | `/planning` |
| 8.6 | 38 | Count by ABC class | `/planning#stock-review` |
| 8.7 | 39 | Your branches side by side | `/planning#branch-review` |
| 9.1 | 40 | Five surfaces, five jobs | `/explore` |
| 9.2 | 41 | Your Home screen: four questions, five parts | `/home` |
| 9.3 | 42 | The health strip: one number, one rule per tile | `/home` |
| 9.4 | 42 | Anatomy of a card | `/home` |
| 9.5 | 43 | Every number says where it came from | `/home` |
| 9.6 | 43 | Ask LEVIII: five kinds of question | `/os` |
| 9.7 | 44 | Reports grow with the period | `/reports` |
| 9.8 | 44 | Monthly report and the accountant's export | `/reports` |
| 9.9 | 45 | Alerts are rationed | `/alerts` |
| 9.10 | 45 | Who uses LEVIII at Eleven | `/entries` |
| 9.11 | 46 | Your first week | `/home` |
| 9.12 | 46 | Plain words on every screen | `/home` |

## Verification and limits

The directory anchor regression checks every referenced area section. 251 frontend tests pass; TypeScript and production build pass. The affected backend run passed 90 checks with one outdated assumptions-list expectation; that expectation was updated for the new prime-cost target and the exact golden plus the three new model tests all pass on recheck. The earlier targeted money/workflow run passed 39 checks. Test counts overlap. Lint remains the existing 14-error/four-warning baseline, with no new findings.

Browser verification follows Explore → full Money area → Quarter chicken KES 400 to KES 450 → actual P&L comparison: 37 recorded paid portions, KES 1,850 additional hypothetical sales and operating result; ingredient, wages and other-cost KES stay unchanged. The browser also verifies Purchasing loads actual orders and par-level controls rather than redirecting Home. No supplier order was approved or sent. Screenshots and logs are under `.tmp/pdf-*`.

**Remaining evidence boundary:** existing physical stock counts cover the entire item, not independent store and kitchen balances. Confirmed/disputed handovers are visible, but the app must not claim that every later usage gap is proved to belong to a particular zone. The screen states this; independent zone-count modelling remains separate work. Real till/statement compatibility still needs client samples. Optional AI/provider messaging is disabled locally. These limits are not represented as completed measurements.

No production deployment, live Eleven provisioning, reseeding or destructive data change was performed.
