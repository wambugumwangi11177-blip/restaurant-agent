# Pricing Assessment — What Leviii Can Truthfully Charge

| | |
|---|---|
| **Reference** | LAI-PRICE-001 |
| **Classification** | **INTERNAL — never share with a prospect** |
| **Version** | 1.0 |
| **Date** | 2026-07-30 |
| **Basis** | Direct source audit of `backend/`, `frontend/`, `execution/`, `docs/` at `bd340dd` |

> Method: price from what the code **does**, not what the brochure says. Every claim below
> was verified against source or by running the suite. Where the product is thinner than the
> pitch, the price is set to the thinner reality. Ranges assume Nairobi mid-market restaurants.

---

## 1. What was verified (the honest asset)

Measured, not asserted:

| Signal | Verified value |
|---|---|
| Backend Python | 31,454 LOC |
| Frontend TS/TSX | 7,035 LOC across 15 pages |
| Tests | **362 passing** (ran full suite: 151s, 0 failures) |
| Test code | 6,465 LOC |
| API surface | 82 endpoints across 15 routers |
| Data model | 33 tables, 25 Alembic migrations |
| Documentation | 4,437 LOC (ADRs, threat model, trust centre, compliance matrix) |
| History | 94 commits, 2026-06-03 → 2026-07-14 |

**Code quality is genuinely high**, and this is the single biggest factor holding the price up.
Evidence, not vibes: `ai/profit/intelligence.py` carries per-bug provenance comments
(BUG-04 UTC-correctness, BUG-10 null-safe cost lookup); `ai/simulation/signals.py` explicitly
refuses to add a "weekend" provider to avoid double-counting the forecaster's baseline;
`feature_flags.py` defaults every flag to its *safe* state; `cost_model.py` rounds unknown
models *up* so spend is never understated. `ai/roi/savings.py` deliberately refuses to sum
realized money and opportunity money into one flattering number. That discipline is rare and
is worth real money.

Integrations that are genuinely wired: **M-Pesa Daraja** (STK push, real HTTP, graceful
degradation), **Twilio WhatsApp**, **Groq LLM** (narration only, PII-scrubbed, grounding-checked).

---

## 2. What the code does *not* support (the price ceiling)

These are the findings that cap what can be charged honestly. Items marked ⚠️ are ones the
existing sales material currently oversells.

**⚠️ F1 — There are zero measured customer outcomes. The demo runs on manufactured data.**
`talk-track-internal.md` §4 instructs running the demo on "**Lavy's real data**." The source
says otherwise. `execution/seed_showcase_restaurant.py` generates the dataset, then two further
scripts tune it for appearance: `tune_showcase_health.py` raises stock levels because 16 low
items "read as *restaurant in crisis*", and `smooth_recent_and_finalize.py` tops up low revenue
days because dips "made revenue WoW read -28%." The margins that make the pricing engine
produce recommendations were themselves varied by the seeder — before that, every item sat at
an identical 62% margin and the engine correctly found nothing.

This is fine as a *demo environment* and the scripts are honest in their own docstrings. But it
means **the ROI table in the sales pack has never been observed on a real restaurant.** The
brochure already labels it "illustrative" — that label is load-bearing and must stay. Pricing
cannot be anchored to it.

**⚠️ F2 — Multi-branch is reporting-only. Operations are single-restaurant.**
This is the demo's "enterprise closer" and it is half-built. `routers/enterprise.py` benchmarks
across an `Organization` correctly and is properly tenant-scoped. But every operational route —
POS, orders, menu, inventory, reservations — resolves the restaurant through
`deps.get_restaurant_or_none()`, which is `.filter(tenant_id == user.tenant_id).first()`
(`backend/routers/deps.py:40`). **56 non-test call sites** use it.

The consequence: one tenant with five branches can *benchmark* all five, but every operational
request lands on branch #1. Split the branches into separate tenants and operations work, but
`Organization` is tenant-scoped so the benchmark can no longer span them. **A chain cannot
actually be run on Leviii today.** This is D4 in the debt register, filed as P2 — it is
commercially P1, because it blocks the highest-value tier.

**F3 — No subscription billing.** `routers/billing.py` is a plan/status state machine with
`provider="manual"`; an admin sets the plan and nothing charges. Stripe returns 501 by design.
Every shilling must be invoiced and chased by hand.

**F4 — The SLA is unbacked.** No uptime monitoring, alerting or paging is wired (only a
Prometheus `/metrics` endpoint that pages no one). The team's own `legal-reconciliation.md`
flags this as E1/highest-risk and holds SLA-001 and BCP-001 from handover. **Credit-backed
uptime terms must not be signed until this is wired** — that is a financial liability, not a
doc gap. It is also ~1 hour of work to fix.

