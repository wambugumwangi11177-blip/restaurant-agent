# ADR 0005 — LLM confined to non-computing roles; math stays deterministic

**Status:** Accepted · **Date:** 2026-07-11 (documenting an existing decision;
scope clarified same day — see Update)

## Context
Language models are useful for interpreting free-form owner messages but add cost,
non-determinism, and a prompt-injection surface. Most owner interactions are structured
commands.

## Decision
Route WhatsApp messages through a **deterministic command router** first
(`ai/whatsapp/brain.py`). Structured commands (SALES, STOCK, APPROVE, REJECT, PROMO…) are
handled without any LLM. Only unmatched free-text is sent to the LLM. All analytics
engines stay deterministic — **the LLM never computes a figure.**

## Update (2026-07-11) — the LLM also narrates, but still never computes
The original decision above framed the LLM as reaching only the free-text WhatsApp path. The
shipped system has a second, equally-bounded LLM role: a **grounded reasoning layer**
(`ai/reasoning/narrator.py`) that turns an already-computed deterministic analytics payload
(pricing, profit, menu, ROI, marketing, per-item explain) into plain-language judgment. This
does **not** relax the core principle — the reasoning layer performs no arithmetic; it may
only cite figures already present in the payload, and a grounding verifier
(`ai/reasoning/grounding.py`) redacts any unbacked number before it reaches an owner.
Narration is additive (disabled ⇒ raw numbers still served). The invariant is therefore
restated precisely: **the LLM is confined to two roles — free-text replies and grounded
narration — and computes nothing in either.**

## Consequences
- Bounded token cost and a minimized attack/error surface on the WhatsApp command path.
- Deterministic, testable behavior for all figures; the LLM handles only genuine free-form
  language and grounded interpretation, advisory and human-reviewed.
- Provider is configuration-driven (`ai/llm_client.py`): Groq today, upgrading to Anthropic
  Claude by task tier via a single env change for production/paying customers — no code change.

## References
`backend/ai/whatsapp/brain.py`, `backend/ai/reasoning/narrator.py`,
`backend/ai/reasoning/grounding.py`, `backend/ai/llm_client.py`,
[ai-governance.md](../ai-governance.md)
