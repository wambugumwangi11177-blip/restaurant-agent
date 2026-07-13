# Leviii — Pitch Talk-Track & Demo Script (INTERNAL — do not share)

> For your eyes only. Never hand this to a prospect. Positioning: **a restaurant operations company that happens to use AI extremely well — not an AI company.** 80% product & money, 20% trust. Security is a *close*, not an opener.

---

## 1. The one-line pitch
"Leviii runs your whole restaurant on one system — POS, kitchen, stock, reservations, M-Pesa — and every morning it tells your managers the three things to do to make more money today."

## 2. Golden rule — say the outcome, never the engine name
| Never say (internal name) | Say this instead |
|---|---|
| Decision Intelligence | "Every morning, the 3 highest-impact actions for today's profit." |
| Digital Twin / What-If | "Test a price or promo change before risking real revenue." |
| Pricing Intelligence | "Spot the dishes quietly killing your profit — fix the price in one tap." |
| Profit Intelligence | "True profit per dish, and it catches when the till charges less than the menu." |
| Inventory Predictor | "Get warned days before you run out." |
| Strategy Agent | "Set a goal like +KES 100k profit and get a step-by-step plan." (say "rolling out") |
| Cross-location benchmarking | "Every branch ranked on one screen." |
| Workflow Engine | "Low stock? It drafts the reorder and waits for your one-tap approval." |
| Audit log / governance | "Every AI suggestion is logged with who approved it." |

## 3. The moat sentence (keep in your back pocket)
When they ask *"why can't our current POS vendor just add this?"*:
> "Every profit number is deterministic math on your real data — the AI only explains and ranks it, it never guesses your numbers. That's what lets you trust it to touch pricing. Bolting a chatbot onto a POS doesn't get you that."

---

## 4. Live demo script (~10 minutes) — run on **Lavy's real data**
Rehearse this exact click-path beforehand. Bring a phone hotspot in case venue wifi fails.

| # | Screen | Say | Watch out |
|---|---|---|---|
| 1 | Dashboard / health score | "One glance — how the restaurant is doing right now." | 30 sec, don't linger |
| 2 | POS | Take a quick order live. | — |
| 3 | Kitchen Display | "The order's already in the kitchen — no shouting, no lost tickets." | — |
| 4 | Inventory (low-stock) | "It's already warning us about this item before we run out." | — |
| 5 | **AI Decisions** | "This is the magic — the 3 highest-impact actions for today, ranked by money." | **The wow moment — pause here** |
| 6 | Profit Intelligence | "True profit per dish. See this one? The till's been charging less than the menu." | — |
| 7 | WhatsApp assistant | Text `SALES` / `STOCK` live. | **Use command mode only** — NL/LLM mode is off |
| 8 | **Digital Twin / What-If** | "Watch — I'll test a 10% price rise on this dish before we ever touch it." | — |
| 9 | **Enterprise dashboard** | "And every branch, ranked, on one screen." | **The enterprise closer** |
| 10 | Questions | Hand over the brochure + ROI sheet. | — |

**Do NOT demo live:** Strategy-Agent LLM mode (flag off — show its deterministic plan instead), WhatsApp natural-language mode (flag off), plugin marketplace (SDK only), menu-photo/vision (not built).

---

## 5. Support answer (rehearse — enterprise deal-maker)
- *"What if the POS dies during Friday dinner rush?"* → "It's our top-priority incident with a direct WhatsApp line to the team; and you have a simple paper-fallback procedure so service never stops while we restore you — orders get entered back in after."
- *"Do you answer at night?"* → "Emergency cover for service-critical outages, and a named contact you reach on WhatsApp during operating hours."
- ⚠️ **Do not quote the June SLA's 15-minute / 24-7 / 'automatic alerting' numbers until monitoring is actually wired (see legal-reconciliation.md → E1).** Speak to intent, not a signed number, until then.

## 6. Private caveats — know these so you're never cornered
- **LLM provider is Groq today**, not Claude. Claude is a configured upgrade path. (If asked: "we run on Groq, with Claude available as a drop-in upgrade.")
- **Strategy-Agent LLM mode** and **WhatsApp natural-language memory** are **flag-off by default** — the deterministic versions always work.
- **Plugin marketplace** is a working SDK with an example — **not a live store, not a hardened sandbox.** First-party/vetted plugins only. Don't promise a marketplace.
- **Billing** has no live payment-provider integration yet (manual plan-setting). Fine to say "subscription billing, M-Pesa/bank."
- **Menu-photo / vision** is declared in routing but **not implemented** — don't demo or promise it.
- **Weather/sports** signals in the Digital Twin are **scaffolded**; Kenyan holidays & school terms are live.
- **Workflow Engine** ships **one** template (low-stock reorder) — the engine is general, but say "starting with automated reordering."
- **Stripe is intentionally disabled** (returns 501) — M-Pesa is the real payment path.
- **Ops metrics (MTTR/RTO)** are marked "TBD — to be measured" in the docs; don't quote hard reliability numbers you can't yet evidence.

## 7. Honesty discipline (why this matters)
Enterprise buyers forgive missing features. They never forgive discovering something was presented as production-ready when it wasn't. Use: **"Built"** (wired today) · **"Rolling out"** (built, gated) · **"Coming soon"** (roadmap). Never blur them.
