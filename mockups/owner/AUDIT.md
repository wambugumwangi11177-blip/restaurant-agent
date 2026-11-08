# Owner mockup audit vs *Eleven on LEVIII* (PDF)

Audit date: Nov 2026 · Branch: `mockups/owner-fresh` · Scope: owner HTML mockups only (`mockups/owner/`).

Legend — **Status before / after**

| Code | Meaning |
|------|---------|
| **Visual** | Dark SVG/CSS chart or diagram on the page (or in Why sheet where the guide expects tap-through depth) |
| **Text** | Plain copy, cards, or layout implementing the figure’s job without a dedicated diagram |
| **None** | Not shown (not needed on owner daily surfaces) |
| **N/A** | Staff-only, backend, or More/Settings explainer only per figure inventory |

**Summary counts (owner-relevant figures only, n=42)**

| | Visual | Text | None | N/A |
|---|--:|--:|--:|--:|
| **Before** | 14 | 19 | 3 | 6 |
| **After** | 25 | 12 | 3 | 6 |

## Figure audit table

| Figure | Title (short) | Page | Before | After |
|--------|-----------------|------|--------|-------|
| 2.1 | P&L staircase | money.html | Text | Text |
| 2.2 | Sales waterfall (KES) | money.html | Visual | Visual |
| 2.3 | KES 100 donut + formulas | money.html | Visual | Visual |
| 2.4 | Food/prime cost dials | money.html | None | Visual (See more) |
| 2.5–2.6 | Price rise columns/table | sales-dishes.html | Text | Text |
| 3.3 | Par / reorder stock line | stock.html | Text | **Visual** (To order + Why) |
| 3.4 | Missing: usage vs sales | stock.html | Text | **Visual** (Why: compare bars) |
| 3.5 | Beef gap bars + zone | stock.html | Text | **Visual** (gap compare on card) |
| 3.6–3.7 | Custody / three cases | stock.html | Text | Text (handovers + Missing) |
| 3.8 | Gap causes (non-accusatory) | stock.html | Text | **Visual** (Why radial) + Text |
| 3.9 | Recipe readiness | stock.html | Text | Text |
| 4.1 | Payment flows | cash-check.html | Text | Text |
| 4.2 | Three-way match triangle | cash-check.html | Text | **Visual** |
| 4.4 | Cash tolerance | settings.html | Text | Text |
| 4.6 | M-Pesa four outcomes | cash-check.html | Text | Text |
| 5.4 | Four dish groups (scatter) | sales-dishes.html | Text | **Visual** (See more) + Text groups |
| 5.3 | Learning gate | home.html | Text | Text |
| 6.1 | Break-even clock line | home.html, money.html | Visual | Visual |
| 6.2 | Bill radar forecast | money.html | Text | **Visual** |
| 6.3 | Costs going up bars | money.html | Visual | Visual |
| 6.4 | Shift report rows | cash-check.html, staff.html | Text | Text |
| 6.5 | Pattern heatmap | cash-check.html | Visual | Visual |
| 6.7 | Forecast range band | stock.html (Coming up) | Text | Text (labelled as estimate) |
| 6.9 | Prep → buy flow | stock.html | Text | Text (order-flow steps in Why) |
| 7.1–7.4 | Money leaks | home.html, sales-dishes.html | Text | Text |
| 8.3 | Rank by KES earned | sales-dishes.html | Visual | Visual |
| 8.5 | Menu long tail | sales-dishes.html | Text | Text |
| 9.1 | Five surfaces | Nav + more.html | Text | Text |
| 9.2 | Home four zones | home.html | Text | Text |
| 9.3 | Health strip tiles | home.html | Visual | Visual |
| 9.4 | Card anatomy | home, stock, alerts | Text | Text |
| 9.5 | Provenance labels | All pages | Text | Text |
| 9.6 | Ask five question types | ask.html | Text | Text |
| 9.7 | Report period depth | reports.html | Text | **Visual** (period blocks) |
| 9.8 | Monthly export | reports.html, money.html | Text | Text |
| 9.9 | Alerts rationed pyramid | alerts.html | Text | **Visual** |
| 9.11 | First week onboarding | home.html (Preview) | Text | Text |
| 9.12 | Plain words | All pages | Text | Text |
| 1.1–1.3, A, B | System / staff doors | — | N/A | N/A |
| 3.2, 3.10–3.11 | Stock staff workflows | — | N/A | N/A |

## Nav link check

All `href="*.html"` targets from owner pages resolve to files in `mockups/owner/`. Bottom nav: Home, Money, Stock, Ask, More on every page. **More** lists Sales & Dishes, Cash Check, Staff, Settings, Reports, Alerts, Ask. **index.html** links all 11 owner pages for developers.

## Files added/updated in this audit fix

- `assets/owner-charts.js` — shared dark SVG snippets (par line, gap compare/causes, three-way match, targets, quadrant, pyramid, report periods, bill radar).
- Page wiring: `stock.html`, `money.html`, `cash-check.html`, `sales-dishes.html`, `alerts.html`, `reports.html`, `assets/sample-data.js`, `assets/styles.css`.

## Not done (by design or missing backend)

- Full PDF teaching diagrams (pyramids, matrices, swimlanes) on daily surfaces — kept behind See more or Why only where listed above.
- Staff capture UI (1.3, 3.11), accountant export screen (9.8 live export), live POS feeds — mock data only.
- Branch comparison (8.7), ABC count calendar (8.6), price ladder (8.4) — not in scope for Eleven single-branch mockup.
- Attached **ideas-backlog-share.md** was not present in uploads; backlog items not cross-checked beyond `eleven-pdf-figures.md`.
