# Eleven onboarding plan, from Wed 21 Oct 2026

**Who does what.** Mbuguss is on site with Eleven. Claude does the building and the system work. Eleven's people give one short session per role, never a whole day. The rule behind the schedule: **one thing per day at the restaurant, and never on a Friday or Saturday night** (their busiest; nobody learns a new screen during a rush).

The guide promised Eleven a first week that meets one area a day (Fig 9.11), and recipes written with the kitchen during setup (Fig 3.9). This plan delivers exactly that, in that order.

## Before anything else (Tue 20 Oct, today, Claude)

- [x] PR #24 CI made green (audits fixed, test hang guarded), docs for the new Railway account.
- [x] Branch picker on the owner screens, so both of Eleven's branches are reachable.
- [ ] New Railway account: as soon as access and the secret values arrive (`docs/v2/RAILWAY.md`).
- [ ] Rename the public URL away from `vibandavillage` (needs the Vercel account that owns it).

## Week 1: kickoff, the data in, the recipes

| Day | At Eleven (Mbuguss) | Who at Eleven, how long | Claude, same day |
|---|---|---|---|
| **Wed 21** Kickoff and payment | Sign, payment. Walk the owner through what the first two weeks look like (this page). **Collect**: (1) the till's make and version, and who has admin access; (2) one real M-Pesa business statement export; (3) last month's P&L from the accountant; (4) menu and prices *per branch*; (5) supplier list; (6) staff list with roles per branch; (7) licences with expiry dates; (8) recurring bills (rent, KPLC, water, security, internet) | Owner, 1–1.5 h | Production up on the new Railway account; Eleven's tenant and **both branches** created; owner login sent |
| **Thu 22** Remote, no visit | Answer Claude's questions from yesterday's material | Owner, 15 min on the phone | Menu, prices, suppliers, bills, licences and expense categories loaded for both branches. **Till feasibility test**: can its sales be read (API, export or database)? Real M-Pesa export run through the parser; anything it cannot read gets fixed |
| **Fri 23** Branch A: recipes | Recipe session for the **top 15 dishes** (they carry about 80% of sales): ingredient, quantity per plate, and how much is lost in trimming. Opening count of the expensive items only (beef, chicken, spirits) | Head chef 1.5 h (before lunch service); storekeeper 30 min | Recipes entered; dish costs and margins visible. Yield column built if the chef gives trim figures (see Build list) |
| **Sat 24 – Sun 25** | **No visit.** Busiest days; the till feeds in by itself if connected | — | Watch the first weekend of real sales: anything not read, any number wrong |

## Week 2: the second branch, then the people

| Day | At Eleven | Who, how long | Claude |
|---|---|---|---|
| **Mon 26** Branch B: recipes | Same recipes; only the *differences* at branch B (portion, supplier, price). Opening count of the expensive items | Branch B chef 45 min; storekeeper 30 min | Branch B costs live; first branch comparison (food cost side by side) ready to show |
| **Tue 27** Storekeepers | Receive a delivery, send stock to the kitchen, count, on their phones | Each storekeeper 20 min, at a quiet hour | Fix whatever they trip on, the same day |
| **Wed 28** Managers | Close a shift (count the drawer), log an expense | Each manager 20 min | Same |
| **Thu 29** Owner's first week starts | Home day 1: today's sales and the money match. Show "Your targets" and set them together (food cost, margin floor, cash tolerance) | Owner 30 min | One new Home area per day from here (Fig 9.11) |
| **Fri 30** Accountant | Map their P&L lines to LEVIII's; walk the export | Accountant 30 min (remote is fine) | Categories adjusted to match their chart |
| **Sat 31** Month end | No visit | — | **First monthly P&L**, labelled "as entered" (costs only from the 21st) |

## Weeks 3–4: settle and learn

- **Mon 2 Nov**: first weekly report reviewed with the owner (30 min). From now on, one visit a week.
- **Around Wed 4 Nov** (14 days of sales): price ideas switch on (Fig 5.3). Look at the first ones together; nothing changes in the till unless the owner says so.
- **Around Fri 20 Nov** (30 days): every engine out of "learning". A review meeting covering what LEVIII found and what it is worth in KES. This is the moment that justifies the payment.

**A shortcut worth asking for on day 1.** If the till can export **past** sales (the last 60–90 days), loading them makes the learning period nearly vanish: dish ranking, the forecast and price ideas work from week 1 instead of week 3.

## Build list for Claude, in the order the days above need it

| # | What | Needed by | Why |
|---|---|---|---|
| 1 | **Door 1 for Eleven's till** (connector, export import, or a daily file) | Thu 22 to start, before Sat 24 ideally | Fig 1.1 promises "nobody types anything"; everything else depends on it. Effort unknown until the till is known |
| 2 | **Expense entry screen** (manager, phone-first: category, amount, paid by, photo optional) | Wed 28 | Fig 1.3; the API exists, the screen does not |
| 3 | **Yield on recipe lines** (and buying-unit → counting-unit) | Fri 23 for yield; Tue 27 for units | Fig 3.10. Without yield, normal trimming shows as missing stock: false alarms against the cooks |
| 4 | Close-shift and receive-delivery screens made phone-first, with invoice photo | Tue 27 / Wed 28 | Fig 1.3; today's versions are the older manager screens |
| 5 | Health tiles to the guide's rules (profit vs costs covered; KES for stock and cash; next licence expiry) | Thu 29 (owner's Home day 1) | Fig 9.3 |
| 6 | Delivery price ideas worded as "a delivery price" and not as a raise | Thu 29 | Fig 5.5 promises ≤15% raises; the demo shows +146% "raises" |
| 7 | Shift report with every signal per shift | week 3 | Fig 6.4 |
| 8 | Prep planner, market list and combo checker as screens | week 3–4 | Figs 6.6, 6.9; the maths is already tested |
| 9 | Chapter 8 items (price ladder, menu trimming, ABC count calendar, learned sensitivity, price lists by branch or channel) | after day 30 | Roadmap. Say so if asked |

## Open questions only Mbuguss or Eleven can answer

1. Which till (POS) does Eleven use at each branch, and can it export sales?
2. What are the branches called, and where are they? (Eleven's own names replace "Westlands" and "Kasarani".)
3. Who is the accountant, and can they give 30 minutes remotely?
4. Is the demo shown to Eleven again before go-live? If so, items 6 and the URL rename come first.
