# Leviii AI — AI Governance

| | |
|---|---|
| **Reference** | LAI-AIGOV-001 |
| **Classification** | Confidential — shared under NDA |
| **Audience** | Auditors, customers, engineers |
| **Version** | 1.3 |
| **Last Updated** | 2026-09-29 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose

Expands the public AI Transparency Statement (LAI-AI-001) with the engineering detail an
auditor or enterprise customer needs: what models are used, how the LLM path is isolated,
human oversight, evaluation, and limitations. Grounded in `backend/ai/`.

## 1. Two kinds of intelligence

| Kind | Where | Determinism |
|---|---|---|
| **Rule-based analytics** (Revenue, Profit, Pricing, Inventory, KDS, Reservation) | `backend/ai/*` engines | Deterministic — same input → same output; **all figures computed here** |
| **Language model** — used in three roles: (a) WhatsApp free-text replies; (b) a **grounded reasoning layer** that narrates the deterministic payloads; (c) a **creative (stochastic) layer** that writes short warm text on Home, the OS chat and Reports ([ADR 0007](adr/0007-creative-narration-layer.md)) | `backend/ai/llm_client.py` + `ai/whatsapp/brain.py` (a) + `ai/reasoning/narrator.py` (b) + `ai/creative.py` (c) | Non-deterministic (temperature 0 for (a)/(b); above 0 for (c)); **never computes** — interprets/converses only |

**The core invariant: the LLM never does arithmetic.** Every number an owner sees
is produced by the deterministic engines. The language model has three jobs — answer
free-form WhatsApp questions, turn an already-computed analytics payload into
plain-language judgment (headline, priorities, actions), and write short creative text on
Home, the OS chat and Reports. In the second and third roles it may
only cite figures verbatim from the evidence it was handed (or, in the OS chat, from the
owner's own words); the narrator's verifier redacts anything unbacked and the creative
layer removes any sentence carrying one (see §5). Narration is additive: with no LLM provider
configured, `narrate()` returns nothing and the raw deterministic numbers are served
unchanged.

"Forecasts" are statistical extrapolations, not trained-ML predictions.

## 2. Model inventory

| Purpose | Provider | Model(s) | Data sent |
|---|---|---|---|
| Free-text WhatsApp replies | The active provider (see strategy below): OpenRouter in the current production deployment; Groq before OpenRouter was configured | e.g. `llama-3.1-8b-instant`, `openai/gpt-oss-120b` (observed on Groq) | Prompt content only |
| Grounded narration of analytics (pricing, profit, menu, roi, marketing, per-item explain) | The active provider: OpenRouter in the current production deployment | Task-tiered: routine narration on the fast model, pricing on the larger model | Deterministic analytics payload only (no raw customer text) |
| Vibanda OS chat answers and the Reports narrative (`ai/owner_narrative.py`) | The active provider: OpenRouter in the current production deployment | Medium tier (`OPENROUTER_MODEL`), temperature 0; the creative tier and `CREATIVE_TEMPERATURE` for OS answers when the creative layer is on | The owner's question and recent turns; the verified evidence card only when restaurant data is available; report figures for the narrative. PII-scrubbed first |
| Creative (stochastic) text: Home story, OS chat answers, Reports take | OpenRouter when `OPENROUTER_API_KEY` is set (else Anthropic/Groq per the strategy above) | Its own `creative` tier: `OPENROUTER_MODEL_CREATIVE` / `ANTHROPIC_MODEL_CREATIVE` / `GROQ_MODEL_CREATIVE`, each defaulting to that provider's medium model. Temperature `CREATIVE_TEMPERATURE` (default 0.7) | Server-built evidence JSON (recorded figures, item and stock names, up to three attention titles) — **none at all while the data source is unverified** (Home sends only what the software does). OS chat also sends the owner's own message and recent turns. Everything is PII-scrubbed first |

**Provider strategy (OpenRouter → Anthropic → Groq).** All LLM roles
run through a single client (`backend/ai/llm_client.py`) that selects OpenRouter when
`OPENROUTER_API_KEY` is set, else Anthropic when `ANTHROPIC_API_KEY` is set, otherwise Groq.
OpenRouter (one key, many models; the `:free` models are the default) is documented in
`llm_client.py` as the owner's chosen chat/report gateway. Task complexity tiers (LOW/MEDIUM/HIGH)
already map to concrete models per provider — e.g. pricing is a money decision and
runs on a MEDIUM-tier model. The current production deployment calls OpenRouter
(Railway logs show `openrouter.ai` chat-completion requests, observed 2026-09-27).
Moving to the frontier tier (Anthropic Claude — Haiku/Sonnet/Opus by tier) is still a
configuration change with **no code change**: either point the `OPENROUTER_MODEL*`
tier variables at Claude models on OpenRouter, or set `ANTHROPIC_API_KEY` **and remove
`OPENROUTER_API_KEY`** (OpenRouter takes precedence while its key is set). When Anthropic
is called directly it becomes an active sub-processor (tracked in the
[Compliance Matrix](compliance-matrix.md) sub-processor list).

- Provider selection and client construction: `backend/ai/llm_client.py`; tier→model
  table and reasoning tasks: `backend/ai/reasoning/narrator.py`.
- **No training on submitted data** (provider API terms); Leviii AI does not train its own
  models on client/customer data.
- **Model/prompt versioning:** the active provider/model is configuration-driven. The
  narration prompt now carries an explicit `PROMPT_VERSION`
  (`backend/ai/reasoning/narrator.py`) that is stamped on every metered turn
  (`token_usage.prompt_version`, migration 018), so a shift in token spend or grounding
  rate can be traced to a specific prompt revision. `GET /api/v1/ai/usage` breaks token
  spend down `by_prompt_version` and reports the `current_prompt_version`. Human-meaningful
  prompt changes are recorded in the changelog table below and the version string is bumped.

### Model & prompt change log

| Date | Change | Reason |
|---|---|---|
| 2026-07-11 | Baseline documented (Groq free-text handler) | Initial AI governance doc |
| 2026-07-11 | Documented the grounded reasoning/narration layer as the second LLM role; recorded Groq→Anthropic Claude tiered upgrade path | Reconcile governance doc with shipped code (`ai/reasoning/narrator.py`) |
| 2026-07-11 | Introduced `PROMPT_VERSION` (`2026-07-11.v1`), stamped on every metered turn (`token_usage.prompt_version`) and surfaced in `GET /api/v1/ai/usage` | Make prompt drift traceable per AIOps roadmap item |
| 2026-09-29 | Added the creative layer's prompts: `creative-today_story-v1`, `creative-system_story-v1`, `creative-report_take-v1` (Home/Reports) and `owner-os-creative-v1` (OS chat); temperature above 0; new `creative` model tier | Third bounded LLM role (ADR 0007); versions are stamped on `token_usage.prompt_version` like every other prompt |

## 3. Where the LLM is invoked (and where it is not)

```
(a) Owner message ─▶ deterministic router (ai/whatsapp/brain.py::handle_owner_command)
                       SALES · STOCK · APPROVE · REJECT · PROMO ...  → handled WITHOUT LLM
                    unmatched free-text ─────────────────────────────▶ LLM

(b) Analytics payload (already computed) ─▶ reasoning layer (ai/reasoning/narrator.py)
                                             LLM narrates; grounding verifier redacts any
                                             number not present in the payload

(c) Evidence the page's own gate allows ───▶ creative layer (ai/creative.py)
    Home: verified source → recorded figures; otherwise → what the software does (no figures)
    Reports: period has orders → report figures + related module findings
    OS: data_available → primary module + up to two related modules, all deterministic
                                             LLM writes; every sentence with an unbacked
                                             figure is removed; text is cached + labelled AI-written
```

Structured WhatsApp commands never spend tokens and never reach the model — only genuinely
free-form text does. The **only three** LLM entry points are (a) unmatched free-text,
(b) narration of a server-built deterministic payload and (c) the creative layer, which only
receives evidence the owning page's gate has already released (behind
`FEATURE_CREATIVE_LAYER`, default off). The narration path never receives raw
untrusted customer/owner text — only figures the engines already computed — which keeps its
prompt-injection surface lower than the free-text path (see
[Threat Model](security/threat-model.md) T14).

