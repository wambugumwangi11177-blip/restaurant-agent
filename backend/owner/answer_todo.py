"""
backend/owner/answer_todo.py — the "what should I do" form (docs/v2/SPEC.md §4 P5.1; the strategist's "goal mode").

It is Home's own ranking (owner/home.py::ranked_cards — what is happening now, then money already going out, then money you could make,
each by KES), so Ask LEVIII and Home cannot give different advice. With a goal in the question ("how can I find KES 20,000 more a
month?") the ideas are added up in that order until the goal is met; the sum is code, and every figure is an estimate and says so.
"""
from __future__ import annotations

import re

from owner import home
from owner.answers import assumption, from_setting, kes_text, make, nothing, row
from owner.states import OwnerContext

SHOWN = home.CARDS_SHOWN
_GOAL = re.compile(r"(?:kes|ksh|sh|ksh\.)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?\b", re.I)


def parse_goal(question: str) -> float | None:
    """A monthly figure the owner is after ("KES 20,000", "20k", "50 thousand"). A bare small number is not a goal."""
    for m in _GOAL.finditer(question):
        value = float(m.group(1).replace(",", ""))
        if m.group(2):
            value *= 1000
        if value >= 1000:
            return value
    return None


def build(ctx: OwnerContext, question: str) -> dict:
    base = ctx.order_state()
    cards = [home._card(c) for c in home.ranked_cards(ctx)]
    follow = ["Compare this week with last week", "Why were sales down yesterday?"]
    if not cards:
        reason = "Nothing is recorded yet to rank." if base["state"] == "no_data" else "Nothing is costing you money that we can see right now."
        return nothing("what_to_do", "what_to_do", question, reason, next=follow, goal_kes=None, covered_by=None, total_kes=None, ideas_counted=None)
    goal = parse_goal(question)
    priced = [c for c in cards if (c["kes_month"] or 0) > 0 and c["tier"] != "now"]
    covered_by, running, total = None, 0.0, 0.0
    if goal:
        for i, c in enumerate(priced, 1):
            running += c["kes_month"]
            if running >= goal:
                covered_by, total = i, round(running, 2)
                break
        else:
            total = round(running, 2)
    # "All 12 ideas add up to …" is only honest if those twelve are on the screen: when the goal is not met, every idea is shown.
    show = cards if goal and not covered_by else cards[: max(SHOWN, covered_by or 0)]
    rows = [row("idea", c["sentence"], c["kes_month"], "kes" if c["kes_month"] else "text",
                id=c["id"], action=c["action"], why=c["why"] or None, tier=c["tier"], domain=c["domain"]) for c in show]
    top = cards[0]
    if goal and covered_by:
        first = "the first idea" if covered_by == 1 else f"the first {covered_by} ideas"
        head = f"To find {kes_text(goal)} a month, do {first} below: together worth about {kes_text(total)} a month. Start with: {top['sentence']}."
    elif goal:
        head = (f"All {len(priced)} ideas I can put a figure on add up to about {kes_text(total)} a month, which is not enough to find {kes_text(goal)}. "
                f"Start with: {top['sentence']}.")
    elif top["kes_month"]:
        head = f"Start with: {top['sentence']} — about {kes_text(top['kes_month'])} a month."
    else:
        head = f"Start with: {top['sentence']}."
    assumptions = [assumption("Each figure is an estimate of what the idea is worth in a month, worked out from your own sales; it is not a promise.")]
    assumptions += from_setting(top.get("assumption"))
    if goal:
        assumptions.append(assumption("The ideas are added up in the order Home shows them: what is happening now, money already going out, then money you could make."))
    state = base if base["state"] != "no_data" else {"state": "live", "as_of": None}
    return make("what_to_do", "what_to_do", question, state=state["state"], as_of=state.get("as_of"), headline=head, rows=rows, assumptions=assumptions,
                next=follow, goal_kes=goal, covered_by=covered_by, total_kes=total if goal else None,
                ideas_counted=len(priced) if goal else None)
