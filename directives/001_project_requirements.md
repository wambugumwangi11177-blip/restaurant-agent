# Project Requirements: Leviii AI (Restaurant Agent)

> Migrated from original GEMINI.md.
> **Revised 2026-08-06** — product name, module claims reconciled against the
> code, and the capture-layer principle added. Divergences are called out
> inline rather than quietly edited away; see the notes under each module.

## Product name

**Leviii AI.** The application was previously branded "Chakula" in the frontend
(layout, login, order page, `manifest.json`, `sw.js`) while every document and
all sales material said Leviii AI — so a prospect clicking the link saw a
different product than the one in the deck. Unified to Leviii AI 2026-08-06.
Use one name everywhere.

## Core Philosophy
This project is an AI Infrastructure App for Restaurants. It must be:
1.  **Scalable**: Multi-tenant architecture (Main Account -> Sub-accounts).
2.  **Premium**: "God-Tier" UI/UX. Dark mode, glassmorphism, fluid animations.
3.  **Intelligent**: AI agents embedded in every module.

### The capture-layer principle (added 2026-08-06)

**Analytics may only read tables that a production code path writes.**

This was learned the expensive way. An audit found several of the most built-out
analytics modules reading tables whose only writer was `populate_production.py`,
the demo seeder — `PrepTime` (kitchen intelligence), `StaffMember`/`LaborShift`
(labor intelligence), and `MenuIngredient` (theoretical usage, which had no API
at all). On a real restaurant every one of those modules took its empty branch,
silently and forever. The analytics were correct; they were starved.

The failure was invisible because an empty response and a healthy response look
the same from outside, and the seeded demo tenant made everything look fine in
development.

So, before building any analytics module, answer in the directive:
1. Which tables does it read?
2. Which **live** endpoint or scheduled job writes each of them — not the seeder?
3. What does the module return when those tables are empty, and how would anyone
   notice the difference between "empty" and "working"?

If (2) has no answer, build the write path first. An analytic with no capture
path is not a feature; it is a place where a feature could go.

## Tech Stack Rules
-   **Frontend**: Next.js (App Router), TailwindCSS. Deployed on Vercel.
-   **Backend**: Python (FastAPI). **Deployed on Railway** (the original spec
    said Render; Railway is what actually runs, via `railway.json` + `Dockerfile`).
-   **Database**: Neon / Railway (PostgreSQL).
-   **Payments**: Safaricom Daraja (M-Pesa STK push + tokenized callback).
-   **Messaging**: Twilio (WhatsApp).

## Modules

1.  **POS (Point of Sale)**: Fast, touch-friendly, **offline-capable** (built
    2026-08-06 — see directive 006 for the full design and its limits before
    describing this to a restaurant). Prices are recalculated server-side from
    the menu on every order — the client cannot set a total.

    > **History, for whoever next touches this claim:** this directive said
    > "offline-capable logic" from the start and for a long time it wasn't true
    > — `frontend/public/sw.js` cached the app shell but the POS kept no local
    > state, so a dropped connection meant no orders could be taken. Corrected
    > the same day it was built: an IndexedDB write queue, a `client_order_id`
    > idempotency key so a retried sync can't double-create an order or
    > double-deduct stock, a cached menu snapshot so the POS still has
    > something to sell from on a cold reload with no connection at all, and a
    > sync indicator. See directive 006 for the mechanism and its remaining
    > edges (queue is per-device, not shared across terminals).

2.  **KDS (Kitchen Display System)**: Real-time syncing, per-station prep timing.

    > **Station routing is partially implemented.** `MenuItem.prep_station` and
    > `PrepTime.station` exist and, since 2026-08-06, are *populated* — see
    > directive 006. What does not yet exist is a station-filtered KDS view: the
    > kitchen page still shows one undifferentiated queue. The data to build it
    > is now being captured, so this is a UI change, not a schema change.

3.  **Inventory**: Order-driven deduction, predictive ordering (AI).
    See directive 007 — deduction became real on 2026-08-06 and works via
    recipes (`MenuIngredient`), which until then had no write API.

4.  **Reservations**: Visual table management, WhatsApp integration.
    Double-booking is prevented at the database level (migration 009), not in
    application code.

5.  **Staff & Labor** (added 2026-08-06): roster, shifts, clock-in/out.
    See directive 015.

6.  **Billing** (added 2026-08-06): per-tenant subscription state and
    enforcement. See directive 016.

## AI Infrastructure

-   Centralized AI agents handling specific tasks across modules.
-   Data-driven insights for restaurants.

**Standing rule on honesty about what is "AI".** Most of `backend/ai/` is
deterministic arithmetic, not LLM inference. Only three modules call an LLM:
`ai/whatsapp/orchestrator.py` (the tool-calling agent), `ai/reasoning/narrator.py`
(turns computed numbers into prose), and `ai/orchestrator/strategist.py`. This is
a deliberate architecture (ADR-0005) and the reason token costs stay bounded —
but it means every number the owner sees is computed, and the LLM only ever
describes it. Label modules accordingly in directives and in the UI; do not
describe deterministic analytics as AI inference.

Numbers written by the LLM are additionally enforced by
`ai/reasoning/grounding.py`, which redacts any figure not present in the payload
the model actually saw.
