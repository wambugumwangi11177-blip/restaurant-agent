"""
backend/ai/whatsapp/orchestrator.py
────────────────────────────────────
Phase 2 (directives/012_agentic_roadmap.md) — the LLM-backed fallback path.

handle_owner_command() in brain.py already handles exact known commands
(SALES, STOCK, PENDING, ...) as a free, instant keyword match — that path is
untouched and stays the default for most real-world traffic. This module is
only invoked when a message doesn't match any known command, i.e. free-form
natural language. It exposes the *existing* deterministic brain functions as
tools and lets Claude decide which to call — no business logic is duplicated
or reimplemented here.
"""

import logging
from sqlalchemy.orm import Session
import models
from . import brain

logger = logging.getLogger("ai.orchestrator")

TOOLS = [
    {
        "name": "get_sales_today",
        "description": "Get today's revenue, order count, and payment breakdown.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_stock_alerts",
        "description": "Get critical/low inventory items that need reordering soon.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_pending_pricing",
        "description": "List pricing recommendations awaiting owner approval.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_tonight_reservations",
        "description": "List tonight's confirmed reservations and total covers.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_winback_candidates",
        "description": "List lapsed customers who haven't ordered recently.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

_TOOL_DISPATCH = {
    "get_sales_today": brain._cmd_sales_today,
    "get_stock_alerts": brain._cmd_stock,
    "get_pending_pricing": brain._cmd_pending_pricing,
    "get_tonight_reservations": brain._cmd_tonight,
    "get_winback_candidates": brain._cmd_winback_summary,
}

SYSTEM_PROMPT = (
    "You are a WhatsApp assistant for a restaurant owner. Use the available "
    "tools to answer questions about sales, stock, pricing approvals, "
    "reservations, or lapsed customers. Keep replies short and WhatsApp-friendly "
    "(plain text, occasional emoji, no markdown headers). If the request doesn't "
    "match any tool, say so plainly and suggest replying HELP for the list of "
    "known commands."
)

MAX_TOOL_TURNS = 4


def handle_natural_language(db: Session, restaurant_id: int, message: str) -> str:
    """
    Fallback path for free-form owner messages that don't match a known
    keyword command. Runs a bounded tool-calling loop against the LLM and logs
    token usage to the token_usage table for per-tenant cost tracking.
    """
    from ai import llm_client, pii_scrub
    from ai.reasoning import grounding
    import feature_flags

    # Respect the global LLM kill-switch (FEATURE_AI_NARRATION=false) here too, so
    # one env flag disables every LLM code path — dashboard narration AND this
    # free-form fallback — for cost/incident control.
    if not feature_flags.is_enabled("ai_narration") or not llm_client.is_available():
        return "I didn't understand that. Reply HELP to see all commands."

    # Redact PII before the owner's free text leaves the process for the LLM.
    # known_names extends the phone/M-Pesa/PIN patterns to this restaurant's
    # on-record customer/staff names (audit remediation, Tier 3 item 8).
    known_names = pii_scrub.known_names_for_restaurant(db, restaurant_id)
    scrubbed = pii_scrub.scrub_for_llm(message, known_names)

    # Short-term memory (Phase 6), flag-gated. When on, prepend the recent
    # owner<->assistant turns so a follow-up ("and last week?") has context.
    # Default off -> history is [], behaviour identical to the stateless path.
    from ai.whatsapp import conversation
    use_memory = feature_flags.is_enabled("conversation_memory")
    history = conversation.load_recent(db, restaurant_id) if use_memory else []
    messages = history + [{"role": "user", "content": scrubbed}]

    # Every figure the model is allowed to state must trace to a deterministic
    # tool result it was actually handed. We accumulate the numbers from those
    # results and redact any figure in the final reply that isn't among them —
    # the same number-faithfulness guarantee narrator.verify() gives the
    # dashboard, applied to this free-form path (which otherwise returned raw
    # model text straight to the owner). An empty set (model answered without
    # calling a tool) correctly redacts every cited figure, since none was
    # looked up.
    grounded_numbers: set = set()

    for _ in range(MAX_TOOL_TURNS):
        response = llm_client.chat_with_tools(
            messages=messages,
            tools=TOOLS,
            system=SYSTEM_PROMPT,
        )
        _log_usage(restaurant_id, response)

        if response.stop_reason != "tool_use":
            reply = "".join(b.text for b in response.content if b.type == "text")
            if reply:
                reply, ungrounded = grounding.redact_free_text(reply, grounded_numbers)
                if ungrounded:
                    logger.warning(
                        "[Orchestrator] redacted ungrounded numbers %s from reply",
                        ungrounded,
                    )
            final = reply or "I didn't understand that. Reply HELP to see all commands."
            # Persist the exchange (scrubbed user text + the grounded reply) so the
            # next message can build on it. Own session, never blocks the reply.
            if use_memory:
                conversation.save_turn(restaurant_id, "user", scrubbed)
                conversation.save_turn(restaurant_id, "assistant", final)
            return final

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            fn = _TOOL_DISPATCH.get(block.name)
            result_text = fn(db, restaurant_id) if fn else f"Unknown tool: {block.name}"
            # Scrub PII (e.g. the raw-phone fallback in winback/tonight summaries)
            # BEFORE it's grounded and appended to the next LLM turn. Runs before
            # collect_payload_numbers so money/percent figures still survive for
            # grounding — only phone/code/PIN/ID patterns are stripped.
            result_text = pii_scrub.scrub_for_llm(result_text, known_names)
            grounded_numbers |= grounding.collect_payload_numbers(result_text)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
            })
        messages.append({"role": "user", "content": tool_results})

    return "That took too many steps to answer — try a more specific question, or reply HELP."


def _log_usage(restaurant_id: int, response) -> None:
    """
    Records one LLM turn's token usage. Uses its own short-lived session (lazy
    SessionLocal import so tests that swap the DB engine pick up the current
    one) so metering never commits or interferes with the caller's request
    transaction.
    """
    from database import SessionLocal
    session = SessionLocal()
    try:
        session.add(models.TokenUsage(
            restaurant_id=restaurant_id,
            llm_model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        ))
        session.commit()
    except Exception as exc:
        logger.warning(f"[Orchestrator] Failed to log token usage: {exc}")
    finally:
        session.close()