**F5 — Single-instance ceiling.** APScheduler runs in-process (`main.py:88`); no Redis, no
durable queue. Horizontal scaling would double-fire scheduled jobs. Fine for the first dozen
tenants, not for a hundred.

**F6 — Partly-built features that must not be sold.** Vision/menu-photo declared in routing but
not implemented. Plugin marketplace is an SDK plus one example — no store, no sandbox. Workflow
engine ships one template. Weather/sports signals return nothing without API keys. Strategy
agent and WhatsApp NL memory are flag-**off**. The talk track already handles these correctly.

**F7 — No external penetration test** (D10), and RBAC coverage is incomplete (D1, the only P1).

---

## 3. Cost floor — what a tenant actually costs to serve

| Cost | Per tenant / month |
|---|---|
| Hosting share (Railway + Neon + Vercel) | KES 1,000 – 2,500 |
| LLM narration (Groq, ~$1–5) | KES 130 – 650 |
| Twilio WhatsApp (volume-driven) | KES 650 – 6,500 |
| **Support labour** (named WhatsApp contact, 2–4 hrs) | **KES 3,000 – 10,000** |
| **Total** | **KES 5,000 – 20,000** |

**The dominant cost is human, not infrastructure.** The support model that has been sold — a
named contact reachable on WhatsApp, plus emergency cover — is what makes this expensive.
Any price below **~KES 15,000/month is loss-making** for a single-operator business once
support time is honestly costed. Onboarding is a further one-off 16–24 hours
(≈ KES 25,000–60,000 of labour).

---

## 4. The recommended price

### First 3–5 customers — design-partner pricing
**KES 25,000 setup + KES 15,000/month.**

Not a discount for its own sake: it is the price of buying the thing the product is missing —
**evidence**. Make reference rights and outcome measurement contractual, and instrument the
four ROI lines against the customer's real books from day one. That converts F1 from a
permanent weakness into a dated one. Price covers cost; it does not fund growth, and it
shouldn't yet.

### Standard pricing — once 3 months of measured outcomes exist

| Tier | Price / month | What it honestly includes |
|---|---|---|
| **Operations** | **KES 15,000** | POS, KDS, inventory + predictive restock, reservations, M-Pesa, dashboard, exports. A complete single-location system. |
| **Intelligence** *(the real product)* | **KES 30,000** | Everything above + profit intelligence, pricing recommendations, ranked daily decisions, what-if simulation, WhatsApp owner assistant, marketing engine, ROI dashboard. |
| **Multi-branch benchmarking** | **+ KES 8,000 / extra branch** | **Cross-branch reporting, benchmarking and chain-wide audit trail only.** Sell it as a reporting add-on. Do **not** sell chain operations until F2 is fixed. |

**Setup fee: KES 50,000**, one-off. Keep it. It covers real labour and filters tyre-kickers.

**Sanity check:** Intelligence at KES 30,000/month against a KES 3M/month restaurant is **1.0%
of revenue** — squarely normal for restaurant tech, and a 3–5× multiple against the brochure's
claimed value range. It only stays defensible if the value shows up, which is exactly why the
design-partner phase comes first.

### What each fix is worth in price

| Do this | Then charge |
|---|---|
| Wire uptime monitoring + alerting (~1 hr, fixes F4) | Unlocks signing a credit-backed SLA at all — a hard blocker on enterprise deals |
| Fix restaurant scoping (F2/D4) | A real chain tier: **KES 20,000 base + KES 15,000/branch** |
| 3 months of measured outcomes at 3 sites (F1) | +30–50% across all tiers; ROI table stops being "illustrative" |
| Real subscription billing (F3) | Cuts collections labour; enables annual prepay discounts |
| External pentest (F7) | Removes the standard enterprise-procurement blocker |

---

## 5. If selling the codebase outright

Distinct from subscription pricing. ~38.5k LOC with 362 passing tests, 25 migrations and a
complete compliance pack represents roughly **8–14 developer-months** of conventional work.

- Kenyan senior-developer cost basis: **KES 2.8M – 4.9M**
- Western contract-rate basis (1,200–2,000 hrs @ $80–150/hr): **$120,000 – 220,000**

Discount for the absence of revenue, customers and a scaling story; a buyer prices the traction,
not the lines. The code is the strong part of this asset — the market evidence is the missing part.

---

## 6. The one-line answer

**KES 30,000/month for a single mid-size restaurant (Intelligence tier), KES 15,000/month for
operations-only, KES 50,000 one-off setup — but start the first three customers at KES 15,000/month
+ KES 25,000 setup in exchange for measured outcomes and reference rights.**

The engineering justifies the top of that range. The **absence of a single measured customer
outcome** is what holds it there rather than higher — and that is a dated problem, not a
structural one. Fix F2 and F4 and the enterprise tier becomes real.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-30 | Engineering | Initial assessment from source audit at `bd340dd` |
