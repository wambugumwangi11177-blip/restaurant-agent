"""
backend/owner/menu_math.py — two small sums about prices that the spec's worked examples use (docs/v2/SPEC.md §7 #4 and #10).

Pure functions on integer cents, no database, no screen: what a dish must cost to earn a target share, and what a combo earns. They exist so the
numbers in the client guide can be reproduced to the cent by the product's own code (E2), and so a later screen has one place to ask.

  target_price_cents   the lowest price, on a price step, at which a dish keeps at least `margin_pct` of what it sells for
  month_gain_cents     what moving a price is worth in a month at a given number of plates
  combo_margin_pct     what a combo keeps once the dishes' own costs are paid

Nothing here has a default for a threshold: the price step, the share to keep and the floor are the owner's settings (`price_step_cents`,
`margin_target_pct`, `margin_floor_pct`, owner/settings.py, SPEC §0.3), so the caller passes them. The guide's #4 rounds to whole shillings (578)
while the product rounds to the owner's step (KES 5 by default: 580); both are right for their step, and the caller says which.
"""
from __future__ import annotations

import math
from fractions import Fraction


def _fraction(value: float | int | str) -> Fraction:
    return Fraction(str(value))


def target_price_cents(cost_cents: int, margin_pct: float, step_cents: int) -> int:
    """The lowest price (cents), a whole number of `step_cents`, at which a dish costing `cost_cents` keeps at least `margin_pct` of its price.

    260 / (1 − 0.45) = 577.78 → 578 on a KES 1 step (SPEC §7 #4), 580 on the default KES 5 step; 260 / 0.60 = 433.33 → 435 at 40% (§7 #3).
    Exact (fractions, not floats) and always rounded UP: a price below the target is not at the target.
    """
    if cost_cents < 0:
        raise ValueError("a cost cannot be negative")
    if not 0 <= margin_pct < 95:
        raise ValueError("the share to keep must be at least 0% and below 95%")
    if step_cents < 1:
        raise ValueError("a price step is at least one cent")
    exact = Fraction(cost_cents) / (1 - _fraction(margin_pct) / 100)
    return math.ceil(exact / step_cents) * step_cents


def month_gain_cents(price_from_cents: int, price_to_cents: int, plates_a_month: int) -> int:
    """What moving a price is worth in a month if as many plates are sold as before: (578 − 400) × 300 = KES 53,400 (§7 #4)."""
    if plates_a_month < 0:
        raise ValueError("plates cannot be negative")
    return (price_to_cents - price_from_cents) * plates_a_month


def combo_margin_pct(combo_price_cents: int, item_costs_cents: list[int] | tuple[int, ...]) -> float:
    """What a combo keeps out of every 100 it sells for, after the dishes' costs, to one decimal: (1,050 − 460) / 1,050 = 56.2% (§7 #10)."""
    if combo_price_cents <= 0:
        raise ValueError("a combo is sold for more than nothing")
    if len(item_costs_cents) < 2:
        raise ValueError("a combo is at least two dishes")
    if any(c < 0 for c in item_costs_cents):
        raise ValueError("a cost cannot be negative")
    return round(float((Fraction(combo_price_cents) - sum(item_costs_cents)) / combo_price_cents * 100), 1)


def combo_summary(item_prices_cents: list[int], combo_price_cents: int, item_costs_cents: list[int], margin_floor_pct: float) -> dict:
    """The combo in the terms the guide uses: the dishes alone, the combo, the discount, what it keeps, and whether that clears the owner's floor."""
    regular = sum(item_prices_cents)
    margin = combo_margin_pct(combo_price_cents, item_costs_cents)
    return {"regular_cents": regular, "combo_cents": combo_price_cents, "discount_cents": regular - combo_price_cents,
            "cost_cents": sum(item_costs_cents), "margin_pct": margin, "above_floor": margin >= margin_floor_pct}
