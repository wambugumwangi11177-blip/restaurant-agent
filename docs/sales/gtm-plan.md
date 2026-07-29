# Leviii — Sales & Marketing Plan

> **INTERNAL.** Companion to `cold-call-playbook.md` (today's dials), `talk-track-internal.md` (demo), `leviii-sales-pack.html` (leave-behind).
> Positioning rule inherited from the talk-track: **a restaurant operations company that happens to use AI extremely well — not an AI company.**

---

## 1. What we are actually selling

The code says something the marketing hasn't fully caught up to yet.

Leviii is not "a POS with AI features." Reading `backend/ai/`, the thing that's been built is **a deterministic profit engine with an LLM bolted on as a narrator** — and that architecture is the commercial advantage, not a technical footnote.

Three facts from the code that should shape every piece of marketing we produce:

**1. The numbers are math, not model output.**
`ai/decisions/ranking.py` opens with: *"No LLM, no randomness — the same set of decisions always ranks the same way, so the 'Best recommendation' the owner sees is reproducible and defensible."* Scoring weights are explicit (`W_IMPACT=0.45`, `W_CONFIDENCE=0.25`, `W_RISK=0.15`, `W_EASE=0.15`) and sum to 1 by construction. ADR-0005 confines the LLM to the free-text path only.

**2. We refuse to flatter our own ROI.**
`ai/roi/savings.py` keeps three totals *"deliberately never summed into one figure"* — hours saved, money captured, and opportunities-not-yet-taken. `money_captured` counts **only** recommendations the owner actually approved. Unquantified decisions contribute **zero** to the impact score rather than a fabricated value.

**3. Nothing acts without a human.**
Every recommendation is advisory; every approval is logged with who made it.

**Why this matters commercially:** the entire market is about to be flooded with "AI for restaurants" that hallucinates a number and asks an owner to trust it with pricing. Owners will get burned, once, publicly. Our differentiation is the opposite promise — **auditable arithmetic, with AI as the explainer** — and it's already true in the code. That's a defensible position and it should be the spine of the brand.

### Positioning statement

> For **multi-site restaurant owners in Kenya** who **can't see where their profit is leaking**, Leviii is **the operating system that runs the restaurant and proves where the money went** — POS, kitchen, stock, reservations and M-Pesa on one system, with a daily ranked action list built on deterministic math you can audit, not AI guesswork.

### The category reframe (the core marketing message)

> **A POS takes orders. An operating system runs the business.**
> Your POS tells you what you *sold*. It can't tell you what you *earned* — and it can't tell you what it let walk out the door.

---

## 2. ICP and segmentation

| Segment | Profile | ACV potential | Cycle | Priority |
|---|---|---|---|---|
| **A1 — Multi-site groups** | 2–8 branches, Nairobi, KES 1.5–6M/mo per site | Highest | 3–8 weeks | 🥇 **Lead here** |
| **A2 — High-volume single sites** | KES 3M+/mo, heavy delivery mix | High | 2–5 weeks | 🥈 |
| **B1 — Hotel F&B / members' clubs** | Has a finance function | High | 2–4 months | 🥉 Long game |
| **B2 — Growing single sites** | KES 1–3M/mo, ambitious owner | Medium | 2–4 weeks | Volume filler |
| **C — Small cafés** | Under KES 1M/mo, no POS | Low | Fast but low value | ⛔ Deprioritise |

**Why A1 leads:** the multi-branch benchmarking screen and chain-wide audit trail are built, they're the "enterprise closer" in the demo script, and no local competitor has them. It's also where a single sale becomes 2–8 sites.

### Buying committee

| Role | Cares about | Lead with |
|---|---|---|
| **Owner / MD** | Profit, theft, control | The leak report. **This is your champion.** |
| **Group Ops Manager** | Consistency across branches | Branch ranking on one screen |
| **Finance / Accountant** | Reconciliation, audit | M-Pesa exactly-once, deterministic numbers, audit log |
| **Head Chef** | Menu autonomy | ⚠️ Can block. Frame pricing as advisory, never automatic |
| **Floor / cashiers** | Not being blamed | ⚠️ Can quietly sabotage. Frame drift detection as *system health*, never as "catching thieves" |

**The chef and the cashiers are the two hidden veto players.** Handle them explicitly in the rollout, or the pilot dies of non-adoption in week three.

---

## 3. The wedge: portion drift

Every good GTM has one wedge — one specific, urgent, provable problem you lead with. Ours is in `_detect_portion_drift()`.

| | |
|---|---|
| **What it is** | Menu price vs. average price actually captured at the till, per dish, 14-day window. Gap over 5% is flagged and extrapolated to a monthly leak |
| **Why it's a great wedge** | Universal (happens everywhere), invisible (no existing tool shows it), emotionally charged (it's *their* money), quantifiable (a number, per dish), and provable in week one |
| **Why competitors can't copy it fast** | It needs menu price + recipe cost + item-level capture + a clean time-anchored window. A POS vendor has the data but not the analytical layer |
| **Marketing translation** | "Your till is charging less than your menu. We'll show you exactly how much." |

