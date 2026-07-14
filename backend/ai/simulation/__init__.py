"""
backend/ai/simulation/
─────────────────────────
Deterministic "what if…" simulation. `run_simulation` is the single entry point
the API and the CEO/Strategy agent call; it normalizes a loosely-typed change
request (price / promo / cost) into the strongly-typed engine functions.

No LLM here — pure projection math over the restaurant's own order history.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

import models
from .engine import simulate_price_change, simulate_cost_change  # noqa: F401
from .twin import forecast_twin  # noqa: F401


def _current_price(db: Session, restaurant_id: int, item_id: int) -> int | None:
    item = (
        db.query(models.MenuItem.price)
        .filter(models.MenuItem.id == item_id,
                models.MenuItem.restaurant_id == restaurant_id)
        .first()
    )
    return item[0] if item else None


def run_simulation(db: Session, restaurant_id: int, change: dict) -> dict:
    """
    Dispatch a change request to the right engine function.

    Accepted shapes:
      {"type": "price_change", "item_id": N, "new_price": cents}
      {"type": "price_change", "item_id": N, "change_pct": +/-float}
      {"type": "promo",        "item_id": N, "discount_pct": float}
      {"type": "cost_change",  "item_id": N, "new_cost": cents, "pass_through": bool}
      {"type": "cost_change",  "item_id": N, "cost_change_pct": float, "pass_through": bool}
    """
    if not isinstance(change, dict):
        return {"available": False, "error": "Provide a change object to simulate."}

    ctype = str(change.get("type", "")).lower()
    item_id = change.get("item_id")
    if not isinstance(item_id, int):
        return {"available": False, "error": "A numeric 'item_id' is required."}

    if ctype in ("price_change", "promo"):
        new_price = change.get("new_price")
        if new_price is None:
            current = _current_price(db, restaurant_id, item_id)
            if current is None:
                return {"available": False, "error": "Menu item not found for this restaurant."}
            if ctype == "promo":
                discount = float(change.get("discount_pct", 0) or 0)
                new_price = current * (1 - discount / 100.0)
            else:
                pct = float(change.get("change_pct", 0) or 0)
                new_price = current * (1 + pct / 100.0)
        return simulate_price_change(db, restaurant_id, item_id, int(round(float(new_price))))

    if ctype == "cost_change":
        new_cost = change.get("new_cost")
        if new_cost is None:
            item = (
                db.query(models.MenuItem.cost_price)
                .filter(models.MenuItem.id == item_id,
                        models.MenuItem.restaurant_id == restaurant_id)
                .first()
            )
            if item is None:
                return {"available": False, "error": "Menu item not found for this restaurant."}
            old_cost = item[0] or 0
            pct = float(change.get("cost_change_pct", 0) or 0)
            new_cost = old_cost * (1 + pct / 100.0)
        return simulate_cost_change(
            db, restaurant_id, item_id, int(round(float(new_cost))),
            pass_through=bool(change.get("pass_through", False)),
        )

    return {"available": False, "error": f"Unknown simulation type '{ctype}'."}
