"""
backend/owner/answers.py — the one shape every Ask LEVIII answer has (docs/v2/SPEC.md §4 P5, §0.3).

    question · form · topic · topic_label · state · as_of · headline · rows · assumptions · next   (+ reason when there is nothing to say)

`headline` is the sentence the owner reads. It is written by code from the same values that sit in `rows`, `drivers` and
`columns`, so a number can only be in the sentence if it is in the data: `ungrounded()` checks exactly that, and the tests
run it on every form. The language model is never asked for a figure.

Money in a row is KES (the edge); the backend's integer cents never leave `owner/`.
"""
from __future__ import annotations

import re
from typing import Any

from owner.states import STATES

FORMS = ("what", "why", "what_if", "what_to_do", "compare")

TOPIC_LABELS = {
    "stock": "Stock", "revenue": "Sales", "bookings": "Bookings", "kitchen": "Kitchen speed", "staff": "Wages and staff",
    "menu": "Best and weakest dishes", "pricing": "Price ideas", "profit": "What each dish earns", "ops": "How the restaurant is doing",
    "cash": "Cash count check", "things_to_check": "Things to check at the till", "suppliers": "Suppliers",
    "win_back": "Winning guests back", "savings": "What LEVIII saved you", "data_trust": "How complete your costs are",
    "money": "Profit & Loss, costs covered, bills",
    "why": "Why", "what_if": "What if", "what_to_do": "What to do", "compare": "Compare",
}


def kes_text(value: float | None) -> str:
    return "KES —" if value is None else f"KES {value:,.0f}"


def day_text(day) -> str:
    """"Tuesday 20 Oct" — a Nairobi calendar day the way an owner says it."""
    return f"{day.strftime('%A')} {day.day} {day.strftime('%b')}"


def clock_text(local) -> str:
    """"6:57 pm" from a Nairobi-local datetime."""
    return f"{local.hour % 12 or 12}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"


def pct_text(value: float | None) -> str:
    if value is None:
        return "—"
    text = f"{value:.1f}"
    return (text[:-2] if text.endswith(".0") else text) + "%"


def row(key: str, label: str, value: float | int | None, unit: str, note: str | None = None, **extra: Any) -> dict:
    """One line of an answer. `unit`: kes · pct · pct_points · count · hours · kg · text (no number)."""
    return {"key": key, "label": label, "value": value, "unit": unit, **({"note": note} if note else {}), **extra}


def assumption(text: str, setting: str | None = None, value: Any = None) -> dict:
    """The rule an answer used, in words. When a setting owns the number, it is named, so the owner can change it."""
    out: dict[str, Any] = {"text": text}
    if setting is not None:
        out.update(setting=setting, value=value)
    return out


def setting_text(unit: str, value) -> str:
    """A setting's value the way the sheet writes it: "35%", "KES 200", "8 hours", "0.7"."""
    if unit == "KES":
        return f"KES {value:,.0f}"
    if unit == "%":
        return pct_text(value)
    return f"{value:g}" + (f" {unit}" if unit else "")


def from_setting(a: dict | None) -> list[dict]:
    """An engine block's `{setting, value, label}` as an answer assumption, the value written as the settings sheet writes it."""
    if not a:
        return []
    from owner.settings import BY_KEY
    spec = BY_KEY.get(a["setting"])
    shown = setting_text(spec.unit, a["value"]) if spec else f"{a['value']}"
    return [assumption(f"{a.get('label') or a['setting']}: {shown}", a["setting"], a["value"])]


def make(form: str, topic: str, question: str, *, state: str, headline: str, label: str | None = None, reason: str | None = None,
         rows: list[dict] | tuple = (), assumptions: list[dict] | tuple = (), next: list[str] | tuple = (), as_of: str | None = None,
         **extra: Any) -> dict:
    assert form in FORMS and state in STATES, (form, state)
    assert state not in ("no_data", "unavailable") or reason, "an answer that has nothing to say must say why"
    out: dict[str, Any] = {
        "question": question, "form": form, "topic": topic, "topic_label": label or TOPIC_LABELS.get(topic, topic),
        "state": state, "as_of": as_of, "headline": headline, "rows": list(rows), "assumptions": list(assumptions), "next": list(next),
    }
    if reason:
        out["reason"] = reason
    out.update(extra)
    return out


def nothing(form: str, topic: str, question: str, reason: str, *, state: str = "no_data", next: list[str] | tuple = (), **extra: Any) -> dict:
    """An honest answer when there is nothing to say: the reason is the sentence."""
    return make(form, topic, question, state=state, headline=reason, reason=reason, next=next, **extra)


# ── grounding ────────────────────────────────────────────────────────────────

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> list[float]:
    """Every number an owner would read in `text`, as written ("12,345.50" → 12345.5; "19:00" → 19, 0)."""
    return [float(m.replace(",", "")) for m in _NUMBER.findall(text or "") if m.strip(",")]


def _backing(node: Any, acc: set[float]) -> None:
    if isinstance(node, bool) or node is None:
        return
    if isinstance(node, (int, float)):
        acc.add(abs(float(node)))
    elif isinstance(node, str):
        acc.update(numbers_in(node))
    elif isinstance(node, dict):
        for key, value in node.items():
            if key not in ("headline", "question"):
                _backing(value, acc)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _backing(value, acc)


def ungrounded(answer: dict) -> list[float]:
    """The numbers in the sentence that no row, driver, column or assumption of the answer (nor the question) carries.
    A figure may be shown to 0, 1 or 2 decimals; zero is "nothing" and needs no backing; the number of rows (or of one kind of row) counts as shown."""
    have: set[float] = set()
    _backing({k: v for k, v in answer.items() if k != "answer"}, have)
    have.update(numbers_in(answer.get("question", "")))
    # how many rows there are, and how many of each kind, is on the screen too ("4 price ideas", "12 months")
    from collections import Counter
    for listing in ("rows", "drivers", "columns", "series"):
        items = [i for i in answer.get(listing) or [] if isinstance(i, dict)]
        have.add(float(len(items)))
        have.update(float(n) for n in Counter(i.get("key") for i in items).values())
    shown = {round(v, d) for v in have for d in (0, 1, 2)} | have
    stray = {n for n in numbers_in(answer.get("headline", "")) if n != 0 and not any(abs(n - h) < 1e-6 for h in shown)}
    return sorted(stray)
