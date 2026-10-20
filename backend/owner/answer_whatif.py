"""
backend/owner/answer_whatif.py — the "what if" form: what happens if I change a dish's price? (docs/v2/SPEC.md §4 P5.1)

The simulator (ai/simulation/engine.py) does the sums; this module only reads the question ("raise Chips to 350", "cut Burger by 10%",
"10% off Burger"), asks the simulator, and says the result in owner words with the assumption it used shown beside it. It never writes:
nothing about the menu changes, and a question it cannot read is asked again, not guessed.
"""
from __future__ import annotations

import re

import models
from sqlalchemy import func
from ai.simulation.engine import simulate_price_change
from owner.answers import assumption, kes_text, make, nothing, pct_text, row
from owner.states import OwnerContext

VERDICT_WORDS = {"YES": "Worth trying", "CAUTION": "Be careful", "NO": "Not worth it"}
_DOWN = ("cut", "lower", "drop", "reduce", "discount", "off", "decrease", "less", "cheaper", "down")
_UP = ("raise", "increase", "up", "higher", "add", "more", "rise", "hike")


def _dishes(ctx: OwnerContext) -> list[tuple[int, str, int]]:
    """The menu's priced dishes, the ones that sell most first (so the suggestions we offer are dishes worth trying a change on)."""
    sold = dict(ctx.db.query(models.OrderItem.menu_item_id, func.sum(models.OrderItem.quantity)).join(models.Order, models.Order.id == models.OrderItem.order_id).filter(
        models.Order.restaurant_id == ctx.rid).group_by(models.OrderItem.menu_item_id).all())
    items = ctx.db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == ctx.rid, models.MenuItem.price > 0).all()
    return [(m.id, m.name, m.price) for m in sorted(items, key=lambda m: (-(sold.get(m.id) or 0), m.name))]


_BEST_SELLER = re.compile(r"\b(?:best[- ]?sell(?:er|ing)|top[- ]?sell(?:er|ing)|most popular|top dish|biggest seller)\b")


def find_dish(question: str, dishes: list[tuple[int, str, int]]) -> tuple[int, str, int] | None:
    """The dish named in the question: its full name or the name without a bracket, longest match first. "My best seller" is the dish
    that sells most (`dishes` is in that order)."""
    q = question.lower()
    if dishes and _BEST_SELLER.search(q) and not any(d[1].lower() in q for d in dishes):
        return dishes[0]
    best = None
    for dish in dishes:
        for name in {dish[1].lower(), re.sub(r"\s*\(.*?\)\s*", " ", dish[1]).strip().lower()}:
            if name and name in q and (best is None or len(name) > best[0]):
                best = (len(name), dish)
    return best[1] if best else None


def _named(question: str) -> str | None:
    m = re.search(r"(?:price of|prices of|cost of|charge for|charging for|price for|change|raise|cut|lower|drop|reduce|increase)\s+(?:the\s+)?(?:price\s+(?:of|for)\s+)?"
                  r"([A-Za-z][A-Za-z' -]{2,40}?)(?:\s+(?:to|by|from|at|down|up)\b|\s*\d|\?|$)", question, re.I)
    if not m:
        return None
    name = m.group(1).strip()
    return None if name.lower() in ("the", "my", "price", "prices", "it", "a price") else name


def parse_price(question: str, current_cents: int) -> tuple[int | None, str]:
    """-> (new price in cents or None, how the owner said it). "by 10%" and "by KES 50" need a direction (cut / raise); "to 350" is the new price."""
    q = question.lower()
    pct = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent)", q)
    if pct:
        amount = float(pct.group(1))
        down = any(re.search(rf"\b{w}\b", q) for w in _DOWN)
        up = any(re.search(rf"\b{w}\b", q) for w in _UP)
        if down == up:
            return None, "direction"
        factor = 1 - amount / 100 if down else 1 + amount / 100
        return max(1, round(current_cents * factor / 100)) * 100, "percent"
    delta = re.search(r"\bby\s*(?:kes|ksh|sh)?\s*(\d[\d,]*(?:\.\d+)?)", q)
    if delta:
        amount = float(delta.group(1).replace(",", "")) * 100
        down = any(re.search(rf"\b{w}\b", q) for w in _DOWN)
        up = any(re.search(rf"\b{w}\b", q) for w in _UP)
        if down == up:
            return None, "direction"
        return max(100, round((current_cents - amount if down else current_cents + amount) / 100) * 100), "amount"
    fig = re.search(r"(?:\bto\b|\bat\b|\bkes\b|\bksh\b|\bsh\b)\s*(?:kes|ksh|sh)?\s*\.?\s*(\d[\d,]*(?:\.\d+)?)", q)
    if fig:
        return round(float(fig.group(1).replace(",", "")) * 100), "figure"
    return None, "missing"


