> Historical audit dated 20 October. The 23 October follow-through implements the missing screens and Chapter 8 workflows listed below. Use [ELEVEN_ACCEPTANCE.md](ELEVEN_ACCEPTANCE.md) for current status, tested connections and real-data boundaries. The older ❌/🟡 entries are preserved as the original audit, not current claims.

# "Eleven on LEVIII" against the code and the demo

The guide sent to Eleven (48 pages, 67 figures, 15 Oct 2026) checked claim by claim against this branch (`ccr-fc67b65b-k9czx3`) on 20 Oct 2026. Evidence comes from reading the code, running the tests, and building the demo with the real generator (`backend/demo/generator.py`, both branches, every planted scenario) and composing each branch's Home through the owner API.

**Legend**
- ✅ **Built, and the demo shows it.**
- 🟡 **Partly true.** Built differently from the picture, or built in code but on no screen.
- ❌ **Not built.** The guide describes it as something Eleven gets.
- 🔧 **Depends on Eleven's setup** (their till, their recipes, their statement).

The guide says "every figure uses example numbers", which covers the *numbers*. It does not cover *features*: where a figure shows a screen or a check, the reader will take it as something that exists.

## The short answer

- **Most of the guide is true and demonstrable.** Profit & Loss, the cash check, the M-Pesa match, missing stock and handovers, dish ranking, price ideas, the four leaks, costs covered, bill radar, cost spikes, Ask LEVIII's five forms, four reports, accountant export, alert levels, the honesty labels, the guided first week. All are built, all are tested, and all run on the demo for both branches.
- **Both branches are real in the demo.** Westlands and Kasarani are separate restaurants with their own sales, staff, stock and cash. The comparison in Fig 8.7 comes out of the engines almost exactly: ingredients are **29.2%** at Westlands and **36.9%** at Kasarani, against the guide's 29% and 37%. Until today the owner could not *see* Kasarani on Home; a branch picker was added on 20 Oct (see Fixed today).
- **Five things are presented as existing and are not.**
  1. The staff entry screens of Fig 1.3, the biggest one. There is no screen for logging an expense, and no invoice photo.
  2. Yield and buying-unit conversion (Fig 3.10).
  3. The shift report with every signal in one row (Fig 6.4).
  4. Prep planner and market list, and combo pricing, as screens (Figs 6.6, 6.9).
  5. The health strip's rules (Fig 9.3): the tiles exist but measure different things.
- **Chapter 8 ("Smarter every month") is mostly roadmap.** Learned price sensitivity, the price ladder, menu trimming, ABC count scheduling, and prices by branch or channel are not built. Read as "what comes with time", it is honest; read as features, it is not.
- **Door 1 is only true if Eleven's till can be read.** The only till connector that exists is for MacSoft (Vibanda's). Which till Eleven runs is the single most important unknown.

## Fixed today (20 Oct)

| What | Change | Proof |
|---|---|---|
| The owner could not reach the second branch on Home, Reports or areas; only Ask "compare my branches" showed it | A **Branch** picker in the owner header (`components/owner/BranchPicker.tsx`). The backend already scoped every owner endpoint to the chosen branch. | vitest `owner-branches.test.tsx` (4); E6 "both branches: the owner picks Kasarani and Home is Kasarani's" at 390 px and 1440 px |

## Figure by figure

### Start here and chapter 1: where numbers come from

| Fig | Claim | Status | Evidence / gap |
|---|---|---|---|
| A | Three doors → one store → engines → five surfaces | ✅ | `owner/registry.py` lists 23 engines; E5 proves each is on Home, in Ask and in a report |
| B | One KES 1,200 sale flows to sales, stock, money, cash, M-Pesa, reports, dishes, monthly P&L | ✅ / 🔧 | Each step exists. The "12:44, read automatically" timing needs a till connector for Eleven's POS |
| 1.1 | Door 1: till read automatically every few minutes | 🔧 | Only the MacSoft mirror exists (`backend/integration/`). Eleven's till is unknown |
| 1.1 | Door 2: team enters on their own screens | 🟡 | Old manager screens exist (inventory, purchasing, kitchen stock with handovers). See 1.3 |
| 1.1 | Door 3: M-Pesa statement upload | ✅ / 🔧 | Built and tested (`parsers/mpesa_csv.py`). Written without a real Safaricom export, so one is needed before trusting it |
| 1.2 | Screens say which costs are missing | ✅ | `as_entered` state plus the "how complete your costs are" block |
| 1.3 | Storekeeper: receive delivery, ordered vs received, **invoice photo** | 🟡 | Receive against a PO exists (`PurchasingWorkspace`); **no invoice photo** |
| 1.3 | Manager: end-of-shift cash count | 🟡 | Drawer counts exist in the data model and engines; the phone-first close-shift screen in the picture is not built |
| 1.3 | Manager: **log an expense** (gas 4,500, paid by petty cash) | ❌ | API exists (`/owner/money/expenses`); **no screen**. The demo's expenses are generated |
| 1.3 | Accountant: export the month | ✅ | Monthly report → XLSX/PDF (`owner/money/export.py`) |