**Everything else — pricing intelligence, the daily action list, the digital twin, benchmarking — is expansion.** The wedge gets you in the door. Don't lead with the platform.

---

## 4. Messaging architecture

### Message hierarchy

```
LEVEL 1 (cold open)      "Your till is charging less than your menu."
LEVEL 2 (the reframe)    "A POS tells you what you sold. Not what you earned."
LEVEL 3 (the platform)   "One system: POS, kitchen, stock, reservations, M-Pesa."
LEVEL 4 (the moat)       "Deterministic math on your data. The AI explains, never guesses."
LEVEL 5 (trust)          "Nothing changes without your approval. Every action logged."
```

Use them in that order. Reversing it — opening with the platform — is the single most common way this pitch fails.

### Outcome vocabulary (never say the engine name)

Inherited verbatim from `talk-track-internal.md` §2 — it applies to all marketing copy, not just calls:

| Internal name | Public language |
|---|---|
| Decision Intelligence | "Every morning, the 3 highest-impact actions for today's profit" |
| Digital Twin / What-If | "Test a price or promo change before risking real revenue" |
| Pricing Intelligence | "Spot the dishes quietly killing your profit — fix it in one tap" |
| Profit Intelligence | "True profit per dish — and it catches when the till charges less than the menu" |
| Inventory Predictor | "Get warned days before you run out" |
| Cross-location benchmarking | "Every branch ranked on one screen" |
| Workflow Engine | "Low stock? It drafts the reorder and waits for your one-tap approval" |
| Audit log / governance | "Every AI suggestion is logged with who approved it" |

### Proof assets we can build from the code (no new engineering)

1. **The Leak Report** — a one-page PDF from the profit-intelligence output. This is the highest-value marketing asset we don't yet have. It should be the demo takeaway and the pilot deliverable.
2. **The Delivery Commission Reality Check** — `DELIVERY_COMMISSIONS` shows Uber Eats 25%, Glovo 25%, Bolt Food 20%. "What delivery apps actually cost your kitchen" is a shareable content piece that needs no product access.
3. **The Margin Benchmark** — food cost over 35% and margin under 40% are already the code's thresholds. "Is your menu healthy?" self-assessment.

---

## 5. Pricing strategy

⚠️ **Pricing is a founder decision — the numbers below are a recommended structure to approve, not established fact.** Nothing here should be quoted to a prospect until signed off.

### Principles

1. **Price per site, per month.** Matches how owners think and makes multi-branch expansion natural.
2. **Anchor on recovered leakage, not on competing POS fees.** The sales pack already estimates KES 45–90k/mo of value for a small site and KES 180–330k for a large one. Price at a clear fraction of the *conservative* end so ROI is obvious.
3. **Charge for onboarding.** Four days of in-person setup and staff training has real cost, and a free setup gets treated as worthless. A paid setup fee also filters out tyre-kickers.
4. **Do not discount on the first ask.** Restructure scope instead (fewer sites in phase one, longer term).

