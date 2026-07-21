# Changelog

Notable changes to the Leviii AI platform and its documentation. Newest first. Derived from
git history on `feat/phase1-production-hardening`.

## Unreleased — Strategist agent reliability fixes (2026-07-21)

### Fixed
- **Strategist tool loop could exhaust its whole turn budget with no output** — with
  tools available on every turn, the model could spend all `MAX_STRATEGY_TURNS` calling
  tools and never produce a final answer, silently burning ~6 real LLM calls (~130s,
  reproduced live) for a bare `"No strategy produced."`. The final turn now drops tool
  access entirely, forcing the model to conclude in text; a defensive trace-based
  fallback also covers the case where even that comes back blank. (D14)
- **Truncated JSON on the concluding turn** — found while verifying the fix above: the
  final turn's `max_tokens=1500` could cut off a full `{headline, steps, risks}` object
  mid-generation, so `_parse_strategy` fell back to raw, truncated text with empty
  `steps`/`risks`. The concluding turn now gets `max_tokens=3000` and an explicit
  instruction to keep the answer concise (≤3 steps, ≤2 risks).
- **`chat_with_tools()` now omits `tools` entirely for a no-tools turn** instead of
  passing an empty array — some OpenAI-compatible APIs reject an explicit `tools: []`,
  which the strategist fix above now relies on. Applies to both providers.
- **Weekly strategy review notification deep-linked to the wrong page** — routed to
  `/dashboard/ai-ops` (a cost/token/reliability metrics page with no strategy content)
  instead of `/dashboard/ai` (the actual `StrategyAgent` headline/steps/risks UI).
  Reproduced live for both Owner and Manager; now routes to a new `"ai"` domain in
  `push_notifier.py`'s `_TIER_URLS`. (D15)

Found and fixed during multi-role staff + AI reasoning layer testing on the Lavy
showcase data. See `tech-debt-register.md` D14/D15 for the full detail and file:line
references. Verified: `pytest tests/test_strategist.py tests/test_llm_client.py
tests/test_push_notifier.py` (45 passed), plus a live re-run of `POST /ai/strategy`
confirming a real, grounded headline where the bug previously returned nothing.

## Unreleased — Documentation & hardening (2026-07-11)

### Added
- **Trust documentation set** under `docs/`: Control Evidence Matrix, Technical & Client
  Trust Centers, Architecture, Engineering Standards, Operations & Reliability, AI
  Governance, Threat Model + Risk Register, Compliance Matrix, FAQ, ADRs, this changelog,
  and a tech-debt register. Grounded in the codebase; operational actuals marked TBD.
- **Legal-pack redline change-list** for the externally-generated 12-document legal set.
- **RBAC enforcement** — `require_role` dependency applied to admin-sensitive routes
  (data export/erasure, `/api/v1/ai/usage`, restaurant profile) with `test_rbac.py`.
- **Password policy at registration** — minimum 8 chars incl. letters + digits.
- Argon2id variant pinned explicitly (`argon2__type="ID"`).

### Changed
- **AI documentation reconciled with shipped code** across the doc set (architecture,
  AI governance, ADR 0005, both trust centers, control-evidence matrix, threat model,
  compliance matrix, engineering standards, FAQ): the LLM is now documented as used in
  **two** non-computing roles — WhatsApp free-text **and** a grounded reasoning/narration
  layer over the deterministic analytics — with the "LLM never computes" invariant and the
  grounding-redaction control stated explicitly, plus the Groq→Anthropic Claude tiered
  upgrade path.

### Notes
- Full backend test suite: **206 passing**.

## Prior (from git history)

- `79908e8` — AIOps: `GET /api/v1/ai/usage` (token spend, agent latency, grounding).
- `638a61a` — `/api/v1` versioning + JWT session revocation (`token_version`).
- `29f188b` — Fail-closed startup config guard + green test suite.
- `cb97fae` — Stock-alert tests pinned to deterministic service hours.
- `4362786` — DB integrity constraints + disaster-recovery runbook.

## Conventions

- Group entries under Added / Changed / Fixed / Security.
- Reference the commit or PR. Move "Unreleased" to a dated version on release.

_Owner: Engineering · Contact: leviiiaikenya@gmail.com_
