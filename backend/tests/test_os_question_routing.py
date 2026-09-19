"""
Every question the OS page offers must reach the module that can answer it.

These are buttons the owner presses. A misroute is not a subtle bug: they ask
"How can I increase my profit?" and get a pricing answer. Before the router was
scored by specificity, 8 of the 78 built-in questions landed on the wrong
module, because generic words in an earlier rule ("today", "increase") beat
specific words in a later one.

The expectations are parsed from the frontend's own osSuggestions.ts, so adding
a question there without a home here fails the build rather than shipping a
button that quietly answers the wrong thing.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from routers.ai_ask import _route

SUGGESTIONS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "lib" / "osSuggestions.ts"
)

# UI group -> the module that should answer it.
GROUP_MODULE = {
    "Profit": "profit",
    "Sales": "revenue",
    "Menu": "menu",
    "Prices": "pricing",
    "Stock": "stock",
    "Kitchen": "kitchen",
    "Orders": "ops",
    "Bookings": "bookings",
    "Staff": "staff",
}

# Questions with more than one defensible home. Naming them here is the honest
# alternative to bending the router until a single answer looks "right".
#   - best-sellers ARE menu engineering, though the UI files them under Sales
#   - an order stuck too long IS a kitchen question
#   - labour's effect on profit is answerable from either side
AMBIGUOUS: dict[str, set[str]] = {
    "What are my best-selling items?": {"revenue", "menu"},
    "Which items make me the most money?": {"menu", "profit", "revenue"},
    "Which orders are taking too long?": {"ops", "kitchen"},
    "How is labor affecting my profit?": {"staff", "profit"},
}


def _load() -> list[tuple[str, str]]:
    src = SUGGESTIONS.read_text(encoding="utf-8")
    out: list[tuple[str, str]] = []
    for name, block in re.findall(
        r'name:\s*"([^"]+)"\s*,\s*questions:\s*\[(.*?)\]', src, re.S
    ):
        module = GROUP_MODULE.get(name)
        if module is None:  # narrative groups with no single owning module
            continue
        for q in re.findall(r'"([^"]{8,})"', block):
            out.append((q, module))
    return out


CASES = _load()


def test_the_suggestions_file_was_actually_found():
    assert SUGGESTIONS.exists(), f"missing {SUGGESTIONS}"
    assert len(CASES) > 30, f"only parsed {len(CASES)} questions — parser drifted?"


@pytest.mark.parametrize("question,expected", CASES, ids=[c[0] for c in CASES])
def test_built_in_question_routes_to_its_module(question: str, expected: str):
    got = _route(question)
    allowed = AMBIGUOUS.get(question, {expected})
    assert got in allowed, (
        f"{question!r} routed to {got!r}; expected one of {sorted(allowed)}"
    )


# ── The specific misroutes that prompted the rewrite ─────────────────────────

@pytest.mark.parametrize("question,expected", [
    ("How can I increase my profit?", "profit"),          # "increase" had won for pricing
    ("Which items make me the most profit?", "profit"),   # "item" had won for menu
    ("Who is working today?", "staff"),                   # "today" had won for revenue
    ("How many customers are expected today?", "bookings"),
    ("How often are customers not showing up?", "bookings"),
    ("Which ingredients are at risk of expiring?", "stock"),  # "expire" never matched "expiring"
])
def test_previously_misrouted_questions(question: str, expected: str):
    assert _route(question) == expected


def test_a_specific_phrase_beats_an_incidental_word():
    """Scoring, not rule order, is what decides."""
    assert _route("Why is my kitchen slow?") == "kitchen"   # kitchen(7) > slow(4)
    assert _route("Which days are slow?") == "revenue"      # only revenue matches


def test_unmatched_question_falls_back_to_ops():
    assert _route("What is the meaning of life?") == "ops"