### Recommended structure

| Tier | For | Includes |
|---|---|---|
| **Pilot** | 1 site, 60–90 days | Full platform + Leak Report + onboarding. Paid, short commitment |
| **Standard** | Single site | Everything built: POS, KDS, inventory, reservations, M-Pesa, profit & pricing intelligence, WhatsApp assistant, daily action list |
| **Group** | 2+ sites | Standard + branch benchmarking + chain-wide audit trail. Per-site rate declining with site count |

**Billing reality check:** there is **no live payment-provider integration** for subscriptions yet (plan-setting is manual; Stripe intentionally returns 501). Invoice via M-Pesa/bank and say "subscription billing, M-Pesa or bank" — which is true. **Automating subscription billing is a real gap to close before we scale past ~20 accounts.**

---

## 6. Channel strategy

Ranked by expected return for a Nairobi-based team **today**.

### 🥇 1. Outbound calling — the primary channel
Highest-intent, fastest feedback, zero spend. **Run the `cold-call-playbook.md` daily.**
Target: 40 dials/day → ~3 demos → ~1 pilot/week.

### 🥇 2. Founder-led in-person visits
Nairobi hospitality is a relationship market. Walking into a restaurant at 3pm with a tablet and asking for eight minutes converts far better than any email. **Pair every calling block with 2–3 physical drop-ins in the same area.**
Bring: tablet with the demo, printed sales pack, phone hotspot.

### 🥈 3. Referrals from live customers
The single highest-conversion channel once we have 3–5 happy sites. Restaurant owners in Nairobi know each other.
**Build this deliberately:** at day 30 of every successful pilot, ask — "Which two other owners should see this?" Consider a formal referral incentive once there are references worth trading on.

### 🥈 4. WhatsApp — the follow-up backbone
Not a cold channel (cold WhatsApp reads as spam), but the **best warm channel in this market**. Every call, voicemail and demo gets a WhatsApp follow-up. See playbook §6.

### 🥉 5. LinkedIn — for hotel groups and the B1 segment
Where group ops managers and hotel F&B directors actually are. Not where independent owner-operators are. Use for B1 only.

### 🥉 6. Content marketing — build the authority asset
Low immediate return, compounding long-term value, and cheap because **the content already exists in the code**:
- "What delivery apps really cost your kitchen" (25/25/20%)
- "The 5% rule: how to tell if your till is undercharging you"
- "Food cost over 35%? Here's what it's doing to your margin"
Publish to LinkedIn + a simple blog. Repurpose each into a WhatsApp-shareable image.

### ⛔ Not yet
- **Paid ads** — don't spend before the pitch is proven and the pilot converts. We don't know CAC yet.
- **Channel partners / resellers** — premature. Requires product maturity and a partner margin we haven't modelled.
- **Conferences / trade shows** — expensive, slow, and a distraction at this stage.

---

## 7. The funnel

```
SUSPECT      Nairobi restaurant groups (build the list — target 200 named)
   ↓ cold call / walk-in
CONVERSATION Reached the owner, they engaged with the poke
   ↓ 20–30%
DEMO         15 min, run on real data, ends with the Leak Report offer
   ↓ 25–40%
PILOT        1 site, paid, 60–90 days, live in 4 days
   ↓ 50%+ if onboarding is done properly
CUSTOMER     Full rollout, all sites
   ↓
EXPANSION    More branches → more modules → referral
```

### Stage exit criteria — don't advance a deal that hasn't met them

| Stage | Advances only when |
|---|---|
| Conversation → Demo | Owner (not manager) has agreed a **specific time slot**, and you have the WhatsApp number |
| Demo → Pilot | The owner has said what the leak is worth to *them*, and finance/ops has seen the audit trail |
| Pilot → Customer | Leak Report delivered, at least one recommendation **approved** (this is what `money_captured` measures), staff actually using the POS daily |