## 4. Human-in-the-loop

- AI output is **advisory decision-support**. It does not take irreversible or legally
  significant actions autonomously.
- **Pricing and similar data-changing actions require explicit approval** (dashboard, or
  `APPROVE` via WhatsApp). Un-actioned recommendations change nothing.
- Every data-changing AI action is written to the append-only `AgentAuditLog` with
  `action_type`, `agent_name`, `before_state`/`after_state`, `reasoning`, `data_sources`,
  and `approved_by` (`backend/models.py`).

## 5. Evaluation & observability

**Grounding guarantee (the control that makes narration safe).** Every narrative the
reasoning layer produces is passed through `grounding.verify()`
(`backend/ai/reasoning/narrator.py` → `backend/ai/reasoning/grounding.py`) before it can
reach an owner: any figure the model wrote that does not appear in the deterministic payload
is **redacted** and recorded. The share of narratives that pass fully grounded is tracked as
a live trust rate (`get_trust_stats()`), not a marketing figure invented separately from the
mechanism. Reasoning also runs at temperature 0 to minimise invented figures before the
verifier even runs.

- **Creative layer grounding.** Text from the creative layer is checked sentence by sentence
  against the evidence it was sent (and, in the OS chat, the owner's own words): a sentence with
  an unbacked figure is removed, and the whole text is dropped when more sentences were removed
  than kept. Dropped counts are stored per text (`creative_takes.dropped_sentences`) and every
  text served is kept in `creative_takes` as an audit trail of what the AI told the owner and
  when. Like the narrator's verifier this is numeric, not semantic.
- **Grounding / trust rate** and per-agent success are tracked and surfaced via
  `GET /api/v1/ai/usage` (`backend/routers/ai.py`), backed by
  `backend/ai/evaluation/tracker.py`.
- **Metered signals:** LLM token spend by model **and by prompt version**, per-agent latency
  (p50/p95), success rate.
- **Quality-drift alarm.** For the forecasting agents (which record predictions and later
  evaluate them against actuals), `get_quality_drift()` compares recent prediction error
  against the prior baseline in the same window and flags an agent whose mean absolute error
  worsened beyond a threshold, so degradation is caught before owners lose trust in a number.
  It reports `insufficient_data` rather than a false all-clear when history is too thin, and
  is included in the `GET /api/v1/ai/usage` payload (`quality_drift`).
- **Evaluation methodology:** deterministic engines are covered by unit tests (same input →
  same output); the free-text path is monitored via grounding trust rate + success metrics;
  forecast agents are monitored via the quality-drift alarm above. A formal offline eval set
  is **TBD** (recommended next step).

## 6. Data use & privacy

- Only the minimum content needed to answer a free-text query is sent to the model.
- No client/customer data is used to train Leviii AI models; the sub-processor does not train
  on submitted data. See DPA (LAI-DPA-001) and Sub-Processor List (LAI-SUB-001).

## 7. Limitations & responsibilities

- AI output may be incomplete or wrong; owners remain responsible for business decisions
  (Terms §05, SLA §09).
- Marketing messages via WhatsApp must honour consent + opt-out; a `STOP` reply suppresses
  the number immediately (`ai/whatsapp/optout.py`).

## 8. Availability & fallback policy

The LLM is an **additive** layer. The product's numbers, decisions, and safety controls do
not depend on it, so an LLM outage degrades presentation, never correctness. Concretely:

| Failure | Behaviour | Owner impact |
|---|---|---|
| No provider configured (`is_available()` false) | `narrate()` returns `None`; routes serve the raw deterministic payload | Sees the exact figures, without the plain-language headline |
| Provider timeout / network / 5xx / bad model id | Caught in `narrate()`; logs a warning and returns `None` | Same as above — graceful, no error surfaced |
| Model returns malformed/creative output | `_parse()` still yields a usable dict; `grounding.verify()` **redacts** any unbacked figure | Never sees an invented number |
| Creative layer off (`FEATURE_CREATIVE_LAYER` unset, `ai_narration` off, or no provider) | Endpoints answer `reason: disabled` with no text and make no provider call; Home, Reports and OS render exactly as before | No creative note; everything else unchanged |
| Creative write fails (provider error, daily budget reached, output fails grounding) | The last good text stays up with its written-at time and a one-line reason; nothing is shown if there is none. A 120 s per-key cooldown stops repeated attempts | Sees an older note, clearly stamped — never an error |
| Data source not verified | Home tells the system story only; no restaurant figure is sent to the provider | Sees what the software does, not their results |
| Free-text WhatsApp reply unavailable | Structured commands (SALES, STOCK, APPROVE, PROMO, …) are handled deterministically and are unaffected; only open-ended free-text replies are skipped | Core WhatsApp operations keep working |

Design guarantees behind the policy:

- **Fail-safe, not fail-open for numbers:** the grounding verifier removes unverifiable
  figures rather than passing them through, so a misbehaving model degrades to *less* text,
  never *wrong* text.
- **No LLM on the money path:** every figure is computed by the deterministic engines; the
  model cannot change a price, send a message, or move data on its own (see §4 human-in-the-loop).
- **Cost ceiling & tiering:** task tiers cap which model each call may use; structured commands
  never spend tokens (see §3), bounding spend even under load.
- **Observability of the degradation:** the grounding trust rate and per-agent success/latency
  (`GET /api/v1/ai/usage`) make a provider degradation visible rather than silent.

Operationally: an LLM provider incident is **not** a SEV-1 for correctness (numbers still
serve); it is handled as a degraded-experience event. Recovery is a config change (restore
the key / switch provider — Groq↔Anthropic per §2), with **no code change** required.

## Open items

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial AI governance doc from `backend/ai/` |
| 1.1 | 2026-07-11 | Engineering | Added the grounded reasoning/narration layer as the second (non-computing) LLM role; provider strategy (Groq→Anthropic Claude); grounding-guarantee subsection |
| 1.2 | 2026-07-11 | Engineering | Prompt versioning (`PROMPT_VERSION` + `token_usage.prompt_version`); quality-drift alarm; written §8 availability & fallback policy |
| 1.3 | 2026-09-29 | Engineering | Creative (stochastic) layer as the third bounded LLM role (ADR 0007): model inventory, §3 entry point (c), §5 sentence-level grounding, §8 fallback rows; provider order documented as OpenRouter → Anthropic → Groq; stale "Groq (current)" rows corrected and the OS chat / Reports narration row added |
