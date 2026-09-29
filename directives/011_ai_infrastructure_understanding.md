# AI RESTAURANT OPERATING SYSTEM
# Executive Infrastructure Directive

## Implementation Status: ACTIVE

### Architecture Summary
The AI Intelligence Engine is built as a modular service layer in `backend/ai/`.
Each AI service queries the database, runs analytical algorithms, and returns structured insights via the `/ai/` API endpoints.

### Implemented Systems

#### 1. Intelligent POS (Transaction Intelligence)
- **Status**: Active
- **Implementation**: Order + OrderItem models capture every transaction with item-level detail
- **AI Service**: Revenue Forecaster analyzes sales patterns and forecasts demand
- **Endpoint**: `GET /ai/revenue-forecast`

#### 2. AI Kitchen Display System (KDS Intelligence)
- **Status**: Active
- **Implementation**: PrepTime model logs actual cook times per station
- **AI Service**: KDS Intelligence detects bottlenecks and measures throughput
- **Endpoint**: `GET /ai/kds-intelligence`

#### 3. AI Inventory Intelligence System
- **Status**: Active
- **Implementation**: StockMovement model tracks all inventory in/out flows
- **AI Service**: Inventory Predictor forecasts depletion and recommends reorders
- **Endpoint**: `GET /ai/inventory-predictions`

#### 4. AI Reservation & Table Flow Intelligence
- **Status**: Active
- **Implementation**: Reservation + Table models with no-show tracking
- **AI Service**: Reservation Optimizer scores no-show probability and calculates revenue per seat
- **Endpoint**: `GET /ai/reservation-insights`

#### 5. AI Operations Manager
- **Status**: Active
- **Implementation**: Central aggregator pulling from all AI services
- **AI Service**: Ops Manager calculates restaurant health score (0-100) and generates cross-system alerts
- **Endpoint**: `GET /ai/dashboard`

#### 6. AI Revenue Optimizer (Menu Engineering)
- **Status**: Active
- **Implementation**: Menu Engineering Matrix (Star/Plowhorse/Puzzle/Dog)
- **AI Service**: Classifies items by popularity vs profitability, detects upsell pairs
- **Endpoint**: `GET /ai/menu-engineering`

### Data Models (backend/models.py)
- **Tenant** — Multi-tenant isolation
- **User** — Role-based access (superadmin/admin/staff)
- **Restaurant** — Core entity
- **Table** — Physical tables with status tracking
- **MenuItem** — Enhanced with cost_price, prep_station, avg_prep_minutes
- **Order** — Enhanced with order_type, table_number, completed_at
- **OrderItem** — Links orders to items with quantity/price snapshot
- **PrepTime** — Actual kitchen prep time per item per station
- **InventoryItem** — Stock levels with expiry tracking
- **StockMovement** — Inventory in/out/adjust tracking
- **Reservation** — Bookings with no-show and deposit tracking

### API Endpoints (backend/routers/analytics.py)
All endpoints require JWT authentication.

| Endpoint | Returns |
|---|---|
| `GET /ai/dashboard` | Health score, quick stats, top alerts, module summaries |
| `GET /ai/menu-engineering` | Item matrix, upsell pairs, pricing recommendations |
| `GET /ai/revenue-forecast` | Daily/hourly/weekly patterns, 7-day forecast, trends |
| `GET /ai/kds-intelligence` | Station performance, bottlenecks, throughput metrics |
| `GET /ai/inventory-predictions` | Depletion timelines, reorder points, spoilage risk |
| `GET /ai/reservation-insights` | No-show analysis, table utilization, revenue per seat |

### Demo Data
Run `execution/seed_demo_data.py` to generate 30 days of realistic data:
- 714+ orders with item-level detail
- 18 menu items with cost prices
- 14 inventory items with stock movements
- 197+ reservations with no-show patterns
- Login: admin@leviii.ai / admin123

### Technology Stack
- **Backend**: Python + FastAPI
- **Database**: SQLAlchemy + SQLite (dev) / PostgreSQL (prod)
- **AI Engine**: Pure Python analytics (no external ML dependencies)
- **Frontend**: Next.js + TailwindCSS
- **Auth**: JWT + Argon2

### Future Enhancements
- [ ] ML-based demand forecasting (sklearn/prophet)
- [ ] Real-time WebSocket updates for KDS
- [ ] Dynamic pricing engine
- [ ] Automated purchase order generation
- [ ] WhatsApp/Voice reservation integration

---

## Creative (stochastic) layer — Home, OS, Reports (added 2026-09-29, ADR 0007)

