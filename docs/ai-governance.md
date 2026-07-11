# Leviii AI — AI Governance

| | |
|---|---|
| **Reference** | LAI-AIGOV-001 |
| **Classification** | Confidential — shared under NDA |
| **Audience** | Auditors, customers, engineers |
| **Version** | 1.1 |
| **Last Updated** | 2026-07-11 |
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
| **Language model** — used in two roles: (a) WhatsApp free-text replies; (b) a **grounded reasoning layer** that narrates the deterministic payloads | `backend/ai/llm_client.py` + `ai/whatsapp/brain.py` (a) + `ai/reasoning/narrator.py` (b) | Non-deterministic; **never computes** — interprets/converses only |

**The core invariant: the LLM never does arithmetic.** Every number an owner sees
is produced by the deterministic engines. The language model has two jobs — answer
free-form WhatsApp questions, and turn an already-computed analytics payload into
plain-language judgment (headline, priorities, actions). In the second role it may
only cite figures verbatim from the payload it was handed, and a grounding verifier
redacts anything unbacked (see §5). Narration is additive: with no LLM provider
configured, `narrate()` returns nothing and the raw deterministic numbers are served
unchanged.

"Forecasts" are statistical extrapolations, not trained-ML predictions.

## 2. Model inventory

| Purpose | Provider | Model(s) | Data sent |
|---|---|---|---|
| Free-text WhatsApp replies | Groq (OpenAI-compatible endpoint) | e.g. `llama-3.1-8b-instant`, `openai/gpt-oss-120b` (observed) | Prompt content only |
| Grounded narration of analytics (pricing, profit, menu, roi, marketing, per-item explain) | Groq (current) | Task-tiered: routine narration on the fast model, pricing on the larger model | Deterministic analytics payload only (no raw customer text) |

**Provider strategy (Groq today → Anthropic Claude on upgrade).** Both LLM roles
run through a single client (`backend/ai/llm_client.py`) that selects Anthropic when
`ANTHROPIC_API_KEY` is set, otherwise Groq. Task complexity tiers (LOW/MEDIUM/HIGH)
already map to concrete models per provider — e.g. pricing is a money decision and
runs on a MEDIUM-tier model. The reasoning layer is running and grounded on Groq
now; enabling the frontier tier (Anthropic Claude — Haiku/Sonnet/Opus by tier) is a
single-config upgrade rolled out for production/paying customers, with **no code
change**. When that key is set, Anthropic becomes an active sub-processor (tracked in
the [Compliance Matrix](compliance-matrix.md) sub-processor list).

- Provider selection and client construction: `backend/ai/llm_client.py`; tier→model
  table and reasoning tasks: `backend/ai/reasoning/narrator.py`.
- **No training on submitted data** (provider API terms); Leviii AI does not train its own
  models on client/customer data.
- **Model/prompt versioning:** the active provider/model is configuration-driven. A formal
  prompt-version + model-change history is **TBD** — recommend recording model/prompt
  changes here going forward (a lightweight changelog table below).

### Model & prompt change log

| Date | Change | Reason |
|---|---|---|
| 2026-07-11 | Baseline documented (Groq free-text handler) | Initial AI governance doc |
| 2026-07-11 | Documented the grounded reasoning/narration layer as the second LLM role; recorded Groq→Anthropic Claude tiered upgrade path | Reconcile governance doc with shipped code (`ai/reasoning/narrator.py`) |

## 3. Where the LLM is invoked (and where it is not)

```
(a) Owner message ─▶ deterministic router (ai/whatsapp/brain.py::handle_owner_command)
                       SALES · STOCK · APPROVE · REJECT · PROMO ...  → handled WITHOUT LLM
                    unmatched free-text ─────────────────────────────▶ LLM

(b) Analytics payload (already computed) ─▶ reasoning layer (ai/reasoning/narrator.py)
                                             LLM narrates; grounding verifier redacts any
                                             number not present in the payload
```

Structured WhatsApp commands never spend tokens and never reach the model — only genuinely
free-form text does. The **only two** LLM entry points are (a) unmatched free-text and
(b) narration of a server-built deterministic payload. The narration path never receives raw
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

- **Grounding / trust rate** and per-agent success are tracked and surfaced via
  `GET /api/v1/ai/usage` (`backend/routers/ai.py`), backed by
  `backend/ai/evaluation/tracker.py`.
- **Metered signals:** LLM token spend by model, per-agent latency (p50/p95), success rate.
- **Evaluation methodology:** deterministic engines are covered by unit tests (same input →
  same output); the free-text path is monitored via grounding trust rate + success metrics.
  A formal offline eval set is **TBD** (recommended next step).

## 6. Data use & privacy

- Only the minimum content needed to answer a free-text query is sent to the model.
- No client/customer data is used to train Leviii AI models; the sub-processor does not train
  on submitted data. See DPA (LAI-DPA-001) and Sub-Processor List (LAI-SUB-001).

## 7. Limitations & responsibilities

- AI output may be incomplete or wrong; owners remain responsible for business decisions
  (Terms §05, SLA §09).
- Marketing messages via WhatsApp must honour consent + opt-out; a `STOP` reply suppresses
  the number immediately (`ai/whatsapp/optout.py`).

## Open items

- Formalise prompt/model version history (table above) and an offline evaluation set.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial AI governance doc from `backend/ai/` |
| 1.1 | 2026-07-11 | Engineering | Added the grounded reasoning/narration layer as the second (non-computing) LLM role; provider strategy (Groq→Anthropic Claude); grounding-guarantee subsection |