**That last criterion is the one to watch.** A pilot where the floor staff quietly kept using the old till is a failed pilot, no matter how good the report was.

---

## 8. Onboarding is a sales function

The four-day onboarding is where deals are won or lost, because the biggest objection in this market is *"we tried software before and it failed"* — and it nearly always failed at implementation, not at the sale.

| Day | What happens | Sales risk to manage |
|---|---|---|
| 1 | Account, branches, staff roles | Get the owner physically present for kickoff |
| 2 | Menu, prices, recipes, M-Pesa | **Recipe/cost data is the hard part.** Bad cost data ⇒ wrong margins ⇒ lost trust. Budget real time here |
| 3 | Staff training on POS + kitchen | **Train the resistant staff member first.** Convert the skeptic and the rest follow |
| 4 | Go live, team on standby | Be physically present through one full dinner service |

**Then, and this is the part that closes the expansion:** deliver the **Leak Report in week 2**, in person, to the owner. That meeting is the real close for the remaining branches.

---

## 9. 30-60-90 day plan

### Days 1–30 — Prove the pitch
- [ ] Build a named list of **200 Nairobi restaurant groups** with owner contact details
- [ ] **40 dials/day**, two blocks (9:00–11:30, 14:30–16:30), Mon–Thu
- [ ] 2–3 in-person drop-ins per day alongside the calls
- [ ] Rehearse the demo click-path until it's flawless — it's currently the weakest link
- [ ] Build the **Leak Report** as a one-page PDF export
- [ ] Get founder sign-off on **pricing** and on whether any guarantee is offered
- [ ] **Target: 3 paid pilots signed**
- [ ] Daily: log every objection, revise one line of the script each evening

### Days 31–60 — Prove the product
- [ ] Onboard the pilots properly — founder present at every go-live
- [ ] Deliver every Leak Report in person in week 2 of each pilot
- [ ] Capture the **first real ROI numbers** from `ai/roi/savings.py` on live customer data — these replace the illustrative ranges in the sales pack and are worth more than any marketing copy we can write
- [ ] Convert 1–2 pilots to **full multi-branch rollouts**
- [ ] Ask every pilot owner for **two referrals**
- [ ] Publish the first 3 content pieces
- [ ] **Target: 2 pilots → customers, 5 new pilots in flight**

### Days 61–90 — Build the machine
- [ ] Replace all illustrative ROI ranges with **measured customer figures**
- [ ] Produce 2 written case studies (with permission) — anonymised leak figures are fine
- [ ] Formalise the referral motion
- [ ] Close the **subscription billing gap** — manual plan-setting won't scale
- [ ] Wire monitoring so we can finally **stand behind an SLA** (currently blocked — see `legal-reconciliation.md` E1). This unblocks the hotel/B1 segment
- [ ] Hire/train a second caller against this playbook
- [ ] **Target: 10 paying sites, repeatable pipeline**

---

## 10. Risks and honest gaps

Stated plainly, because the talk-track's honesty discipline applies internally too.

| Risk | Severity | Mitigation |
|---|---|---|
| **Onboarding doesn't scale** — 4 days in-person per site is founder-heavy | 🔴 High | Document it, template it, hire early. This caps growth before sales does |
| **Recipe/cost data quality** — margins are only as good as `cost_price` | 🔴 High | Make cost capture a hard gate in onboarding. Wrong margins destroy trust irreversibly |
| **No live subscription billing** | 🟠 Medium | Manual invoicing works to ~20 accounts. Close it in the 90-day window |
| **No SLA we can stand behind** | 🟠 Medium | Blocks the hotel/enterprise segment. Wire monitoring, then sell it |
| **Staff resistance to drift detection** | 🟠 Medium | Never frame it as catching thieves. Frame as system health. Train the skeptic first |
| **Chef blocking pricing changes** | 🟡 Low-med | Advisory-only framing; get the chef into the demo |
| **A POS incumbent adds a leak report** | 🟡 Low-med | Move fast, win the multi-site groups, make the audit trail and determinism the brand |
| **Over-promising gated features** | 🔴 High | The guardrails in playbook §10 are non-negotiable. One discovered over-promise costs the market's trust |

