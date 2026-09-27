"""Keep the curated analytical question bank aligned with backend routing."""
from __future__ import annotations

import pathlib
import re

import pytest

from routers.ai_ask import _route

SUGGESTIONS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "osSuggestions.ts"

# Question family -> the route that owns its live analysis. Broad and planned
# families are intentionally excluded from module routing assertions.
GROUP_MODULE = {
    "Profit": "profit", "Sales": "revenue", "Menu": "menu", "Prices": "pricing",
    "Stock": "stock", "Kitchen": "kitchen", "Orders": "ops", "Bookings": "bookings",
    "Staff": "staff",
}

AMBIGUOUS: dict[str, set[str]] = {
    "What are my best-selling items?": {"revenue", "menu"},
    "Which items make me the most money?": {"menu", "profit", "revenue"},
    "Which orders are taking too long?": {"ops", "kitchen"},
    "How is labor affecting my profit?": {"staff", "profit"},
}


def _load() -> list[tuple[str, str]]:
    src = SUGGESTIONS.read_text(encoding="utf-8")
    src = src.split("const DATA_QUESTIONS", 1)[1].split("const SOURCE_GROUPS", 1)[0]
    out: list[tuple[str, str]] = []
    pattern = r'^\s*(?:"([^\"]+)"|([A-Za-z ]+)):\s*\[([^\]]*)\],?\s*$'
    for quoted_name, bare_name, block in re.findall(pattern, src, re.M):
        name = quoted_name or bare_name.strip()
        module = GROUP_MODULE.get(name)
        if module:
            out.extend((q, module) for q in re.findall(r'"([^\"]{8,})"', block))
    return out


CASES = _load()


def test_the_suggestions_file_was_found_and_question_groups_parse():
    assert SUGGESTIONS.exists(), f"missing {SUGGESTIONS}"
    assert len(CASES) >= 40, f"only parsed {len(CASES)} questions — parser drifted?"


@pytest.mark.parametrize("question,expected", CASES, ids=[case[0] for case in CASES])
def test_built_in_question_routes_to_its_module(question: str, expected: str):
    got = _route(question)
    allowed = AMBIGUOUS.get(question, {expected})
    assert got in allowed, f"{question!r} routed to {got!r}; expected one of {sorted(allowed)}"


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