### Chapter 2: Profit & Loss

| Fig | Claim | Status | Evidence / gap |
|---|---|---|---|
| 2.1 | P&L lines; delivery net of commission | ✅ | `owner/money/pnl.py`. Commission is a cost line under fees rather than netted off revenue; the totals agree (documented deviation) |
| 2.2–2.3 | Waterfall, KES-100 split, three formulas | ✅ | E2 golden #1, to the cent |
| 2.4 | Dials against the owner's targets | ✅ | `cost_dials` block; settings `food_cost_target_pct`, `prime_cost_target_pct` |
| 2.5–2.6 | Price rise, line by line | ✅ | E2 golden #2 |

### Chapter 3: store & kitchen

| Fig | Claim | Status | Evidence / gap |
|---|---|---|---|
| 3.1 | Missing stock with item and zone | ✅ | Demo: beef 2.5 kg, KES 8,705 a month (P5) |
| 3.1 | Reorder point and draft PO to approve | ✅ | `reorder` block; inventory predictor |
| 3.1 | **Waste % per item**, items at risk | 🟡 | Spoilage risk scores exist; a waste-% per item on the owner screen does not |
| 3.1 | Short deliveries, price trend, on-time % | 🟡 | Short deliveries ✅ (P13, Kenchic 9.3 of 10 kg); on-time % ✅; **supplier price trend ❌** |
| 3.1 | Cost and margin per dish | ✅ | Profit engine, `dishes_by_kes` |
| 3.1 | **Stock value in KES, slow movers** | ❌ | No stock valuation on any owner screen |
| 3.2–3.4 | Six leak points; variance formula, 3% flag | ✅ | `ai/stock_custody.py`, setting `missing_stock_flag_pct` 3 |
| 3.5–3.7 | Custody zones, handover disputes, three cases | ✅ | Demo P6: store 4.0 kg, kitchen 3.8 kg on 18 Oct |
| 3.8 | "Check this zone", never "someone stole" | ✅ | Wording rule held in code and copy |
| 3.9 | Recipes unlock the checks; written with the kitchen at setup | ✅ / 🔧 | Engines need recipes. Writing them is onboarding work |
| 3.10 | **Buying unit → counting unit** (crate × 24) | ❌ | No unit conversion in the model |
| 3.10 | **Yield** (1 kg raw → 0.8 kg cooked) | ❌ | No yield on recipes; only a helper function `owner/kitchen.py` used by tests. Without it, normal trim shows as a kitchen gap, which is the false alarm the guide promises to avoid |
| 3.10 | Bar: spirits in tenths, beer by bottle | 🟡 | The demo counts its spirit in tenths (a note on the count); no tenths-aware counting screen |
| 3.11 | Phone entry at the shelf, pick from lists | 🟡 | See 1.3; P7 design note only |

### Chapter 4: cash check

| Fig | Claim | Status | Evidence / gap |
|---|---|---|---|
| 4.1 | Card and delivery payouts settle later, minus commission | 🟡 | Explanatory only; no card or platform settlement matching. That is fine if it is not claimed as a check |
| 4.2–4.3 | Three-way match catches cash recorded as M-Pesa | ✅ | Cash check plus M-Pesa match; demo P8, 3 sales (KES 3,120) not on the statement |
| 4.4 | Tolerance max(KES 200, 1%), 520 short on 35,000 flagged | ✅ | E2 golden #8; settings |
| 4.5 | Void signals | ✅ | Fraud engine, "cancelled sales" block |
| 4.6 | Four outcomes incl. combined payment | ✅ | `owner/mpesa_match.py` (receipt, exact, grouped, split). Demo: 2 pairs paid with one payment |
| — | Cash and M-Pesa alerts to the owner only | ✅ | S5.3 alert levels |

### Chapter 5: suggestions

| Fig | Claim | Status | Evidence / gap |
|---|---|---|---|
| 5.1–5.2 | Engines need recipes and history; one ranked list | ✅ | `costing_you_money` |
| 5.3 | Learning state, day n of 30 | ✅ | `owner/states.py` (`LEARNING_DAYS = 30`) |
| 5.4 | Four groups, 70% cut-off, plain names | ✅ | Menu engine; demo P11 |
| 5.5 | Price idea tree, floor 40, raise ≤15% at ≥1.3× for ≥14 days, offer at ≤0.6× with margin ≥55% | ✅ | `ai/pricing/analysis.py` |
| 5.6 | Weights 45/25/15/15, score 82.5 | ✅ / 🟡 | Weights ✅. 82.5 cannot happen: risk 0.8 is not a level the code produces (it scores 81.75). Illustrative, but say so |
| 5.7 | Six settings the owner can change | ✅ | All six in `owner/settings.py`, editable with a live preview |

### Chapter 6: more from the same numbers

