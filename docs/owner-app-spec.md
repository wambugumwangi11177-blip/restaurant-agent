# Owner app (Eleven) — v11 redesign spec

**Audience:** builders only. User-facing copy must **not** say “AI” or internal engine names. Jack (store role) never sees Money or owner financials.

**Design system:** existing `owner-glass` dark theme. One chart library: **Recharts**. Every chart: one-line plain-English caption under it, tap → detail route with tables/numbers, grey outline empty state (“Starts when the till connects”).

**Navigation (bottom):** Home · Money · **Ask OS (centre FAB)** · Stock · More. Team lives under More only.

**Refresh:** page navigation cache-busts GETs so till sales, handovers, and price confirms appear on next visit (no manual refresh).

**Stacks:** DEMO seed = WITH DATA (30–90 days Nairobi-shaped history). EMPTY stack = clean empty states everywhere.

---

## Global patterns

| Pattern | With data | Empty |
|--------|-----------|-------|
| Chart block | Recharts + caption + chevron to `/eleven/.../detail` | `owner-chart-empty`: dashed border, caption explains what populates it |
| KES figures | `formatKes`, 2dp when under 100k else whole KES | “—” or “0” with same empty copy |
| Decisions | Ranked buttons by `kes_at_stake` desc | Setup checklist on Home only |
| Reports | In-app notification + list in Settings › Reports | “No reports yet” |

**Auth:** owner `ADMIN` + `StaffRole.OWNER`, tenant `eleven`. Jack: store routes only; RBAC unchanged (`staff-roles-permissions` skill).

---

## Home (`/eleven`)

### Top line (always visible)

| UI | With data | Empty | Source | Trigger |
|----|-----------|-------|--------|---------|
| Today’s sales so far | KES + ticket count | “0 · connect till” hint | `GET /api/v1/eleven/home/today` (new) aggregates paid `Order` since 06:00 EAT | POS webhook, import |
| Cash expected at close | KES range (sales − paid bills − M-Pesa share + opening float if set) | “Set opening float in Settings” or “—” | `GET /api/v1/eleven/home/today` + `eleven_outcomes.cash` + bills | sales events, bill pay |

### Needs you

| UI | With data | Empty | Source | Trigger |
|----|-----------|-------|--------|---------|
| Decision buttons (all types) | Sorted by KES at stake; each → `/eleven/decisions/[id]` | Hidden; see setup below | `GET /api/v1/store/approvals` `pending` + enriched metadata | restock, waste, handover mismatch, bill approve, etc. |
| Decision detail page | Why, evidence, photo URL, numbers, actions (approve/reject/defer) | N/A | `GET /api/v1/eleven/decisions/{id}` (new) | same as pending item |

### Waiting on others

| UI | With data | Empty | Source | Trigger |
|----|-----------|-------|--------|---------|
| Rows: name, role, what, reminder count | `waiting` slice from approvals feed | “Nobody waiting on you.” | `GET /api/v1/store/approvals` `events` / labels | `approval_workflow` reminders on feed GET |

### Done today

| UI | With data | Empty | Source | Trigger |
|----|-----------|-------|--------|---------|
| One line summary | e.g. “4 handovers matched, 1 delivery checked” | “Nothing recorded yet today.” | `GET /api/v1/eleven/home/done-today` (new) counts handovers, deliveries, day close | Jack handover, delivery receive, close |

### Empty-only setup

| Step | CTA | Source | Trigger |
|------|-----|--------|---------|
| Jack: answer setup questions | → More › Team (Jack answers) | store questionnaire completion % | Jack `/store/questions` |
| Connect the till | → Settings › Connections › Till | `PosSourceBinding` + last inbox receipt | webhook / bind |
| Add staff | → More › Team › Add | staff count | owner invite |

### Removed (v11)

- “Till live” card, duplicate sales lines, “how restaurant is doing” strip, old specialist tiles that repeat Money.

---

## Money (`/eleven/money`)

Hub scroll; each block = chart + caption + link.

