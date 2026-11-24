# Engine review — restaurant-agent

**Repo:** `/workspace/ra-r`  
**Branch:** `feat/jack-storekeeper`  
**HEAD:** `c4d235d` (theme: remove vertical ribs)  
**Date:** 25 Nov 2026, Africa/Nairobi  
**Scope:** read-only. No repo files were edited, committed, or pushed. Secrets were not printed.

The codebase follows the stated split: **Layer 3 math is deterministic Python over the DB; the LLM may only narrate or word evidence it was given** (`CLAUDE.md`, `directives/011_ai_infrastructure_understanding.md`, `directives/014_business_intelligence_roadmap.md`). That design is mostly honoured in the engine modules themselves. The gap is not "the LLM invents money figures inside the engines." The gap is that **many engines are disconnected from the Eleven screens**, **key numbers are hardcoded or never rolled up from recipes**, and **Ask OS talks to the old analytics layer rather than the store/handover/approvals data the owner actually uses**.

Architecture note: `backend/routers/analytics.py`, `inventory.py`, `stock_custody.py`, `orders.py`, and `attendance.py` are **not in this tree**. `main.py` mounts only the Eleven/store routers plus `/api/v1/ai` (Ask OS) and `/api/v1/overview`. The old `/ai/dashboard`, `/ai/menu-engineering`, `/ai/revenue-forecast`, `/ai/inventory-predictions` HTTP surfaces described in directive 011 are gone.

---

## 1. Summary table

