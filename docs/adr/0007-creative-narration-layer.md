# ADR 0007 — A third, bounded LLM role: creative (stochastic) writing on Home, OS and Reports

**Status:** Accepted · **Date:** 2026-09-29 · **Extends:** [ADR 0005](0005-llm-only-on-free-text-path.md)

## Context
The owner wants Home, the OS chat and Reports to *sound* like a person who knows the
business — warm, vivid, different each time — not like a template. ADR 0005 allows the LLM
two roles (free-text replies, grounded narration) and runs all of it at temperature 0 so it
embellishes as little as possible. A creative layer needs temperature above 0, which raises
the risk of invented figures and of confident claims the data does not support.

## Decision
Add a **third bounded role** — creative writing — without relaxing the invariant that **the
LLM never computes a figure**:

1. **Stochastic = temperature above 0** (`CREATIVE_TEMPERATURE`, default 0.7, clamped to
   0–1.2). It uses its own model tier (`creative`, defaulting to the medium model of whichever
   provider is active) so the voice model can be chosen independently of cost tiers.
2. **Creative voice, real figures.** Every number the model writes must already appear in the
   evidence it was given or in the owner's own words. Grounding is enforced **per sentence**
   (`ai/creative.py::keep_grounded_sentences`, built on the existing `ai/reasoning/grounding.py`
   verifier): a sentence with an unbacked figure is removed, and the whole text is discarded if
   more sentences were removed than kept. The model's own assertions are phrased as *ideas to
   test*, never as findings.
3. **Each page's evidence gate is inherited and never widened.**
   - Home: restaurant facts only when the source is *receiving and reconciled* (the same rule
     as the OS chat and `vibandaSource.ts`); otherwise it tells the **system story** and no
     restaurant figure is sent to the provider at all.
   - Reports: no take and no provider call for a period with zero recorded orders.
   - OS: restaurant evidence only when the answer is `data_available` (existing rule); planned
     features stay deterministic with no LLM call.
4. **OS orchestrates deterministic modules from code, not from the model.** Code picks up to
   three relevant modules (the primary route, other keyword matches, then companions), runs
   their existing handlers, and gives all their findings to **one** LLM call that connects
   them. The model does not choose or call anything.
5. **Automatic, cached, and honest about it.** Text is written on demand and stored in
   `creative_takes` (also an audit trail of exactly what the AI told the owner, and when). The
   last good version is always served with a "Written HH:MM" stamp; a stale one is refreshed in
   the background; a failed refresh leaves the last good text up. Every text is labelled
   **AI-written** and says what kind of statement it is.
6. **Same boundary as everything else.** All calls go through `ai/owner_narrative.narrate()`
   (PII scrub, tenant-wide spend cap, token metering, tenant lock). The layer is behind
   `FEATURE_CREATIVE_LAYER` (default **off**) and also requires `ai_narration`, so the master
   kill switch silences it.

## Alternatives considered
- **Let the LLM choose modules through tool calls** — rejected for now: 2–6 calls per question
  against a free quota, and the 2026-09-20 production review already removed a similar
  `/ai/strategy` call from chat for latency and irrelevance.
- **Redact only the offending figure, keep the sentence** — rejected: the surrounding claim was
  written around the invented number and usually no longer means anything true.
- **Generate on every page load** — rejected: quota. Cache-first with background refresh.

## Consequences
- **Quota.** Roughly two writes per hour per page and period, plus one per OS question. On the
  OpenRouter free tier (about 50 requests a day, under $10 of credit — *not verified by this
  repo*) a busy day can exhaust it; every page then serves its last take or its deterministic
  text. A failed write starts a 120 s per-key cooldown so an outage or an empty quota is not
  hammered on every page load.
- **Tenant lock contention.** `narrate()` holds a tenant-row lock during each LLM call
  (existing design); a background creative refresh can delay a chat answer by one round-trip on
  PostgreSQL.
- **Numbers can lag.** A cached story can trail the live cards by up to its TTL (30 min; 6 h
  for the system story). The written-at stamp makes this visible. A "today" story or a daily
  take written before the current Nairobi day began is never served.
- **Grounding is numeric, not semantic.** Like the narrator, it stops invented figures; it does
  not prove a sentence true or stop every prompt injection. Evidence and the owner's words are
  passed as untrusted user-role data, never in the system message.

## References
`backend/ai/creative.py`, `backend/routers/creative.py`, `backend/routers/reports.py`
(`report_creative`), `backend/routers/ai_ask.py` (`_orchestrate`, `_gather_evidence`),
`backend/ai/owner_narrative.py`, `backend/alembic/versions/050_add_creative_takes.py`,
`frontend/src/components/vibanda/CreativeNote.tsx`, [ai-governance.md](../ai-governance.md)
