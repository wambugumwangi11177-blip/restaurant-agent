"""Keep the curated analytical question bank aligned with backend routing."""
from __future__ import annotations

import pathlib
import re

import pytest

from routers.ai_ask import _route

ASK_CATALOGUE = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "owner" / "ask.ts"

# The questions the OS offers to try, and where each must go: the form it is listed under and, for "what", the topic.
TOPIC_OF = {
    "Am I making a profit this month?": "money", "How is my cash count looking?": "cash", "How are my suppliers doing?": "suppliers",
    "What will run out soon?": "stock", "Which dishes earn the most?": "menu", "Which guests haven't come back?": "win_back",
}


def _load() -> list[tuple[str, str]]:
    """(question, form) for every example in ASK_FORMS (frontend/src/lib/owner/ask.ts)."""
    src = ASK_CATALOGUE.read_text(encoding="utf-8").split("export const ASK_FORMS", 1)[1].split("/** How a row's number", 1)[0]
    out: list[tuple[str, str]] = []
    for form, block in re.findall(r'\{ id: "(\w+)",.*?examples: \[(.*?)\] \}', src, re.S):
        out.extend((q, form) for q in re.findall(r'"((?:[^"\\]|\\.)+)"', block))
    return out


CASES = _load()


def test_the_question_catalogue_was_found_and_every_form_has_questions():
    assert ASK_CATALOGUE.exists(), f"missing {ASK_CATALOGUE}"
    assert {form for _q, form in CASES} == {"what", "why", "what_if", "what_to_do", "compare"}, "parser drifted?"
    assert len(CASES) >= 15


@pytest.mark.parametrize("question,form", CASES, ids=[case[0] for case in CASES])
def test_every_question_we_offer_is_answered_in_the_form_it_is_listed_under(question: str, form: str):
    from owner import ask
    got_form, got_topic = ask.classify(question)
    assert got_form == form, f"{question!r} would be answered as {got_form!r}, but is offered under {form!r}"
    if form == "what":
        assert got_topic == TOPIC_OF[question], f"{question!r} routed to {got_topic!r}"


@pytest.mark.parametrize("question,expected", [
    ("How can I increase my profit?", "profit"),
    ("Which items make me the most profit?", "profit"),
    ("Who is working today?", "staff"),
    ("How many customers are expected today?", "bookings"),
    ("How often are customers not showing up?", "bookings"),
    ("Which ingredients are at risk of expiring?", "stock"),
])
def test_specific_terms_beat_incidental_words(question: str, expected: str):
    assert _route(question) == expected


def test_an_unmatched_question_falls_back_to_general_operations():
    assert _route("What is the meaning of life?") == "ops"