A third bounded LLM role: warm, temperature-above-0 writing that may only cite figures already
in its evidence (or, in OS, the owner's own words). **Default off.**

**Turn it on:** set `FEATURE_CREATIVE_LAYER=true` (also needs `ai_narration`, which is on by
default, and a provider key). Turn it off the same way; `FEATURE_AI_NARRATION=false` silences it
too. The migration (`050_creative_takes`) runs on boot like every other.

| Surface | Endpoint | Mode | Gate it inherits |
|---|---|---|---|
| Home | `GET /api/v1/ai/creative/home?period=today\|1h\|7d\|30d` | `today_story` when the source is *receiving and reconciled*; otherwise `system_story` (period `any`, **no restaurant figures sent**) | Same rule as the OS chat and `frontend/src/lib/vibandaSource.ts` |
| Reports | `GET /api/v1/reports/{period}/creative` | `report_take` | No orders in the period → `reason: no_data`, no provider call |
| OS | `POST /api/v1/ai/chat` (existing) | Answers become creative when the flag is on; adds `creative`, `consulted_modules`, `dropped_sentences` | `data_available` (existing). Planned-feature answers stay deterministic |

All three accept `?refresh=1` (Home/Reports). Response: `{surface, mode, period, text, llm_used,
generated_at, stale, reason, dropped_sentences}` plus `refresh_failed` when a rewrite failed and
the previous text was kept. `reason` is one of `disabled`, `no_data`, `budget_reached`,
`provider_error`, `ungrounded`, `evidence_unavailable`.

**How it works (`backend/ai/creative.py`, no router imports):**
- Text is cached in `creative_takes` (also the audit trail). Cache hit = one indexed query, no
  evidence build, no provider call. TTL 30 min (`CREATIVE_CACHE_TTL_SECONDS`), 6 h for the system
  story (`CREATIVE_SYSTEM_STORY_TTL_SECONDS`). A stale take is served and flagged; the client
  refreshes it once in the background. "Try another take" is debounced for 60 s.
- A "today" story / daily take written before the current Nairobi day began is **never served**
  (`valid_since`): the cache key has no date.
- A failed write keeps the last good text and starts a 120 s per-key cooldown, so a provider
  outage or an empty quota is not hammered by page loads. Cooldown and the duplicate-call lock
  are in-process — correct because gunicorn runs `--workers 1` (`backend/Dockerfile`); revisit
  if that changes.
- Grounding is sentence-level (`keep_grounded_sentences`): unbacked figure → sentence removed;
  more removed than kept → whole text dropped (tokens are still metered).
- OS orchestration is done by **code**, not by the model: `_orchestrate()` picks up to three
  modules (primary, other keyword matches, companions from `_COMPANIONS`), `_gather_evidence()`
  runs their handlers (each in its own SAVEPOINT), and one creative call connects the findings.

**Env vars:** `FEATURE_CREATIVE_LAYER`, `CREATIVE_TEMPERATURE` (default 0.7, clamped 0–1.2),
`CREATIVE_CACHE_TTL_SECONDS`, `CREATIVE_SYSTEM_STORY_TTL_SECONDS`, and the creative model tier
`OPENROUTER_MODEL_CREATIVE` / `ANTHROPIC_MODEL_CREATIVE` / `GROQ_MODEL_CREATIVE` (each defaults to
that provider's medium model). See `backend/.env.example`.

**Quota warning.** Up to about two writes per hour per page and period, plus one per OS
question, all sharing one provider quota. On the OpenRouter free tier this can run out on a busy
day (the ~50/day figure is unverified here); pages then fall back to their last take or their
deterministic text. Adding OpenRouter credit, or pointing `OPENROUTER_MODEL_CREATIVE` at a paid
model, is the fix.

**Verify after deploying (cannot be done from the build container — openrouter.ai egress is
blocked there):** set the flag, open `/vibanda`, `/vibanda/os` and `/vibanda/reports`; check the
"AI-written" labels and "Written HH:MM" stamps; check `token_usage.prompt_version` rows named
`creative-*` and `owner-os-creative-v1`; check OpenRouter's daily usage. Ask the owner before
spending live quota on a test.

**Learnings:** the plan's cache key had no date, so a story written at 23:50 would have been
served at 00:10 as "today's" — `valid_since` fixes it. Evidence is built lazily (only when a
provider call will be made) because Home's evidence runs every specialist agent. The
duplicate-call guard compares row identity ("was a take written while I waited for the lock?"),
not an age window — running the layer against a real PostgreSQL showed the age-window version
stopped deduplicating as soon as the refresh debounce was tuned to 0. The alembic chain cannot
run end-to-end on SQLite (043 uses PostgreSQL-only `unnest(enum_range(...))`); to check a new
migration locally, use a PostgreSQL cluster, or `alembic stamp <previous>` on a scratch SQLite
DB and exercise just the new revision.
