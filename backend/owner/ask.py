"""
backend/owner/ask.py — POST /owner/ask: Ask LEVIII (OS), in five forms (docs/v2/SPEC.md §2, §4 P5.1).

    what         what is the position in one area          owner/answer_what.py    (old handlers + the blocks Home shows)
    why          why was that day bad                      owner/answer_why.py     (drivers in order: holiday, a top dish running out, staffing, cancelled sales)
    what_if      what happens if I change a price          owner/answer_whatif.py  (the simulator, its assumption shown)
    what_to_do   what should I do                          owner/answer_todo.py    (Home's ranking by KES; a goal adds the ideas up)
    compare      my branches, or this period vs the last   owner/answer_compare.py

The question is routed to a form and a topic by plain rules (`classify`): no model decides, and the owner can pick the form
themselves. Every answer has one shape (owner/answers.py) and its sentence is made from the numbers beside it. An engine that fails
gives an honest "could not be worked out", never another area's facts and never an error message.
"""
from __future__ import annotations

import logging
import re

from owner import answer_compare, answer_todo, answer_what, answer_whatif, answer_why
from owner.answers import FORMS, nothing
from owner.states import OwnerContext

logger = logging.getLogger("owner")

FORM_TOPICS = ("why", "what_if", "what_to_do", "compare")


def what_topics() -> tuple[str, ...]:
    """The areas the "what" form answers: the nine old handlers, then the areas answered from Home's blocks."""
    return answer_what.legacy_topics() + tuple(answer_what.AREA_TOPICS)


def topics() -> tuple[str, ...]:
    """Every topic Ask LEVIII answers (the registry's `os_topics` are names from here)."""
    return what_topics() + FORM_TOPICS


# ── routing: a question → (form, topic) ──────────────────────────────────────

_WHAT_IF = (r"\bwhat if\b", r"\bwhat would happen\b", r"\bwhat happens if\b", r"\bif i (?:raise|lower|cut|drop|increase|reduce|change|charge|put)\b",
            r"\bshould i (?:raise|lower|cut|drop|increase|reduce|charge)\b")
_COMPARE_EXPLICIT = (r"\bcompar", r"\bvs\.?\b", r"\bversus\b", r"\bbranch(?:es)?\b", r"\bdifference between\b")
_WHY = (r"^\s*why\b", r"\bwhy (?:is|are|was|were|did|do|does|has|have)\b", r"\bhow come\b", r"\bwhat happened\b", r"\bwhat went wrong\b",
        r"\breason for\b", r"\bwhat caused\b")
_COMPARE_SOFT = (r"\bbetter than\b", r"\bworse than\b", r"\bthan last\b", r"\bthan yesterday\b", r"\bthan before\b")
_WHAT_TO_DO = (r"\bwhat should i do\b", r"\bwhat can i do\b", r"\bwhat do i do\b", r"\bwhat to do\b", r"\bwhere (?:do|should) i start\b", r"\bhow (?:can|do|could|should) i\b",
               r"\bwhat next\b", r"\bprioriti", r"\bfocus on\b", r"\bmake more money\b", r"\bsave money\b", r"\badvice\b", r"\bbiggest win\b", r"\bfirst thing\b")

# area topics that are answered from Home's blocks: topic -> keywords (the longest keyword that appears scores)
_TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("things_to_check", ("things to check", "to check at", "voids", "void ", "cancelled sale", "cancelled order", "refund", "fraud", "suspicious", "unusual", "late-night", "late night")),
    ("mpesa", ("m-pesa", "mpesa", "m pesa", "mobile money", "my statement", "the statement")),
    ("cash", ("cash count", "cash check", "till short", "short on any", "drawer", "cash short", "counted", "cash")),
    ("suppliers", ("supplier", "short delivery", "purchase order", "delivered")),
    ("win_back", ("win back", "winning back", "come back", "came back", "haven't come", "lapsed", "regulars", "guests who")),
    ("savings", ("saved me", "savings", "return on", "roi")),
    ("data_trust", ("how complete", "complete are", "costs known", "missing cost", "data trust", "no cost yet", "trust my numbers")),
    ("money", ("profit and loss", "profit & loss", "p&l", "making a profit", "costs covered", "break-even", "break even", "bills", "rent", "licence", "license",
               "what i kept", "left after", "expenses")),
]


def _matches(patterns: tuple[str, ...], q: str) -> bool:
    return any(re.search(p, q) for p in patterns)


def classify_what(question: str) -> str:
    """The topic of a "what" question: the longest keyword wins; the areas answered from Home's blocks come before the old handlers on a tie."""
    from routers import ai_ask
    q = question.lower().replace("’", "'")
    best, score = "ops", 0
    for topic, keywords in [*_TOPIC_RULES, *ai_ask._ROUTING_RULES]:
        s = max((len(k) for k in keywords if k in q), default=0)
        if s > score and (topic in answer_what.AREA_TOPICS or topic in what_topics()):
            best, score = topic, s
    return best


def classify(question: str) -> tuple[str, str]:
    """-> (form, topic). A form that is not "what" is its own topic."""
    q = question.lower().replace("’", "'")
    if _matches(_WHAT_IF, q):
        return "what_if", "what_if"
    if _matches(_COMPARE_EXPLICIT, q):
        return "compare", "compare"
    if _matches(_WHY, q):
        return "why", "why"
    if _matches(_COMPARE_SOFT, q):
        return "compare", "compare"
    if _matches(_WHAT_TO_DO, q):
        return "what_to_do", "what_to_do"
    return "what", classify_what(question)


# ── the entry point ──────────────────────────────────────────────────────────

_BUILDERS = {
    "why": lambda ctx, q, topic: answer_why.build(ctx, q),
    "what_if": lambda ctx, q, topic: answer_whatif.build(ctx, q),
    "what_to_do": lambda ctx, q, topic: answer_todo.build(ctx, q),
    "compare": lambda ctx, q, topic: answer_compare.build(ctx, q),
    "what": lambda ctx, q, topic: answer_what.build(ctx, q, topic),
}


def ask(ctx: OwnerContext, question: str, form: str | None = None, topic: str | None = None) -> dict:
    """Answer `question` in `form` (chosen by the owner, else by the words of the question)."""
    question = question.strip()
    auto_form, auto_topic = classify(question)
    form = form or auto_form
    if form not in FORMS:
        raise ValueError(f"form must be one of {FORMS}")
    if form == "what":
        topic = topic if topic in what_topics() else (auto_topic if auto_form == "what" else classify_what(question))
    else:
        topic = form
    try:
        with ctx.db.begin_nested():
            return _BUILDERS[form](ctx, question, topic)
    except Exception:  # noqa: BLE001 — never substitute unrelated facts or expose internals
        logger.exception("ask LEVIII (%s/%s) failed for restaurant %s", form, topic, ctx.rid)
        return nothing(form, topic, question, "This could not be worked out just now.", state="unavailable")
