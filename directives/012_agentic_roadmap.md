# Agentic Roadmap — Replaces the Sprint 0.3–0.10 Plan

## Why this exists
The previous plan ("Sprint Summary: Privacy-Preserving AI System Build") was written with
help from a small local model (Gemma-class) and audited on 2026-07-07. Findings:

- Phase 0 basics (Twilio validation, structured logging, circuit breakers, DPA audit trail,
  consent gating) are **real and largely correct** — keep them.
- Sprints 0.6–0.10 (differential privacy, federated learning, zero-knowledge proofs,
  homomorphic encryption, secure multi-party computation) are **non-functional theater**:
  hallucinated/uninstalled dependencies (`phe`, `snarkyjs`), single-process simulations
  labeled as distributed protocols, none of it callable in the current environment, none
  of it something an enterprise restaurant buyer asks for. Cut permanently.
- `restaurant-agent/` (untracked folder) is a separate, abandoned tree — not the deployed
  app — and contained a supply-chain-style prompt injection (a `.claude` hook that tried to
  get an agent to clone-and-run an unvetted external script). Quarantined, not deleted.
  The real, deployed app is the top-level `backend/` (tracked in git, run via
  `backend/Procfile` → gunicorn).
- Every module under `backend/ai/` (pricing, labor, marketing, profit, supply_chain,
  menu_engineer, reservation_optimizer, revenue_forecaster, ops_manager, kds_intelligence)
  is deterministic SQLAlchemy + threshold rules. This is **correct design, not a bug** —
  see `directives/011_ai_infrastructure_understanding.md`, which already says so honestly
  ("Pure Python analytics, no external ML dependencies"). The mistake was ever calling it
  "AI Intelligence" in sprint-plan language; the modules themselves don't need to change.
- `backend/ai/llm_client.py` is a real, correctly-built Anthropic client (with optional
  Headroom token-compression) — but is imported nowhere. 0% of "the AI system" is
  currently LLM-backed.
- The WhatsApp "brain" (`backend/ai/whatsapp/brain.py`) is a hardcoded keyword matcher
  (SALES/STOCK/PENDING/...), not a reasoning agent. Its inbound webhook route did not
  exist until this roadmap's Phase 2 work started (see status below) — the app could
  send WhatsApp messages but never receive owner replies.

## Principle carried forward from CLAUDE.md
Layer 3 (execution) stays deterministic. LLMs are probabilistic and only belong where a
decision requires interpreting open-ended natural language or planning a sequence of tool
calls — i.e. Layer 2 orchestration. Do not add LLM calls inside pricing/labor/forecasting
logic; that would make the system less reliable, not more intelligent.

---

## Phase 0 — Foundation (DONE, verified 2026-07-07)
- [x] Twilio request signature validation — real HMAC check in
      `backend/ai/whatsapp/twilio_client.py`, fail-closed.
- [x] Inbound WhatsApp webhook wired — `backend/routers/webhooks.py: POST /webhooks/whatsapp`,
      verified end-to-end (bad signature → 403, missing signature → 403, valid signature →
      200 with real command reply).
- [x] Structured logging, circuit breakers, consent gating, DPA audit trail — real, keep.
- [ ] Rotate `GROQ_API_KEY` / `SECRET_KEY` found in plaintext in the quarantined
      `restaurant-agent/.claude/settings.local.json` — treat as burned regardless of
      whether they were ever pushed remotely.

## Phase 1 — Deterministic Core

### Correction (2026-07-07)
`execution/deploy_payment_schema.py` / `verify_payment_callback.py` were mistakenly
assumed to be Phase 1 progress on the real app. They actually target a `bookings` /
`user_id_hash` schema that only exists in the abandoned `restaurant-agent/` tree —
**zero overlap with the real `backend/models.py` `Order` table.** The real app had
**zero working M-Pesa integration**: `routers/webhooks.py`'s `/mpesa` endpoint was a
stub that logged the payload and returned `{"status": "received"}` without touching the
database. Flagging this explicitly since it was stated as "further along" earlier in
this roadmap before a closer read caught the mismatch — worth remembering that a script
existing and doing real-looking work doesn't mean it's wired to the actual deployed schema.

### Status (updated 2026-07-07) — M-Pesa now real, verified end-to-end
- [x] `models.Order`: added `mpesa_checkout_request_id` (unique, correlation key) and
      `mpesa_receipt`. Migration `alembic/versions/003_add_mpesa_fields_to_orders.py`,
      tested against a simulated pre-existing `orders` table (not just a fresh DB).