| Engine | Type | Connected? | Screen | Data needed | Issues |
|---|---|---|---|---|---|
| Inventory predictor `ai/inventory_predictor.py` | Deterministic | Partial — Ask OS + ops/WhatsApp, not Eleven Stock | Ask (`/eleven/ask`) only | Stock movements, `cost_per_unit`, `expiry_days` | Hardcodes lead time = 2 days (ignores `Supplier.avg_lead_days`). Ignores `par_level`. Ask OS reads `days_until_stockout` but the engine returns `days_until_depletion` — "run out within a week" path never fires. Usage is diluted over a fixed 30 days (new items look slower than they are). EOQ uses a hardcoded KES 500 order cost and 25% holding cost. No dedicated tests. |
| Par-level reorder `ai/reorder.py` | Deterministic | Scheduler yes (06:00 EAT drafts POs); Eleven approvals **no** | Push/WhatsApp only, not `/store/approvals` restock cards | `par_level`, `low_stock_threshold` (used as ROP), `default_supplier_id`, holiday signals | ROP is a stored threshold, not computed from usage × lead time. Will silently draft nothing until par + default supplier are set — onboarding does not collect either. Two disconnected restock paths (auto-PO vs Jack's restock request). Tests exist for tiered PO approval, not for the Eleven feed hookup. |
| Recipe deduction `ai/order_stock.py` | Deterministic | **Dead** — zero callers | None | `MenuIngredient` recipes + POS order lines | Never called from webhooks, intake, or any router. Also ignores `yield_fraction` (deducts `qty * quantity_per_serving` only). The missing link for "plates used vs stock handed over." |
| Stock custody / variance `ai/stock_custody.py` | Deterministic | Scheduler only (21:00 EAT). HTTP router removed | No Eleven screen | Recipes + POS dish lines + `StockMovement` OUT | Theoretical usage also ignores `yield_fraction`. 3% flag threshold is generic and reasonable. Cannot run usefully until Sam's receipts list dishes **and** `order_stock` is wired (or movements are recorded another way). |
| Menu engineering `ai/menu_engineer.py` | Deterministic | Ask OS + ops_manager + tests | Ask only | 30 days of `OrderItem` + `MenuItem.cost_price` | Uses stored `cost_price`, not recipe rollup. `store_recipes` creates dishes with `cost_price=0`, so every dish looks 100% margin / 0% food cost until someone keys a cost. Math is tested (`test_menu_engineering_math.py`). No Dishes/menu-review page in the Eleven app. |
| Revenue forecaster `ai/revenue_forecaster.py` | Deterministic (moving averages + weekly pattern, ±1σ band) | Ask OS, digital twin, learning loop | Ask only | Paid/non-cancelled orders | Fine as a baseline. No Money or Reports chart uses it. Useless until the till is live. |
| Pricing analysis + recommendations `ai/pricing/{analysis,recommendations}.py` | Deterministic | Ask OS, decisions adapters, tests | Ask only (invoice-prices is a different, photo flow) | `MenuItem.price` + `cost_price` + velocity | Same `cost_price=0` problem. Floor/margin rules are tested. LLM is not used to pick a price. |
| Profit / "P&L" `ai/profit/intelligence.py` | Deterministic | Ask OS + overview home specialists — **not** My Money | My Money (`/eleven/money`) does **not** call this | `OrderItem` + `cost_price`; bills live in a separate costs table | This is a **food-cost gross margin**, not a full P&L (rent, gas, salaries, approved bills are ignored). `_detect_portion_drift` is actually **POS price drift**, not portion-size drift. Money page only shows till status + approved bill names. |
| Labour intelligence `ai/labor/intelligence.py` | Deterministic | Ask OS only | Team pages use `services/labor_schedule.py` instead | `LaborShift` (written by the schedule service) + pay rates + sales | Connected data path exists if the weekly schedule and pay rates are filled. The engine itself is not shown on Team. Jack must not see `hourly_rate` / `labor_cost` — middleware scrubs those keys on `/store` for stockkeeper/accountant. |
| Labour schedule + shift sales `services/labor_schedule.py`, `shift_sales.py` | Deterministic | **Yes** | `/eleven/team`, `/store/team`, `/store/schedule` | Weekly templates, roster, optional POS sales for the shift | Well tested. Shared-shift sales policy still needs an owner decision (team total vs even split). |
| Cash reconciliation `ai/cash_reconciliation/intelligence.py` | Deterministic | Home specialists + fraud helper; no Eleven API | `/eleven/cash-check` does not call it | Cash `Order.total` vs a submitted drawer count | Tolerance KES 200 or 1% — reasonable. There is no screen for a manager to submit a drawer count, so the engine has nothing to flag. Honest about no bank feed. |
| Fraud detection `ai/fraud/detection.py` | Deterministic | Scheduler every 2h + home specialists | No Eleven screen | `OrderAudit` voids/refunds, M-Pesa receipts, order hours | Adaptive baselines with cold-start guards. Good design. Results do not appear on Alerts (Alerts reads the approvals feed). |
| Supply chain `ai/supply_chain/intelligence.py` | Deterministic | Used when drafting POs (reliability warning) | No supplier score on `/store/suppliers` | Purchase order history (`ordered_at` / `delivered_at`) | `Supplier.avg_lead_days` exists but is defaulted to 1 and **never collected** in Jack's supplier questions (name, brings, arrival only). Predictor still ignores this field. |
| KDS / kitchen times `ai/kds_intelligence.py` | Deterministic | Ask OS + specialists | None in Eleven | `PrepTime` rows | Eleven has no KDS and QuickSell is unlikely to send ticket times. Effectively idle. |
| Ops manager `ai/ops_manager.py` | Deterministic aggregator | Ask OS fallback | No `/ai/dashboard` | All of the above | 0–100 "health score" is a heuristic. Cached 120s. |
| Reservation optimizer `ai/reservation_optimizer.py` | Deterministic | Ask OS + specialists | None | Reservations / tables | Not an Eleven workflow. |
| Decisions ranking `ai/decisions/*` | Deterministic | Overview `/overview/today` only | Eleven Home uses `/store/approvals`, not this | Downstream engines | Built and tested, not shown to the owner. |
| Simulation + digital twin `ai/simulation/*` | Deterministic | `demand_signals` used by reorder; twin/simulate HTTP gone | None | Forecast + holiday calendar | Signals are the useful part (KE holidays / school terms). Weather/sports are stubs. |
| Knowledge graph `ai/graph/*` | Deterministic | Tests only | None | Recipe links | Dead in product. |
| Workflows `ai/workflows/*` | Deterministic | Tests + some event hooks; no `/ai/workflows` router | None | Templates, human approval steps | Orphaned HTTP surface. |
| Strategist `ai/orchestrator/strategist.py` | Hybrid (LLM tool-loop over deterministic tools, grounded + metered) | Monday 08:00 EAT job if `autonomous_strategist` flag is on | No `/ai/strategy` page | All engines as read-only tools | HTTP surface removed. Flag default off. Fallback is deterministic when no provider. |
| Executive / push notifier / escalation / notify | Deterministic (event + cron) | Scheduler + in-app notifications | Notification bell | Events | Live. WhatsApp briefing also scheduled — only useful if Twilio/WhatsApp is configured. |
| Evaluation / learning / ROI / cost_model / spend_cap | Deterministic | Learning cron 05:00 EAT; spend cap on LLM calls | No AI-ops page | Token usage, forecasts vs actuals | Spend cap default $20/day/tenant; 429 is caught by Ask OS and falls back. |
| Marketing, plugins, enterprise, memory | Deterministic | Tests / unused HTTP | None | Various | Marketplace/plugins deliberately not for untrusted code. Dead in the Eleven product. |
| Data quality `ai/data_quality.py` | Deterministic | WhatsApp brain only | None | Mixed | Idle if WhatsApp is off. |
| Creative layer `ai/creative.py` + owner narrative | LLM (wording only; sentence-level grounding) | Ask OS when `FEATURE_CREATIVE_LAYER` / `ai_narration` on | Ask | Evidence JSON from engines | Design is correct: numbers must already be in evidence. Default creative layer is off. Cache + cooldown on provider failure. |
| Store photo check `store_vision.py` | Hybrid (OpenRouter vision + grounding) | Yes — deliveries, invoices, handovers, stock photos | Store intake / handover / invoice-prices | Photo + keyed figures | Ungrounded numbers are stripped. Match is refused if the model invents a figure. Fail-open if the key has no credit (check is skipped / pending — must not block the handover). |
| Approval workflow `services/approval_workflow.py` | Deterministic | **Yes** | Owner Home, Approvals, Alerts; reminders every 5 min | The store request | Actor is still almost always "owner". Restock requester notify needs `ordered_by` (known leftover). Team rules still owner-only. |
| Ask OS `routers/ai_ask.py` + `/eleven/ask` | Hybrid | **Yes** (owner only) | `/eleven/ask` | Whatever the routed engine needs | See §3. Grounds in **old engines**, not store/approvals/handover/invoice records. Suggested questions on the page therefore cannot be answered well. |

**Counts (product engines, not tiny helpers):** ~28 deterministic, 3 LLM-only narration modules (creative, owner_narrative, narrator), 4 hybrid (Ask OS, strategist, store vision, WhatsApp orchestrator). Helpers: analysis_clock, pii_scrub, grounding, llm_client, cost_model, spend_cap, memory, routing policy.

**Truly uncalled:** `order_stock.deduct_ingredients_for_order` / `reverse_ingredients_for_order`.

**Built but not shown on any Eleven screen:** profit P&L, menu engineering, pricing recs, inventory predictor, forecast, labour intelligence, cash recon, fraud report, stock variance, decisions stream, simulation, twin, graph, workflows, strategist, ops dashboard, KDS, reservations.

---

## 2. Numbers vs the LLM

The engines that produce money, stock, cost, or forecast figures are pure Python. I found **no case** where an LLM writes a cost, price, stock qty, or P&L number into the database.

Risks that remain:

1. **Ask OS narration** can only keep sentences whose figures appear in the evidence (or, in creative mode, in the owner's own words). If evidence is wrong (field-name bug, `cost_price=0`), the wording will confidently repeat the wrong number.
2. **Vision** is allowed to read a photo, then grounding strips any number not in the photo-read or the keyed fields. This is the right pattern.
3. **Jack and kitchen never see money** via `money_visibility` middleware (`MONEY_KEYS` scrubbed on `/store`). Ask OS is `require_staff_role()` with an empty allow-list, so only ADMIN/SUPERADMIN pass — Jack gets 403. The Ask page is behind `OwnerShell`. Good.
4. Caveats on the scrub list: free-text fields (`sentence`, `answer_text`, `notes`, `finding`) are not key-scrubbed. Jack cannot hit Ask OS, but a future "Ask" for managers must keep the same block. `"amount"` and `"value_kes"` are not in `MONEY_KEYS` (`value_cents` and `amount_cents` are). `eleven_owner.owner_summary` returns `revenue_kes` / `value_kes` — not currently used by My Money, and that endpoint is owner-only anyway.

**Bug in `eleven_owner.py` (if that summary is ever wired):** `stock_value_cents` is computed from `cost_per_unit` which is already KES, then divided by 100 again — stock value would show 100× too small.

---

## 3. Ask OS

Path: owner types on `/eleven/ask` → `POST /api/v1/ai/chat`.

How it grounds:

1. Keyword router picks a module (stock, revenue, bookings, kitchen, staff, pricing, menu, profit, else ops). Deterministic, tested (`test_os_question_routing.py`).
2. The handler **calls the matching deterministic engine** and builds a finding card from its output. The LLM does not choose tools.
3. If `ai_narration` is on and a provider key exists, `owner_narrative` rewrites the card. Grounding (`verify` / `keep_grounded_sentences`) drops unbacked figures. If the rewrite fails, the deterministic card (or a "needs data" sentence) is shown.
4. `narrative_allowed=False` blocks narration for precise threshold answers (so the model cannot invent a stockout date from a par threshold).

**Failure when OpenRouter has no credit / key missing:** `llm_client.is_available()` is false when no key is set (no call). Provider errors and the daily spend cap (HTTP 429) are caught; `llm_reply` becomes null; the UI falls back to the grounded card or a plain "I can't verify this from restaurant records" message. The page will not crash. Tokens are metered to `token_usage` when a call succeeds. Chat is rate-limited 10/minute.

**Gaps:**

- Suggested starters ("Which bills are waiting on me?", "delivery photo mismatches", "stock moves this week") do **not** query approvals, vision checks, or stock movements. "Bills" has no routing keyword and falls through to ops.
- `_answer_stock` looks for `days_until_stockout` / `item_name`; predictor emits `days_until_depletion` / `name`. Weekly stockout wording is dead.
- Analysis is still gated on `source_is_trusted` for non-direct tenants. Eleven **is** in `DIRECT_SOURCE_TENANTS`, so that gate is correctly skipped for this client.
- The page still shows a "Written by AI" line, which breaks the "never show engine names / AI" product rule.

---

## 4. Data that is missing (and what that blocks)

| Data | Status in this branch | Blocked engines |
|---|---|---|
| POS dish lines (item + qty on each receipt) | Waiting on Sam / QuickSell webhook (end of November). Till tickets alone are not enough | Recipe deduction, plate counts, custody variance, true dish cost vs sales, menu engineering, portion checks |
| Recipe lines | Storekeeper can enter them (`/store/recipes`) after account setup | Needed for almost everything above. Coverage is not shown to the owner |
| Dish cost rollup | **Not implemented.** New dishes get `cost_price=0`. Invoice prices update stock item cost, not the dish | Profit, pricing, menu engineering, "what a plate costs" |
| `par_level` + `default_supplier_id` | Columns exist; import can set par; onboarding does not ask | Auto reorder drafts nothing |
| `Supplier.avg_lead_days` and phone | Column defaults to 1; supplier question does not collect days or phone | Lead-time ROP, WhatsApp order draft |
| Opening/closing + handover + invoice photos | Flows exist on the store app | Ready for Jack; owner reviews in the feed |
| Running costs / bills | Flows exist; accountant/Jack can enter; owner approves | Ready to sit in a real P&L — but profit engine does not include them |
| Drawer counts, KDS ticket times, reservations | Models exist; no Eleven workflow | Cash recon, KDS, reservation optimizer stay idle |
| Yield / buying unit | Fields exist on items and recipe lines | Not used in deduction or variance |

---

## 5. Tests run

Command (Africa/Nairobi): `/workspace/ra-venv/bin/python -m pytest` in `backend/`, ignoring `test_owner_postgres.py` and `test_pos_inbox_postgres.py` (need a live Postgres).

**Result: 633 passed, 1 skipped, in 2 min 18 s.** No failures.

Coverage of engines is uneven: menu math, pricing floors, Ask routing, grounding, spend cap, approvals, labour schedule, simulation, twin, graph, workflows, and stock-alert copy are tested. There is **no** unit test that `inventory_predictor` lead time comes from the supplier, or that `order_stock` is invoked on a POS ingest, or that a drafted PO appears in `/store/approvals`.

---

## 6. Prioritised fix list

1. **Wire recipe costing.** After each recipe save (and after an invoice updates an ingredient cost), recompute `MenuItem.cost_price` = sum(raw qty / yield × ingredient cost). All profit, pricing, and menu figures then become real. Show the plate cost on an owner Dishes page, never to Jack.
2. **Call `order_stock` from the POS webhook** (and reverse on a void before the food is made) once dish lines exist. Honour `yield_fraction`. Until then, show "plate check waiting on the till" rather than a fake variance.
3. **One reorder path.** Compute ROP as recent daily use × (`Supplier.avg_lead_days` + safety days), order qty = par − on hand (or a max qty if that is how they order). Draft goes onto the **same** approvals feed the owner already uses, routed to whoever the ordering-mode answer names. Stop hardcoding 2-day lead time in the predictor. Fix the `days_until_depletion` / `days_until_stockout` mismatch.
4. **Put a real P&L on My Money.** Sales (when the till is live) − recipe food cost − approved bills (rent, gas, pay, etc.). Use only approved amounts; unknown bills stay in "Still unknown." Do not show this to Jack.
5. **Show custody and fraud flags on Alerts**, with the wording "needs a look, not proof of theft." Needs recipes + dish lines first.
6. **Point Ask OS at Eleven records** (approvals, deliveries, vision mismatches, handovers, bills) as tools, and keep the old engines only for questions they can actually answer. Remove the "Written by AI" label.
7. **Collect the missing onboarding answers** (see §9) so par, lead time, ordering mode, handover times, and who approves are configuration, not code forks.
8. **Add tests** for (1)–(3) and for "Jack cannot open `/api/v1/ai/chat` or see cost fields."
9. Later / lower: wire cash drawer count at close; include approved labour cost in P&L; retire or hide dead reservation/KDS/simulation surfaces; fix `owner_summary` 100× stock-value bug if that endpoint is reused.

---

## 7. Rules to add

Principle: every rule is generic software. The trigger math is the same for every restaurant. Thresholds, who acts, and timing come from storekeeper (or owner) answers and stored item/supplier fields — not from an Eleven-only fork.

| # | Rule | Trigger | Who sees "needs you" | Everyone else | Data needed | Generic vs Eleven config |
|---|---|---|---|---|---|---|
| R1 | Reorder in time for delivery | On-hand ≤ (recent daily use × lead days + safety), or ≤ stated par / max qty | The person named in the ordering-mode answer (owner, storekeeper, or accountant) | "Waiting on X to order Y" | Usage, `avg_lead_days`, par or max qty, default supplier, open PO | Generic. Lead days, par/max, and who orders are onboarding + item setup |
| R2 | No second order while one is in flight | Existing PENDING/SENT PO for that item (already in `reorder.py`) | — | — | Purchase orders | Generic; already written, just not shown on the Eleven feed |
| R3 | Delivery photo vs invoice / counted qty | Vision mismatch, or counted qty ≠ invoice qty beyond a small tolerance | Owner (and accountant if they handle prices) | Store sees "waiting on owner" | Delivery photo, keyed qty, invoice photo | Generic. Tolerance can be a restaurant setting (default e.g. 2% or 1 unit) |
| R4 | Invoice price change | New unit cost differs from last stored cost by more than a set % | Accountant (prices) and owner (if margin on a dish will drop below the floor) | Jack never sees the money, only "price recorded" | Invoice line vs `cost_per_unit`; recipe rollup | Generic. Alert band (e.g. 10%) is a setting |
| R5 | Store → kitchen handover each service | At each configured handover time, no completed handover (photo + chef PIN) for that window | Storekeeper | Owner sees "Waiting on Jack" | Handover times from questions, photos, chef PIN | Generic. Times and whether a PIN is required are onboarding |
| R6 | Opening and closing photos | No opening photo after start-of-day; no close submitted at end-of-day | Storekeeper (open/close); owner (to accept the close) | "Waiting on Jack / owner" | Day-photo + close flows (already built) | Generic. Who closes is already asked (`closes_the_day`) |
| R7 | Spoilage / write-off needs a second person | Waste record saved | Owner (or the named approver) | Store sees "waiting for approval" | Waste photo + reason (already built) | Generic. Who approves can be an answer (today it is hardcoded owner) |
| R8 | Custody gap (theoretical vs actual) | After close, \|actual OUT − recipe use\| / recipe use > threshold (default 3%, already in `stock_custody`) | Owner | Jack sees only qty, not value | Recipes, POS dish lines, movements, yield | Generic. Threshold is a setting. Do not label it theft |
| R9 | Count vs book variance | Closing count vs (opening + deliveries − issues − waste) | Owner | Store sees the qty gap only | Opening, deliveries, issues, waste, close | Generic. Same "possible reasons" list: recipe, yield, unrecorded waste, count error, theft |
| R10 | Dish below margin floor | Recipe cost / selling price > food-cost ceiling (code already uses ~35% cost / 40% margin) after a cost update | Owner | Accountant may see the cost change; Jack does not | Recipe rollup + menu price | Generic industry floor; restaurant can set its own |
| R11 | Unknown or overdue bill | Running cost with no amount, or due date passed without approval | Owner (approve); accountant (complete the amount) if that is the policy | "Waiting on owner / accountant" | Costs flow already built | Generic. "Accountant may complete an unknown bill" is a known leftover |
| R12 | Labour vs sales for a shift | After till data exists: labour cost for the shift vs that shift's sales above a cap | Owner | Managers see headcount, not pay, if that is the rule | Schedule + pay rates + POS | Generic. Cap (e.g. 30%) is a setting. Jack never sees pay |
| R13 | Till / drawer mismatch | Drawer count vs cash sales (and float) beyond KES 200 or 1% (already coded) | Owner / manager on duty | — | Drawer count submitted at close + cash receipts | Generic. Needs a close-time count step |
| R14 | Unusual voids or missing M-Pesa receipt | Existing fraud patterns (spike vs own baseline, burst refunds, paid-with-no-receipt) | Owner | Never accuse a named waiter on a staff screen | `OrderAudit`, receipts | Generic. Wording: "needs a look," not "fraud" |
| R15 | Daily prep list | See §8. If tomorrow's prep qty is above what was handed over + still in the kitchen | Kitchen (prep list); storekeeper (issue shortfall) | Owner sees "Waiting on kitchen / store" | Recipes, recent sales, handover qty, par for mise en place | Generic. Prep window and which dishes are prepped ahead are onboarding |
| R16 | Supplier late vs promised lead time | `now > ordered_at + avg_lead_days` and not delivered (late-PO job already exists) | The person who orders (R1) | — | `avg_lead_days`, PO timestamps | Generic. Already scheduled; hook to the Eleven feed |

---

## 8. Prep

**How it should work (deterministic):**

1. For each dish that is prepped ahead (from an onboarding / recipe flag, not guessed), take recent same-weekday sales (or the last N services) as expected plates. If the till is not live yet, use a storekeeper/chef "usual plates" number entered once, and replace it when sales arrive.
2. Ingredient need = plates × (`quantity_per_serving` / `yield_fraction`), summed by stock item.
3. Subtract what is already in the kitchen (last handover that has not been used, plus any kitchen-zone count). The remainder is the **issue list** for the store.
4. Compare the issue list to store on-hand and to supplier lead time (if something must be bought, jump to R1).
5. Publish a dated prep list: dish, plates, each ingredient qty, whose turn it is. No LLM in the math. Optional later: a short plain-language note around the list.

**What exists today:**

- Recipe lines with `quantity_per_serving`, `yield_fraction`, `is_critical`, `recipe_unit`.
- Buying unit / `units_per_buy` / item-level yield on `InventoryItem`.
- Kitchen handover with photo + chef PIN, spoilage, day close.
- Menu item `avg_prep_minutes` and a `PrepTime` table — these are ticket cook times (KDS), not mise-en-place planning.
- Ask OS treats the word "prep" as kitchen ticket delays, not tomorrow's prep list.
- A planning "prep planner / market list" lived on an older dashboard and is **not** in this Eleven frontend.

**Gaps:** no expected-plates forecast per dish, no kitchen-zone remaining qty, no daily prep list screen, no use of yield in deduction, no market list grouped by supplier. Plate checks cannot be compared to sales until POS lines exist; the product should say that plainly.

---

## 9. Jack's questions — compare and merged list

**Principle:** one generic questionnaire. Answers unlock modules, fill supplier/item settings, and choose who the rules in §7 notify. "I don't know" always goes to the owner (or accountant for money). Do not hard-code Eleven's habits in Python.

**Already in `config/storekeeper-questions.json` (v3, 7 questions):**

1. `receives_deliveries` — Do you take in deliveries?
2. `supplier_list` — Who are the suppliers? What they bring, how they arrive. **Does not ask phone or lead days.**
3. `stock_in_pos` — Are inventory items kept in the POS or server?
4. `issues_to_kitchen` — Do you hand stock from the store to the kitchen?
5. `records_waste` — Do you write down food that is thrown away?
6. `closes_the_day` — Who closes the day?
7. `knows_running_costs` — Do you know rent, gas, electricity, water, salaries, other bills?

**In `/workspace/audit/jack-app-plan.md` (12 questions) but not in the live file:** units (crate vs bottle), zones (store / cold room / bar), who signs kitchen handovers and chef names, whether there is a scale, who approves waste, how often the store is counted and with whom, who pays suppliers / who holds invoices, which dishes sell most and whether the chef measures portions.

**On the design Page (conversation, not in this repo file):** "How do you order stock today?"  
A) Owner approves, then I order.  
B) I order staples myself, up to a maximum quantity each, never a KES limit.  
C) Owner or accountant orders after I flag low stock.  
D) I don't know → owner.

