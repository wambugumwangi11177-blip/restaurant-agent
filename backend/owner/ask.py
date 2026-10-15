"""
backend/owner/ask.py — POST /owner/ask: Ask LEVIII (OS). A thin adapter over the deterministic handlers in
routers/ai_ask.py (docs/v2/SPEC.md §2). S1.4 delegates the "what" form; S5.1 adds why / what-if / what should I
do / compare on the same entry point.
"""
from __future__ import annotations

from owner.states import OwnerContext, block, iso


def topics() -> tuple[str, ...]:
    """The topics Ask LEVIII can answer deterministically today (the handlers in routers/ai_ask.py)."""
    from routers import ai_ask
    return tuple(ai_ask._HANDLERS)


def ask(ctx: OwnerContext, question: str) -> dict:
    from routers import ai_ask
    module = ai_ask._route(question)
    try:
        with ctx.db.begin_nested():
            card = ai_ask._HANDLERS[module](ctx.db, ctx.rid, question)
    except Exception:  # noqa: BLE001 — never substitute unrelated facts or expose internals
        card = ai_ask._unavailable_card(module)
    card = ai_ask._with_provenance(card, ctx.db, ctx.rid)
    answered = card.get("data", {}).get("available") is not False
    state = ctx.order_state() if answered else block("unavailable", reason="The data needed to answer this was not available.")
    return {"question": question, "form": "what", "topic": module, "state": state["state"], "as_of": state.get("as_of"),
            "answer": {k: card.get(k) for k in ("finding", "why", "impact", "recommendation", "steps", "data")}}