### The gaps a buyer could legitimately hold against us
Know these cold so you're never cornered (from `talk-track-internal.md` §6): LLM is Groq today (Claude is a configured upgrade path); Strategy-Agent LLM mode and WhatsApp natural-language mode are flag-off; the plugin marketplace is an SDK, not a store; menu-photo/vision is declared in routing but not implemented; the workflow engine ships one template (low-stock reorder); weather/sports signals in the twin are scaffolded (Kenyan holidays and school terms are live); Stripe intentionally returns 501; ops metrics are TBD.

**None of these are deal-breakers if disclosed. All of them are deal-breakers if discovered.**

---

## 11. Research sources

The methodology synthesis in `cold-call-playbook.md` §2 draws on:

- [Andy Elliott — How to Master the Automotive Cold Call](https://pod.wave.co/podcast/andy-elliotts-elite-mindset-motivation-and-sales-training/how-to-master-the-automotive-cold-call-andy-elliott-1a132019)
- [Jeremy Miner — A Step-By-Step Breakdown of the NEPQ Sales Process](https://7thlevelhq.com/a-step-by-step-breakdown-of-the-nepq-sales-process/)
- [Jeremy Miner — NEPQ Method guide](https://www.11x.ai/guides/jeremy-miner-sales-training-method)
- [Chris Voss — Never Split the Difference, all chapters explained](https://grahammann.net/book-notes/never-split-the-difference-chris-voss)
- [Chris Voss — Tactical Empathy (Black Swan Group)](https://vascopatricio.com/chris-voss-the-black-swan-groups-tactical-empathy/)
- [Josh Braun — Poke the Bear Cold Call Script](https://joshbraun.com/poke-the-bear-cold-call-script/)
- [Josh Braun — Ditch the Pitch. Poke the Bear](https://joshbraun.com/ditch-the-pitch-poke-the-bear/)
- [Alex Hormozi — $100M Offers summary / the Value Equation](https://www.gregfaxon.com/blog/100m-offers-summary)
- [Sandler — What Is the Sandler Pain Funnel?](https://www.alpharun.com/blog/sandler-pain-funnel)
- [Sandler — Framework explained](https://www.avoma.com/blog/sandler-sales-methodology)
- [The Challenger Sale — teach, tailor, take control](https://kendo.ai/blogs/sandler-sales-methodology)
- [Jordan Belfort — The Way of the Wolf: Straight Line Selling](https://www.theinvestorspodcast.com/blog/the-way-of-the-wolf-straight-line-selling-book-summary/)
- [Jeb Blount & cold call champions — Cold Calling Tips by Sales Champions](https://futureofprospecting.substack.com/p/cold-calling-tips-by-sales-champions)
- [Grant Cardone & others — 25 entrepreneurs teaching sales skills](https://www.amraandelma.com/entrepreneur-influencers-teaching-sales-skills/)
- [Best cold call opening lines, per three experts](https://www.greaserconsulting.com/resources/best-cold-call-opening-lines-three-experts/)
- [Objection Handling: a data-backed guide](https://prospeo.io/s/objection-handling-cold-calling)

Product claims are sourced from this repository: `backend/ai/profit/intelligence.py`, `backend/ai/roi/savings.py`, `backend/ai/decisions/ranking.py`, `backend/payments/`, `docs/adr/0005-llm-only-on-free-text-path.md`, `docs/sales/leviii-sales-pack.html`, `docs/sales/talk-track-internal.md`, `docs/sales/legal-reconciliation.md`.