| Block | With data | Empty | Source | Trigger |
|-------|-----------|-------|--------|---------|
| Today strip: sales, break-even clock, cash expected | live | grey placeholders | `GET /api/v1/eleven/money/today` (new) | orders |
| 30-day sales line | daily KES | flat zero line + empty | `GET /api/v1/eleven/money/series/sales?days=30` (new) | orders |
| This week vs last | two bars or % | empty | same series | orders |
| 7-day forecast range bars | low–high band + point | “Need a week of sales” | `ai/revenue_forecaster.py` via `GET /api/v1/eleven/money/forecast?days=7` (new) | on read + 05:00 cron |
| Plates per dish (7d) | bar chart top N | “No dish sales yet” | `GET /api/v1/eleven/money/dishes/plates` (new) | order lines |
| P&L waterfall (MTD) | cascade chart | empty | `GET /api/v1/eleven/pnl` + waterfall builder (new) | orders, costs, bills |
| See full P&L | → `/eleven/money/pnl` | empty table shell | `GET /api/v1/eleven/pnl?period=month` | month events |
| **Final monthly P&L** (`/eleven/money/pnl`) | Every line in owner words, % sales, vs LM vs target, lock at month end, export xlsx/pdf, summary sentence | “Month not closed” / no rows | `GET /api/v1/eleven/money/pnl/monthly/{yyyy-mm}` (new) + export routes (new) | day close, bills, payroll |
| Where money goes pie | COGS, labour, bills, waste, net | empty | `GET /api/v1/eleven/money/where` (new) | rollup |
| Food cost % vs target | line; red if over | empty | `GET /api/v1/eleven/money/food-cost` (new) + settings target | prices confirmed, sales |
| Cash vs M-Pesa + expected drawer | pie + number | empty | payment method on `Order` + cash endpoint | POS |
| Bills paid/due/unknown + 30d cash-after-bills line | bars | empty | bills models + `GET /api/v1/eleven/money/bills` (new) | accountant, owner pay |
| Dishes hub → `/eleven/money/dishes` | quadrant, plate profit, Pareto, delivery vs dine-in, price suggestions | empty states per chart | `menu_engineer`, dish costs, orders | on read |
| Hour × day heatmap | cells | empty | orders timestamp EAT | POS |
| 3-month bars + average | revenue bars | empty | 90d aggregation | POS |
| Waste & missing KES bars | from movements flagged waste/shrink | empty | stock movements + custody | waste POST, variance |
| Supplier price trends | multi-line | empty | `InventoryItem.cost_per_unit` history | invoice confirm |
| Profit per weekday | bar | empty | orders − COGS by weekday | POS |
| Avg spend per customer | line (tickets proxy) | empty | revenue / distinct tickets | POS |
| Discounts/voids by person | bar (staff attribution when present) | empty | void/discount lines | POS |
| Monthly goals progress | vs target sales & food cost | empty | settings targets + MTD | owner settings |

---

## Stock (`/eleven/stock`)

Tabs or sections: **Levels · Reorder · Missing · Spoilage · Handovers · Counts · Trends · Waste · Suppliers · Prep**

| Block | With data | Empty | Source | Trigger |
|-------|-----------|-------|--------|---------|
| Par bars (green/amber/red) + days left | per SKU | “No inventory yet” | `GET /api/v1/eleven/stock/levels` (new) + par from reorder_points | sales, delivery, count |
| Reorder list | use/day × lead time; Jack “send to owner approve” | empty | `ai/reorder.py` PO drafts | inventory touch |
| Missing: issued vs used kg+KES + photo | variance chart | empty | `stock_custody` window | handover, sales |
| Spoilage/expiry by date + zone | list/chart | empty | expiry fields + waste | Jack waste |
| Handover timeline | photo, PIN, time, matched | empty | `GET /api/v1/eleven/handovers` | Jack handover |
| Count history + photos + who | list | empty | stock count events | Jack count |
| Use trend lines | OUT movements | empty | movements | sales, issue |
| Waste bars by reason | KES | empty | waste movements | Jack |
| **Suppliers** (`/eleven/stock/suppliers`) | on-time %, lead days, price trend, jump flags | empty | deliveries, PO, invoice history | Jack/accountant |
| **Prep** (`/eleven/stock/prep`) | forecast plates × recipes − kitchen stock | empty | `GET /api/v1/store/prep` (owner proxy) | handovers, sales |

Jack actions stay on `/store/*`; owner sees read-only + approve restock from Home/Money decisions.

---

## Ask OS (`/eleven/ask`)

Centre nav on every page (not a tab slot — floating centre button).

| UI | With data | Empty | Source | Trigger |
|----|-----------|-------|--------|---------|
| Chat | Answers product help + live numbers | Explains setup steps | `POST /api/v1/ai/chat` + help corpus (new static `docs/owner-help.md` ingested) | on demand |
| History | session list in More | “No questions yet” | chat session store | on demand |

---

## More (`/eleven/more`)

| Section | With data | Empty | Source | Trigger |
|---------|-----------|-------|--------|---------|
| Team | role, shift, PIN status, handover history, short score, add/remove, Jack setup answers | invite CTA | `eleven_handover`, staff APIs, questionnaire export | Jack + owner |
| Alerts history (filter) | list | empty | `GET /api/v1/eleven/alerts` | events |
| Handovers | link to stock handover timeline | empty | same | Jack |
| Ask OS history | link | empty | chat | owner |
| Help | plain guide every page (no engine names) | full guide still readable | static help route `/eleven/more/help` | static |
| Logout | auth | auth | `POST /api/v1/auth/logout` | user |

