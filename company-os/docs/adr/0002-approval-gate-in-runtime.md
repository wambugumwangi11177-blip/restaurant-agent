# ADR 0002 — The approval gate lives in the tool runtime, not in prompts

**Status:** Accepted, 2026-09-26

## Context
Agents read untrusted text: documents, client emails, WhatsApp messages. A prompt instruction such as "never send without approval" can be overridden by injected text. Restaurant-agent already saw a real injection attempt (its directive 012).

## Decision
- Every tool declares an `Effect`: `READ`, `INTERNAL` (writes inside the OS) or `EXTERNAL` (reaches the outside world).
- `execute_tool()` is the only path by which any tool runs. For an `EXTERNAL` tool with no approval id, it creates a `Proposal` and returns `pending_approval`.
- With an approval id, it runs only if the proposal belongs to the same workspace, is `approved`, names the same tool, and has **byte-identical canonical arguments**.
- `EXTERNAL` handlers also call `require_approval(ctx)` as a second, independent check.
- Only the `founder` role holds `approvals.decide`. Rejections require a reason. Every decision writes a `Feedback` row.
- Auto-approval is off by default. It is enabled per tool by the founder, and it only activates after a streak of `streak_threshold` (default 20, minimum 5) human approvals with no edits. An edit or a rejection resets the streak.

## Consequences
- A fully successful prompt injection can at most create a pending proposal that the founder sees in the inbox.
- Messages to the company's own members (for example WhatsApp replies to the founder) are internal notifications and don't need approval.
- Tests: `tests/test_approvals.py` covers forged, tampered, cross-workspace and replayed approvals.