| Fig | Claim | Status | Evidence / gap |
|---|---|---|---|
| 6.1 | Costs-covered clock | ✅ | E2 golden #9 |
| 6.2 | Bill radar | ✅ | Demo P10: rent KES 70,000 due in 3 days |
| 6.3 | Cost spike | ✅ | Demo P9: gas 18,600 against a usual 14,333 |
| 6.4 | **Shift report: cash, M-Pesa, cancelled, stock gap per shift** | 🟡 | Per-shift cash table ✅; M-Pesa, cancelled and stock gap are not lined up per shift |
| 6.5 | Recurring patterns grid | ✅ | Demo P7: Tuesday-evening cash short 4 of 4 times |
| 6.6 | **Star–Puzzle combo, priced** | 🟡 | Maths ✅ (golden #10); on no screen |
| 6.7 | Forecast band, unusual day | ✅ | `forecast` block |
| 6.8 | Why was Tuesday bad (holiday, stock-out, staff, voids) | ✅ | `owner/answer_why.py`; demo P12 |
| 6.9 | **Prep planner and market list** | 🟡 | Maths ✅ (goldens #11, #12); on no screen |

### Chapter 7: leaks

| Fig | Claim | Status | Evidence / gap |
|---|---|---|---|
| 7.1 | Quarter chicken to the floor, 435, KES 10,500 a month at 300 plates | ✅ | Golden #3; demo card "Reprice Quarter chicken to KES 435" |
| 7.2 | Chips 270 vs 300 | ✅ | Demo P2 |
| 7.3 | Burger on Glovo keeps 170 vs 320 | ✅ | Demo P3 |
| 7.4 | Weak hours | ✅ | Demo P4: afternoon the weakest on every date tested |

### Chapter 8: smarter every month (read as roadmap)

| Fig | Claim | Status | Evidence / gap |
|---|---|---|---|
| 8.1 | Prices by branch, channel, daypart | ❌ | Engines *suggest* channel prices; there are no stored price lists by branch or channel |
| 8.2 | Learned price sensitivity per dish | 🟡 | Approved price changes are followed up at day 7 and day 14 (revenue checked); no per-dish learned sensitivity replaces −0.7 |
| 8.3 | Rank by KES | ✅ | `dishes_by_kes`, decisions ranked by KES |
| 8.4 | Price ladder gap | ❌ | |
| 8.5 | Menu trimming, long tail | ❌ | |
| 8.6 | ABC count schedule | 🟡 | ABC classes are computed (`inventory_predictor`); no count calendar |
| 8.7 | Branches side by side | ✅ | Ask "compare my branches": food cost, wages, sales, KES-a-month gap. Discounts, cash and stock gaps side by side ❌ |

### Chapter 9: screens

| Fig | Claim | Status | Evidence / gap |
|---|---|---|---|
| 9.1 | Five surfaces, every engine placed | ✅ | E5 |
| 9.2 | Home zones 1–4 | ✅ | E6 (33 browser tests) |
| 9.2 | Zone 5, "LEVIII's read" | 🟡 | Built and grounded, **switched off** on Home (PROGRESS open item 8). The guide marks it optional, which is true |
| 9.3 | **Health strip rules** | 🟡 | Six tiles exist, but Money shows food cost % (guide: profit this week vs costs covered); Stock and Cash show *counts* (guide: KES); Compliance shows "dishes with a cost" (guide: next licence expiry, red under 14 days) |
| 9.4 | Card: sentence, KES, action, Why? | ✅ | |
| 9.5 | Six honesty labels | ✅ | `owner/states.py` |
| 9.6 | Ask: five forms; an unbacked number is deleted | ✅ | E3 grounding eval |
| 9.7–9.8 | Four reports; monthly P&L and accountant XLSX | ✅ | S5.2, S3.4 |
| 9.8 | "Price changes: pilau +50 → +KES 6,100" | 🟡 | "What LEVIII saved you" exists; a per-change result line in the monthly report is not built |
| 9.9 | Rationed alerts: max 5 a day, quiet hours, cash & fraud to owner only | ✅ | Settings `urgent_alerts_per_day` 5, quiet hours 22–7 |
| 9.10 | Each person gets their own screen | 🟡 | See 1.3 |
| 9.11 | First week, one area a day | ✅ | `FirstWeek.tsx` |
| 9.12 | Plain words | ✅ | SPEC §3.4 vocabulary |

## Things in the demo that would undercut the guide

- **Delivery price suggestions ignore the 15% raise cap the guide promises (Fig 5.5).** Kasarani's Home lists "Raise Quarter chicken on Uber Eats to KES 985 (from KES 400)", and Westlands' lists "Raise Burger on Glovo to KES 800 (from KES 600)". The maths is right (the price that keeps the 40% floor after a 25% commission), but it is labelled a *raise*. Fig 7.3 frames it as "a separate delivery price, or keep the dish off delivery". Changing the wording and framing is small; the decision is yours.
- **The first branch is named "Demo Restaurant", not "Westlands".** The picker shows "Demo Restaurant · Westlands" and "Demo Restaurant – Kasarani". This is acceptable in a demo; Eleven's branches will carry their own names.
- **The public frontend URL is `vibandavillage.vercel.app`, another client's name,** and Eleven will see it. It is not in the Vercel team this session can reach (that team's only project serves `restaurant-agent-seven.vercel.app`).