def build(ctx: OwnerContext, question: str) -> dict:
    dishes = _dishes(ctx)
    suggestions = [f"What if I raise the price of {d[1]} by 10%?" for d in dishes[:3]]
    if not dishes:
        return nothing("what_if", "what_if", question, "There are no dishes with a price on your menu yet, so there is nothing to try a change on.")
    dish = find_dish(question, dishes)
    if dish is None:
        named = _named(question)
        reason = (f"I couldn't find a dish called \"{named}\" on your menu." if named
                  else "Tell me which dish and what new price, for example: What if I raise Chips to KES 350?")
        return nothing("what_if", "what_if", question, reason, state="unavailable", next=suggestions)
    dish_id, name, current = dish
    new_price, how = parse_price(question, current)
    if new_price is None:
        reason = (f"Do you mean a higher or a lower price for {name}? Say raise or cut, for example: What if I cut {name} by 10%?"
                  if how == "direction" else f"What new price for {name}? Say the price or a percentage, for example: What if I raise {name} to KES {current // 100 + 50}?")
        return nothing("what_if", "what_if", question, reason, state="unavailable", next=[f"What if I raise {name} by 10%?", f"What if I cut {name} by 10%?"])
    sim = simulate_price_change(ctx.db, ctx.rid, dish_id, new_price, ctx.settings)
    if not sim.get("available"):
        return nothing("what_if", "what_if", question, sim.get("error") or "The simulator could not run for this dish.", state="unavailable", next=suggestions)
    d, base, proj = sim["deltas"], sim["baseline"], sim["projected"]
    change = sim["change"]
    profit = d["profit_cents_month"] / 100.0
    verdict = VERDICT_WORDS[sim["verdict"]]
    fewer = d["sales_pct"]
    rows = [
        row("price_from", f"{name} now", current / 100.0, "kes"), row("price_to", f"{name} at", new_price / 100.0, "kes"),
        row("sales_change_pct", "Plates sold", fewer, "pct", "a rise in price is expected to sell fewer; a cut, more"),
        row("profit_change_month", "Profit a month", profit, "kes", "more if positive, less if negative"),
        row("margin_from", "Kept from each plate now", base["margin_pct"], "pct"), row("margin_to", "Kept from each plate then", proj["margin_pct"], "pct"),
        row("confidence", "How sure", sim["confidence_pct"], "pct", f"from {base['monthly_qty']:g} plates sold in the last 30 days"),
    ]
    direction = "fewer" if fewer < 0 else "more"
    more_less = "rise" if profit > 0 else "fall"
    head = (f"If the price of {name} goes from {kes_text(current / 100)} to {kes_text(new_price / 100)}, about {pct_text(abs(fewer))} {direction} plates would sell "
            f"and profit would {more_less} by about {kes_text(abs(profit))} a month. You would keep {pct_text(proj['margin_pct'])} of each plate's price, "
            f"{'up' if proj['margin_pct'] >= base['margin_pct'] else 'down'} from {pct_text(base['margin_pct'])}. {verdict}.")
    el = abs(sim["elasticity_used"])
    assumptions = [
        assumption(f"For every 10% on the price, about {el * 10:.0f}% fewer plates sell (your price sensitivity, adjusted for how fast {name} sells now).",
                   "price_sensitivity", ctx.settings.price_sensitivity),
        assumption(f"The starting point is {base['daily_qty']:g} plates a day, from the last 30 days of sales."),
        assumption("How guests react is a rough guide, not something measured; try a small change first."),
    ]
    state = ctx.order_state()
    return make("what_if", "what_if", question, state=state["state"], as_of=state.get("as_of"), headline=head, rows=rows, assumptions=assumptions,
                next=[f"What if I {'cut' if new_price > current else 'raise'} {name} by 10%?", "What should I do to make more money?"],
                verdict=verdict, dish=change["item_name"])
