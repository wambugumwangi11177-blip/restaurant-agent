"""
backend/owner/kitchen.py — two small sums the kitchen and the market run on (docs/v2/SPEC.md §7 #11 and #12).

Pure functions, no database, no screen. They exist so the numbers in the client guide are reproduced by the product's own code (E2) and a later
screen (the staff entry screens, docs/v2/P7.md) has one place to ask.

  prep_raw_quantity   how much raw to take out to cook a number of portions, when cooking loses part of it (the cooked yield)
  market_list         what to buy: what the days ahead need, plus a buffer, less what is on the shelf; never below zero

Nothing in the recipes yet records a cooked yield, so the yield is passed in; where it should live (per recipe line) is a decision for the owner.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def _d(value: float | int | str) -> Decimal:
    return Decimal(str(value))


def prep_raw_quantity(portions: int, cooked_per_portion: float, yield_fraction: float, places: int = 2) -> float:
    """Raw to take out for `portions` of a dish that is served as `cooked_per_portion` and keeps `yield_fraction` of its raw weight when cooked.

    45 portions × 0.25 kg cooked ÷ 0.80 yield = 14.0625 → 14.06 kg raw (§7 #11). A yield of 1 means nothing is lost.
    """
    if portions < 0 or cooked_per_portion < 0:
        raise ValueError("portions and the cooked weight of one cannot be negative")
    if not 0 < yield_fraction <= 1:
        raise ValueError("a cooked yield is above 0 and at most 1 (0.80 means 80% is left after cooking)")
    raw = _d(portions) * _d(cooked_per_portion) / _d(yield_fraction)
    return float(raw.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def market_list(items: list[dict], places: int = 2) -> list[dict]:
    """What to buy for each item: `need + buffer − on_hand`, never below zero. Each item is {"item", "unit", "need", "buffer", "on_hand"}.

    beef 14 + 5 − 8 = 11 · chicken 60 + 20 − 32 = 48 · tomatoes 6 + 2 − 1 = 7 · rice 13.5 + 10 − 25 = −1.5 → 0 (§7 #12): stock already on the shelf
    covers rice, and a negative order is not an order.
    """
    out = []
    for it in items:
        need, buffer, on_hand = _d(it["need"]), _d(it.get("buffer", 0)), _d(it.get("on_hand", 0))
        if need < 0 or buffer < 0 or on_hand < 0:
            raise ValueError(f"{it.get('item', 'an item')}: need, buffer and on-hand cannot be negative")
        buy = max(need + buffer - on_hand, Decimal(0)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        out.append({**it, "buy": float(buy)})
    return out
