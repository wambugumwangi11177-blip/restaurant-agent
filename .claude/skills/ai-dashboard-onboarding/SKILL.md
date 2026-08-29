---
name: ai-dashboard-onboarding
description: Fix or extend what a brand-new restaurant-agent account sees on the AI Command Center (/dashboard/ai) and related AI/analytics pages before real data exists. Use this whenever asked why a new account's dashboard looks incomplete, why AI agents/insights aren't showing, why the empty state doesn't match what's actually built, or when adding a new AI module that also needs an onboarding/empty-state story. Also use it before labeling anything "AI" in dashboard copy — this app has a specific, previously-litigated rule about that.
---

# AI Dashboard Onboarding & Empty States

## The bug, exactly as it exists today

`frontend/src/app/dashboard/ai/page.tsx`:
- Line 175: `isNewRestaurant = !data || (!data.quick_stats.menu_items && !data.quick_stats.total_revenue_30d)`
- Line 176-178: if true, the page returns **only** `<EmptyState>` — a full early
  return, not a partial one.
- `EmptyState` (line 85) advertises exactly **3** agents: Pricing
  Intelligence, Stock Monitoring, Revenue Forecasting (lines 115-118).
- But the real, built system (verified against
  `directives/014_business_intelligence_roadmap.md`, phases P1-P11, all
  marked DONE) has far more: Decisions (`DecisionsSection`), Pricing, Labor,
  Supply Chain, Data Quality, Menu Engineering, Profit — 7 module sections
  in the normal (non-empty) render path — **plus** `<StrategyAgent />`,
  `<WhatIfSimulator />`, `<DigitalTwin />` (lines 269/276/279), and
  server-side capability for a knowledge graph (`/ai/graph/impact`),
  workflow engine (`/ai/workflows/*`), and plugin marketplace (`/ai/plugins`)
  that have no dashboard surface referenced in `EmptyState` at all.

So the bug isn't "the AI system is incomplete" — it's that the **empty
state undersells a system that's mostly already built**, and hides all of
it behind a single all-or-nothing gate instead of showing each module in
its own not-yet-active state. This is exactly the "same dashboard, but some
of it doesn't show what's needed" complaint — verify this diagnosis still
holds (re-check the line numbers above) before assuming the fix, since this
file is under active development and may have moved.

## Fix direction (not yet built — this is the plan, verify before assuming done)

1. **Don't gate the whole page on `isNewRestaurant`.** Each module section
   already fetches independently via `useAiModule` (the hook used by
   `PricingSection`, `LaborSection`, etc. — grep `useAiModule` for its
   current shape before changing it). Each section should handle its own
   "not enough data yet" state and explain what it *will* show, the same
   way `ModuleShell` already handles `loading`/`error` — extend that
   pattern to a third state instead of short-circuiting the entire page one
   level up.
2. **`EmptyState`'s agent list must match reality.** List all the modules
   that actually exist (grep the `function ...Section()` definitions in
   this file, plus the three components rendered outside sections, plus
   anything server-side with no UI yet — flag those as "coming soon" rather
   than omitting them silently, or omit them deliberately and say why, but
   don't let the list silently drift out of sync with what's built again).
3. **`StrategyAgent`, `WhatIfSimulator`, `DigitalTwin` should still render
   for a new account** — they're interactive tools (a what-if simulator
   works with hypothetical inputs regardless of history), not just charts
   over past data. Check whether each one already degrades gracefully with
   no data before assuming it needs its own empty state built.

## The labeling rule — don't violate this while fixing the empty state

`directives/012_agentic_roadmap.md`'s "Standing rule for all future
modules": **before calling anything "AI" in copy, know whether it calls an
LLM or is deterministic.** Verified fact: most of `backend/ai/*` (pricing,
labor, marketing, profit, supply_chain, menu_engineer,
reservation_optimizer, revenue_forecaster, ops_manager, kds_intelligence)
is deterministic SQLAlchemy + threshold rules, not LLM-backed — this is
called out as *correct design*, not a bug, but mislabeling it in
user-facing copy was flagged as a real mistake previously. Only
`StrategyAgent` (`ai/orchestrator/strategist.py`) is genuinely LLM-backed
today. When writing new empty-state copy, don't upgrade a deterministic
threshold check into "AI predicts..." language it doesn't earn — "predicts"
is fine for the forecaster (it's doing real forecasting math), "AI" as a
standalone label for a threshold rule is the thing to avoid.

## Verify before calling it done

- Load `/dashboard/ai` as a genuinely fresh account (no menu items, no
  orders) and confirm every module that should appear does, in whatever
  reduced/explained state is appropriate — not just that the page doesn't
  crash.
- Load it again after adding one menu item and one order, and confirm the
  transition from empty-state to real-data is a smooth per-module
  transition, not a jarring whole-page swap.
- Grep for other pages with the same all-or-nothing empty-state pattern
  (the code comment at line 170-174 of `page.tsx` references "the main
  dashboard's demo-data fallback" as a same-class bug already fixed
  elsewhere — check whether that fix's approach is reusable here, and
  whether any other dashboard route still has the old pattern).

## When you're done

If the actual module list or empty-state design changes meaningfully from
what's described here, this file drifts out of date fast — update it in
the same change, the same way directives get updated, so the next person
(or the next invocation of this skill) isn't working from a stale bug
description.