- [x] `payments/mpesa_client.py` (new, deliberately outside `ai/` — this is payments
      infra, not AI, per the roadmap's own labeling rule): real Daraja OAuth + STK push
      request builder, degrades to `{"status": "not_configured"}` when credentials are
      unset (mirrors `ai/whatsapp/twilio_client.py`'s pattern). Verified: correct payload
      shape (whole-shilling amount conversion, base64 password, bearer token) via a
      mocked HTTP layer, and graceful no-crash when unconfigured.
- [x] `routers/webhooks.py: POST /webhooks/mpesa` rewritten to actually parse Safaricom's
      real `stkCallback` shape, correlate via `mpesa_checkout_request_id`, and hand off to
      the *existing* (previously never-triggered) event bus — `emit(EventType.ORDER_PAID,
      ...)` → `ai/orchestrator/executive.on_order_paid_mpesa` (already correctly marks
      paid, sends WhatsApp receipt, writes audit log — no logic duplicated).
      Verified end-to-end against 5 real scenarios: successful payment, duplicate
      callback (idempotent — does not reprocess or resend the receipt), failed/cancelled
      payment (does not mark paid), and an unrecognized `CheckoutRequestID` (ignored, no
      crash).
- [x] `routers/orders.py: POST /orders/public` now triggers `initiate_stk_push()` when
      `payment_method == "mpesa"`, storing the returned `checkout_request_id` on the
      order. Best-effort by design: a failed/unconfigured push never breaks order
      creation (`_trigger_mpesa_stk_push`'s docstring explains why — cash/card/manual
      retry remain valid fallbacks). Added `mpesa_client.normalize_phone()` to convert
      the common Kenyan phone input shapes (0712..., +254712..., 712...) to the
      2547XXXXXXXX format Daraja requires, returning `None` (skip, don't guess) for
      anything unrecognizable.
      **Bug fixed in passing**: `create_public_order` was silently ignoring the
      customer's chosen `payment_method` and always storing `PENDING` regardless of
      input — found while wiring this in, fixed in the same change.
      Verified end-to-end (mocked HTTP): valid M-Pesa order stores the
      `checkout_request_id`; malformed phone number skips the push without crashing
      order creation; cash order confirmed to keep "cash" (bug-fix regression check).
- [ ] Rename mislabeled endpoints/docs from "AI Intelligence" to "Recommendations Engine" /
      "Analytics" where they are rule-based — cosmetic only, prevents future confusion
      about what's LLM-backed vs deterministic. No logic changes.
- [ ] pricing/labor/forecasting/menu_engineer modules are correct as-is — no new work
      needed there.

## Phase 2 — The Orchestrator (the real new work — start here)
This is the only phase that should introduce LLM calls.

### Status (updated 2026-07-07)
- [x] `ai/llm_client.py`: added `chat_with_tools()` — Anthropic tool-use + prompt caching
      (cache_control on the last tool + system block). Verified the request shape is
      accepted by Anthropic's API (rejected only on a fake key — auth error, not a
      validation error), so the payload structure is confirmed correct.
- [x] Per-tenant token metering: `agent_messages.llm_model/input_tokens/output_tokens`
      (`alembic/versions/002_add_agent_message_token_usage.py`), migration tested clean
      against a fresh DB (upgrades 001 → 002 without error).
- [x] `ai/whatsapp/orchestrator.py`: tool-calling router wrapping the existing
      `_cmd_sales_today` / `_cmd_stock` / `_cmd_pending_pricing` / `_cmd_tonight` /
      `_cmd_winback_summary` functions as tools (bounded to 4 turns, logs usage each turn).
      No business logic duplicated.
- [x] `brain.handle_owner_command`: keyword matcher untouched (SALES/STOCK/PENDING/...
      still a free, instant, zero-token match); only unmatched free-form text falls
      through to the orchestrator. Verified end-to-end: keyword path never touches the
      LLM, and free-text degrades gracefully to the pre-existing "I didn't understand"
      message when `ANTHROPIC_API_KEY` is unset — safe to deploy today with the key still
      off.
- [x] `ai/reservation_optimizer.find_available_tables()`: real deterministic
      capacity + time-overlap conflict checker, verified against 6 scenarios (empty
      slate, party too large, exact overlap, partial overlap, adjacent non-overlap,
      cross-date isolation).
- [x] **Booking-write guards + concurrency gap closed (2026-07-08).** The docstring's
      "no DB-level concurrency guard yet" caveat turned out to *understate* the problem.
      Auditing the write path found `routers/reservations.create_reservation` never
      called `find_available_tables()` — or any availability check — at all. It took
      `table_id` from the request body and wrote it straight to the row. Consequences,
      both reproduced in tests before fixing:
        1. **Double-booking needed no race**: two plain sequential POSTs for the same
           table and overlapping times both succeeded.
        2. **Cross-tenant IDOR**: passing another restaurant's `table_id` booked *their*
           table, since nothing checked the table belonged to the caller's restaurant.
           `test_tenant_isolation.py` covered orders/reservations *update/delete by id*,
           but not a **foreign key supplied in a create body** — a class of IDOR that
           id-scoping tests structurally miss. Worth auditing other routers for
           FK-in-body inputs that are never ownership-validated.
      Fixed in three layers: table ownership + capacity + `is_table_available()` checked
      before INSERT (409 on conflict, **404 — not 403 — on another tenant's table**, so
      the response cannot be used to enumerate other restaurants' floor plans); an
      `IntegrityError` catch turning a lost race into the same clean 409; and
      `alembic/versions/009_add_reservation_overlap_guard.py`.
      **Why not the `ix_pricing_rec_one_pending_per_item` partial-unique-index pattern
      this roadmap originally prescribed**: uniqueness cannot express *interval overlap*.
      Bookings at 18:00 and 18:30 on one table are distinct rows under any unique key,
      yet they conflict. It needs `EXCLUDE USING gist (table_id WITH =, tsrange(...) WITH
      &&)` plus the `btree_gist` extension. The original prescription was wrong — noting
      it because "apply the same fix as last time" is exactly how a wrong guard ships
      looking right. Half-open `tsrange` matches the Python `_intervals_overlap` boundary
      semantics by construction, so 18:00–19:30 and 19:30–21:00 conflict in neither layer.
      Verified: 9 new tests in `tests/test_reservation_booking.py` (overlap rejected,
      adjacent allowed, cancelled frees the slot, cross-tenant table 404s, undersized
      table 400s, table-less booking still works, migration no-ops on SQLite / emits the
      constraint on Postgres / is idempotent). Suite: 85 passed.
- [ ] **Migration 009 has not been run against a real Postgres.** No local Postgres exists
      here and the only reachable instance is the production Neon DB — running untested
      DDL against production to prove it works is not testing. Before deploy: run it
      against a staging/Neon branch, confirm the role may `CREATE EXTENSION btree_gist`,
      and **check for pre-existing overlapping CONFIRMED rows first** — nothing has ever
      prevented them, so `ADD CONSTRAINT` can fail on live data. The migration's docstring
      carries the exact reconciliation query.
- [ ] **Blocked on a product/legal decision, not an engineering one**: reservation
      booking needs a customer-facing inbound flow (distinct from the owner-command
      webhook) and a decision on consent/PII handling — the consent/tokenization vault
      code only exists in the abandoned `restaurant-agent/` tree, not in the real
      deployed `backend/`. Do not build the customer-facing webhook or wire an LLM
      booking tool until this is decided.
- [x] **Provider correction (2026-07-07): the project's real, available LLM credential
      is `GROQ_API_KEY`, not Anthropic.** `backend/` had no `.env` at all (only the
      abandoned `restaurant-agent/backend/.env` did), and that file has `GROQ_API_KEY`
      + `OPENAI_API_KEY` but no `ANTHROPIC_API_KEY` — matching the original sprint plan's
      own description ("Sprint 0.3: real LLM orchestration (Groq + Twilio + ReAct
      loop)"). `llm_client.py` had been built Anthropic-only up to this point on an
      unstated assumption. Rewritten to select a provider at runtime (Anthropic if
      configured, else Groq, else unavailable) and normalize Groq/OpenAI-shaped
      responses into the same interface `ai/whatsapp/orchestrator.py` already expects
      (`response.stop_reason`, `.content` blocks, `.usage`) — the orchestrator's own code
      did not need to change. `requirements.txt`: added `openai==1.58.1` (Groq's API is
      OpenAI-compatible) as active now; Anthropic stays commented out, gated behind the
      same explicit "client has paid" business decision as before.
      **Real tool-use round-trip against a live API key — done.** Used the real
      (already-available) Groq key against a local throwaway test database (not the
      shared production Neon DB — see note below). The full loop worked for real: a
      free-form message ("how are sales looking today?") correctly triggered the
      `get_sales_today` tool, got a real tool result, and produced a natural-language
      reply — with real token usage (517 input / 9 output, `llama-3.3-70b-versatile`)
      logged to `agent_messages`, confirming the Phase 2 cost-metering plumbing works
      end-to-end on a genuine call, not just a mocked one.
      **Deliberately not decided autonomously**: whether to point the real `backend/` at
      the same production Neon database referenced in the abandoned tree's `.env`. That
      database has known incompatible-schema history (the `bookings`/`user_id_hash`
      tables from the M-Pesa mismatch found earlier) — pointing live production
      infrastructure at shared state is a consequential decision for the user, not
      something to do quietly while fixing an LLM provider bug.
- [x] **Model default updated (2026-07-07)**: `GROQ_MODEL` default changed from
      `llama-3.3-70b-versatile` to `openai/gpt-oss-120b` (the model the user's own
      working curl example against Groq's API used) — re-verified with a real live
      orchestrator round-trip on the new key + model, tool-calling confirmed working.
- [ ] Cheap/fast model for intent classification vs Sonnet/Opus escalation — not yet
      implemented; `chat_with_tools()` currently always uses the single configured
      model. Worth noting Groq's models are already inference-optimized/cheap relative
      to frontier models, so this matters less urgently on the Groq path than it would
      on Anthropic — revisit if/when Anthropic is ever enabled.
- [x] **Reservation-booking consent blocker resolved (2026-07-07)** — see
      directives/013_production_readiness_roadmap.md's "Minimal consent gate" entry.
      The mechanism (`models.CustomerConsent`) now exists and is wired into the one
      current customer-facing PII touchpoint (`POST /orders/public`). Building the
      actual customer-facing WhatsApp reservation-booking flow itself is still separate,
      unstarted work — this only resolves what specifically blocked it (no consent
      mechanism existing at all).

### Design (as implemented)
1. **Hybrid router**: exact known commands stay a free, instant, zero-token match; only
   unmatched free-form text spends tokens. This is most real-world owner traffic.
2. **Tool-calling, not prompt-stuffing**: existing `ai/*` functions exposed as thin tool
   wrappers — the LLM only decides which to call, never reimplements the logic.
3. **Cost engineering built in from the start**: prompt caching on by default; tool
   outputs stay terse (matches existing `_cmd_*` string composition); per-tenant token
   counter live from the first orchestrator turn, before any billing model exists.
4. **Headroom** (`headroom-ai`, still commented out in `requirements.txt` per the
   explicit "uncomment when client has paid" gate) becomes worth enabling once real
   token volume exists — not yet, since Phase 2 hasn't shipped real LLM traffic.

## Phase 3 — Memory & Localization (small, follows naturally from Phase 2)
- [ ] Decide honestly whether `ai/memory/store.py`'s Postgres event log is sufficient
      context for the orchestrator, or whether real semantic recall (vector DB) is needed —
      don't build vector search speculatively; the current docstring's "no vector DB
      needed at this scale" may still hold true after Phase 2 ships.
- [ ] Sheng/Swahili support — a system-prompt/locale addition once real LLM calls exist,
      not a separate engineering effort.

## Phase 4 — Operational Bridge / Enterprise Scale (original Phases 3–4, unchanged in spirit)
- POS/table sync, multi-tenant schema isolation, staff notification system — proceed as
  originally planned, but now sitting on top of a real orchestrator instead of a rules
  engine mislabeled as one.
- Model-routing cost engineering (originally "Sprint 4.2") graduates here from "the one
  router in Phase 2" to "route every agent call by task complexity" across all
  LLM-backed flows.

## Permanently cut
Differential privacy, federated learning, zero-knowledge proofs, homomorphic encryption,
secure multi-party computation. If a specific enterprise deal ever genuinely requires a
provable-privacy claim, scope it as a real, standalone feature at that time — not as a
standing phase built speculatively ahead of any customer asking for it.

## Standing rule for all future modules
Before calling anything "AI," answer one question: does it call an LLM, or is it
deterministic logic? Label it accordingly in code comments, directive docs, and any
customer-facing copy. This single check would have caught the mislabeling across all of
Phase 3–5 in the original plan.