**Merged ordered list** (keep existing ids where they still fit; new ids marked \* — add to the JSON, do not fork Eleven-only code):

1. **\* `order_mode` — How do you order stock today?** A/B/C/D as above. This must be first: it drives R1 and who sees "needs you."
2. `receives_deliveries` — Do you take in deliveries? (existing)
3. `supplier_list` — **Extend:** name, what they bring, how they arrive, **phone**, and **usual days from order to delivery**. "I don't know" → owner.
4. **\* `zones` — Where is stock kept?** Main store, cold room, bar, kitchen shelf, other. Unlocks zones.
5. **\* `buying_units` — Do you buy in one unit and use in another?** (crate→bottles, sack→kg). Unlocks buying unit / `units_per_buy`.
6. `stock_in_pos` — Are items also kept in the POS or a server book? (existing; still useful for import)
7. `issues_to_kitchen` — Do you hand stock from the store to the kitchen? (existing)
8. **\* `handover_who` — When stock goes to the kitchen, who takes it and who signs?** Names chefs; unlocks PIN on Jack's phone.
9. **\* `handover_when` — At what times do you hand over, on a normal day?** (e.g. before lunch, before dinner). Drives R5.
10. **\* `has_scale` — Is there a weighing scale in the store or kitchen?** No → photo recommended; yes → weight-first entry.
11. `records_waste` — Do you write down food that is thrown away? (existing)
12. **\* `waste_approver` — Who approves waste or spoilage?** Owner / manager / other name.
13. `closes_the_day` — Who closes the day? (existing)
14. **\* `count_rhythm` — How often is the store counted, and who counts with you?** Daily/weekly + second person, or working-alone.
15. **\* `par_and_max` — For each staple, what should you never go below, and (if you order yourself) what is the most you may order?** Can be "I'll set this on each item" and open the stock list, or "I don't know" → owner. Fills `par_level` / max order qty.
16. `knows_running_costs` — Rent, gas, electricity, water, salaries, other bills? (existing; money still hidden from Jack after entry)
17. **\* `who_pays` — Who pays suppliers, and who keeps the invoice?** Payments stay with accountant/owner; invoice photo stays with the store if they hold the paper.
18. **\* `prep_ahead` — Which dishes are prepped before service, and who does that?** Unlocks the prep list (chef / kitchen). "I don't know" → owner or head chef.
19. **\* `portions` — Does the chef measure portions, or is it by eye?** If measured, ask the usual unit; feeds yield / recipe completeness. Top-selling dishes can be named so recipes start there (recipes themselves stay the earlier setup step).

Recipes stay the step **before** this questionnaire (`staff_setup` already gates: account → recipes → questions). After questions, the stock list is the place to finish par, lead time, and opening counts — not a long form of every item in the questionnaire.

Anything still unknown after Jack answers is an owner (or accountant) task, with "needs you" on their Home, not a guess in an engine.

---

## 10. What I did not do

- No edits, commits, or pushes on `feat/jack-storekeeper` (a cloud agent is building on it).
- Postgres-only tests were not run.
- I did not call OpenRouter or print any key.