---

## Settings (`/eleven/settings`)

| Page | With data | Empty | Source | Trigger |
|------|-----------|-------|--------|---------|
| **Reports** (`/eleven/settings/reports`) | Daily 21:00 EAT, weekly Mon, monthly final P&L; in-app notification; past PDF/xlsx list | “Reports start after first day of sales” | `GET/POST /api/v1/eleven/reports/*` (extend) + scheduler | cron + month lock |
| Notifications prefs | toggles | defaults | user prefs model | owner |
| Targets | food cost %, sales goal, par defaults | defaults | restaurant settings | owner |
| Restaurant | name, hours, bills assignee | partial from onboarding | restaurant + bills config | owner |
| Connections | till, WhatsApp, accountant status | disconnected states | inbox, Twilio, staff roles | owner/Jack |
| Language EN / Kiswahili | strings file `locales/sw.json` (partial OK) | EN only | i18n | owner |

---

## API surface (new / extended) — implementation checklist

| Route | Purpose |
|-------|---------|
| `GET /api/v1/eleven/home/today` | sales + cash expected |
| `GET /api/v1/eleven/home/done-today` | matched handovers, deliveries |
| `GET /api/v1/eleven/decisions/{id}` | decision detail |
| `GET /api/v1/eleven/money/today` | Money top strip |
| `GET /api/v1/eleven/money/series/*` | sales, food cost, cash-after-bills, etc. |
| `GET /api/v1/eleven/money/forecast` | 7d range |
| `GET /api/v1/eleven/money/pnl/monthly/{ym}` | final P&L + lock flag |
| `GET /api/v1/eleven/money/export/{ym}.{xlsx\|pdf}` | exports |
| `GET /api/v1/eleven/money/dishes/*` | menu engineering bundle |
| `GET /api/v1/eleven/stock/*` | levels, missing, suppliers, trends |
| Extend `leviii_test_seed` | 30–90d orders, movements, handovers, bills for DEMO; minimal for EMPTY |

Existing: `GET /api/v1/store/approvals`, `GET /api/v1/eleven/pnl`, `GET /api/v1/eleven/summary`, `GET /api/v1/eleven/handovers`, `GET /api/v1/store/prep`.

---

## Restock human-in-the-loop (owner + Jack)

When Jack or the reorder job flags low stock, the system creates a **PENDING** purchase order and an **invoice draft** (supplier, lines, qty, last unit price) stored on the PO notes. Nothing changes stock or prices automatically.

| Step | Actor | UI |
|------|-------|-----|
| Draft created | system (suggest only) | Owner sees **Needs you** on `restock`; Jack sees qty/supplier **without prices** |
| Owner approves | owner | PO → `APPROVED`; **Needs you** moves to placer (`restock_place`) per `restock_routing_mode` (`owner_approves` → owner places; `staples_self` → Jack; `flag_office` → accountant) |
| Place order | placer | `POST /store/restock/ordered`; others see **Waiting on &lt;name&gt;** |

Routing is read from Jack questionnaire → `Restaurant.restock_routing_mode`. Tests: `backend/tests/test_restock_workflow.py`.

## Scheduled owner reports

| Job | Cron (UTC) | Local | Output |
|-----|------------|-------|--------|
| Daily store report | 18:00 | 21:00 EAT | `Notification` + row in Settings › Reports list (`reports_past` in owner prefs JSON) |
| Weekly summary | Mon 05:00 | Mon 08:00 EAT | same |
| Monthly P&L | 1st 03:00 | 1st 06:00 EAT | same + export link |

Implementation: `backend/services/owner_reports.py`, registered in `main.py` APScheduler.

## Tests

- Backend: pytest per new router module under `backend/tests/test_eleven_v11_*.py`, plus `test_owner_reports.py`, `test_restock_workflow.py`.
- Frontend: vitest for formatters; Playwright `ui-broken-sweep` clicks in-page buttons (not only nav).
- Captures: 390×844, `serviceWorkers: block`, **PIN unlock after login** (`SEED_OWNER_PIN`), wait for page chrome before screenshot; files `v11-{empty|data}-{page}.png` for Home, Money (top, full P&L, Dishes, bills, supplier trends), Stock (top, Suppliers, Prep), More, Team (`/eleven/more/team`), Settings›Reports, Ask OS.

---

## Rollout (build order)

1. Nav + Ask OS FAB + shared chart primitives (`OwnerChart`, `ChartEmpty`).
2. Home API + page.
3. Money API batch + hub + detail routes.
4. Stock hub + suppliers + prep.
5. More/Team/Help; Settings/Reports/notifications/targets.
6. Seed extension; tests; sweep; screenshots.

Branch: `feat/jack-storekeeper` (auto-deploy test Railway).