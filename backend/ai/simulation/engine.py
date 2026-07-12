"""
backend/ai/simulation/engine.py
─────────────────────────────────
The "what if…" Simulation Engine — deterministic, no LLM.

Given a proposed change (raise/lower an item's price, run a promo discount, or
absorb a supplier cost change) it projects the effect on sales volume, profit,
margin and a customer-satisfaction proxy, with a confidence score and a
YES / CAUTION / NO verdict.

Grounding rules (directives/012):
  • It reuses the SAME demand signal the pricing agent already computes
    (ai/pricing/analysis.fetch_item_velocities) — the item's own 30-day,
    anchor-windowed velocity. It never invents a baseline.
  • The demand response uses a bounded constant-elasticity model. Own-price
    elasticity for restaurant items sits roughly in [-1.2, -0.4]; we centre on
    -0.7 and tilt it per item by that item's own recent velocity (a dish selling
    hot is less price-sensitive than one that's already slow). The elasticity
    used is always returned, so the assumption is auditable, never hidden.
  • The satisfaction figure is explicitly a PROXY (a heuristic reading of how a
    price move lands with diners), labelled as such — not a measured metric.

Money is integer cents throughout. All projections are monthly (×30 days) to
match how the pricing agent reports `monthly_impact_cents`.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from time_utils import utcnow
from ai.analysis_clock import analysis_anchor
from ai.pricing.analysis import fetch_item_velocities, MIN_MARGIN_PCT

# ── Demand model constants (explicit + documented, not buried in a formula) ────
BASE_ELASTICITY = -0.7          # own-price elasticity at normal (baseline) velocity
ELASTICITY_MIN, ELASTICITY_MAX = -1.2, -0.4   # clamp — never outside sane bounds
DAYS_IN_MONTH = 30

# Confidence anchors on how much history backs the item's velocity.
_CONF_BY_DATA_DAYS = [(30, 80), (14, 65), (7, 45)]   # (min_days, confidence)
_CONF_FLOOR, _CONF_CEIL = 20, 90


def _effective_elasticity(velocity_ratio: float) -> float:
    """
    Tilt the base elasticity by the item's own recent velocity. A dish selling
    ABOVE its baseline (ratio > 1) is running hot → less price-sensitive (toward
    -0.4). One selling BELOW baseline (ratio < 1) is fragile → more sensitive
    (toward -1.2). At ratio 1.0 this is exactly BASE_ELASTICITY.
    """
    tilted = BASE_ELASTICITY * (2.0 - max(0.3, min(1.7, velocity_ratio)))
    return max(ELASTICITY_MIN, min(ELASTICITY_MAX, tilted))


def _confidence(data_days: int, price_change_pct: float) -> int:
    """More history → more confident; larger price moves → less (elasticity is a
    LOCAL approximation, unreliable far from the current price)."""
    base = _CONF_FLOOR
    for min_days, conf in _CONF_BY_DATA_DAYS:
        if data_days >= min_days:
            base = conf
            break
    # Penalise big moves: elasticity extrapolation degrades past ~15%.
    penalty = max(0, abs(price_change_pct) - 15) * 1.5
    return int(max(_CONF_FLOOR, min(_CONF_CEIL, base - penalty)))


def _satisfaction_delta(price_change_pct: float) -> float:
    """
    Heuristic PROXY (not a measured metric): raising a price nudges diner
    satisfaction down, a discount nudges it up (asymmetrically — people notice
    increases more than discounts). Bounded to a sane range.
    """
    if price_change_pct >= 0:
        return round(max(-15.0, -price_change_pct * 0.5), 1)
    return round(min(8.0, -price_change_pct * 0.25), 1)


def _item_baseline(db: Session, restaurant_id: int, item_id: int) -> dict:
    """
    Daily/monthly baseline demand for one item from its 30-day anchored window.
    Prefers the pricing agent's velocity (identical windowing); falls back to a
    direct count when the item has too few orders for velocity to be computed.
    """
    velocities = fetch_item_velocities(db, restaurant_id)
    vel = velocities.get(item_id)
    if vel is not None:
        return {
            "daily_qty": vel.avg_daily_baseline,
            "qty_30d": vel.qty_30d,
            "data_days": vel.data_days,
            "velocity_ratio": vel.velocity_ratio,
        }

    # Fallback: light direct query over the same anchored 30-day window.
    anchor = analysis_anchor(db, restaurant_id)
    since = anchor - timedelta(days=30)
    qty = (
        db.query(func.coalesce(func.sum(models.OrderItem.quantity), 0))
        .join(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= since,
            models.OrderItem.menu_item_id == item_id,
        )
        .scalar()
    ) or 0
    return {
        "daily_qty": qty / 30.0,
        "qty_30d": int(qty),
        "data_days": 0,          # unknown / thin — confidence will reflect this
        "velocity_ratio": 1.0,
    }


def _verdict(profit_delta: int, projected_margin_pct: float,
             satisfaction_delta: float, breaches_floor: bool) -> tuple[str, str]:
    if breaches_floor:
        return "NO", (
            f"Projected margin {projected_margin_pct:.0f}% falls below the "
            f"{MIN_MARGIN_PCT:.0f}% healthy floor."
        )
    if profit_delta > 0 and satisfaction_delta >= -10:
        return "YES", "Projected to raise monthly profit with limited customer-perception risk."
    if profit_delta > 0:
        return "CAUTION", "Profit rises, but the price move is large enough to dent diner satisfaction — test it."
    if profit_delta == 0:
        return "CAUTION", "Roughly profit-neutral — little upside for the effort/risk."
    return "NO", "Projected to reduce monthly profit."


def simulate_price_change(
    db: Session,
    restaurant_id: int,
    item_id: int,
    new_price_cents: int,
) -> dict:
    """
    Project the effect of setting `item_id`'s price to `new_price_cents`.
    A promo/discount is just a price_change to a lower price; a cost change is
    handled by simulate_cost_change below.
    """
    item = (
        db.query(models.MenuItem)
        .filter(models.MenuItem.id == item_id,
                models.MenuItem.restaurant_id == restaurant_id)
        .first()
    )
    if item is None:
        return {"available": False, "error": "Menu item not found for this restaurant."}

    current_price = item.price
    cost = item.cost_price or 0
    if current_price <= 0:
        return {"available": False, "error": "Item has no current price to simulate against."}
    new_price = int(new_price_cents)
    if new_price <= 0:
        return {"available": False, "error": "Proposed price must be positive."}

    baseline = _item_baseline(db, restaurant_id, item_id)
    price_change_pct = (new_price - current_price) / current_price * 100

    elasticity = _effective_elasticity(baseline["velocity_ratio"])
    demand_change_pct = elasticity * price_change_pct
    # Demand can't go negative; a >100% projected drop is clamped to ~0 sales.
    demand_factor = max(0.0, 1.0 + demand_change_pct / 100.0)

    base_daily = baseline["daily_qty"]
    proj_daily = base_daily * demand_factor

    base_profit_month = int(base_daily * (current_price - cost) * DAYS_IN_MONTH)
    proj_profit_month = int(proj_daily * (new_price - cost) * DAYS_IN_MONTH)
    base_rev_month = int(base_daily * current_price * DAYS_IN_MONTH)
    proj_rev_month = int(proj_daily * new_price * DAYS_IN_MONTH)

    base_margin = (current_price - cost) / current_price * 100
    proj_margin = (new_price - cost) / new_price * 100 if new_price else 0.0

    satisfaction_delta = _satisfaction_delta(price_change_pct)
    profit_delta = proj_profit_month - base_profit_month
    # Only a downward margin move that crosses under the floor is a hard no.
    breaches_floor = proj_margin < MIN_MARGIN_PCT and proj_margin < base_margin
    verdict, reason = _verdict(profit_delta, proj_margin, satisfaction_delta, breaches_floor)

    return {
        "available": True,
        "change": {
            "type": "price_change",
            "item_id": item_id,
            "item_name": item.name,
            "current_price": current_price,
            "new_price": new_price,
            "price_change_pct": round(price_change_pct, 1),
        },
        "baseline": {
            "daily_qty": round(base_daily, 2),
            "monthly_qty": round(base_daily * DAYS_IN_MONTH, 1),
            "monthly_revenue_cents": base_rev_month,
            "monthly_profit_cents": base_profit_month,
            "margin_pct": round(base_margin, 1),
        },
        "projected": {
            "daily_qty": round(proj_daily, 2),
            "monthly_qty": round(proj_daily * DAYS_IN_MONTH, 1),
            "monthly_revenue_cents": proj_rev_month,
            "monthly_profit_cents": proj_profit_month,
            "margin_pct": round(proj_margin, 1),
        },
        "deltas": {
            "sales_pct": round((demand_factor - 1) * 100, 1),
            "profit_cents_month": profit_delta,
            "revenue_cents_month": proj_rev_month - base_rev_month,
            "margin_pct_points": round(proj_margin - base_margin, 1),
            "satisfaction_pct_points": satisfaction_delta,
        },
        "elasticity_used": round(elasticity, 2),
        "confidence_pct": _confidence(baseline["data_days"], price_change_pct),
        "verdict": verdict,
        "verdict_reason": reason,
        "assumptions": [
            f"Own-price elasticity {round(elasticity, 2)} (tilted by this item's recent velocity {round(baseline['velocity_ratio'], 2)}x).",
            f"Baseline demand {round(base_daily, 2)} units/day from the last 30 days of orders.",
            "Satisfaction is a heuristic proxy, not a measured metric.",
        ],
    }


def simulate_cost_change(
    db: Session,
    restaurant_id: int,
    item_id: int,
    new_cost_cents: int,
    pass_through: bool = False,
) -> dict:
    """
    Project a supplier ingredient-cost change on an item. If pass_through is
    False (default) the price is held and profit absorbs the change; if True the
    price is lifted to keep the current margin, and demand responds via the
    price-change model.
    """
    item = (
        db.query(models.MenuItem)
        .filter(models.MenuItem.id == item_id,
                models.MenuItem.restaurant_id == restaurant_id)
        .first()
    )
    if item is None:
        return {"available": False, "error": "Menu item not found for this restaurant."}

    current_price = item.price
    old_cost = item.cost_price or 0
    new_cost = int(new_cost_cents)
    baseline = _item_baseline(db, restaurant_id, item_id)
    base_daily = baseline["daily_qty"]

    if not pass_through:
        # Price held; profit absorbs the delta at unchanged demand.
        base_profit = int(base_daily * (current_price - old_cost) * DAYS_IN_MONTH)
        proj_profit = int(base_daily * (current_price - new_cost) * DAYS_IN_MONTH)
        proj_margin = (current_price - new_cost) / current_price * 100 if current_price else 0.0
        base_margin = (current_price - old_cost) / current_price * 100 if current_price else 0.0
        profit_delta = proj_profit - base_profit
        breaches_floor = proj_margin < MIN_MARGIN_PCT and proj_margin < base_margin
        verdict, reason = _verdict(profit_delta, proj_margin, 0.0, breaches_floor)
        return {
            "available": True,
            "change": {
                "type": "cost_change",
                "item_id": item_id,
                "item_name": item.name,
                "old_cost": old_cost,
                "new_cost": new_cost,
                "pass_through": False,
            },
            "baseline": {"monthly_profit_cents": base_profit, "margin_pct": round(base_margin, 1)},
            "projected": {"monthly_profit_cents": proj_profit, "margin_pct": round(proj_margin, 1)},
            "deltas": {
                "profit_cents_month": profit_delta,
                "margin_pct_points": round(proj_margin - base_margin, 1),
            },
            "confidence_pct": _confidence(baseline["data_days"], 0.0),
            "verdict": verdict,
            "verdict_reason": reason,
            "assumptions": [
                "Price held; demand unchanged; profit absorbs the full cost change.",
                f"Baseline demand {round(base_daily, 2)} units/day (last 30 days).",
            ],
        }

    # Pass-through: lift price to restore the current margin, then run the
    # price-change demand model on that new price.
    base_margin_frac = (current_price - old_cost) / current_price if current_price else 0.0
    new_price = int(round(new_cost / max(1 - base_margin_frac, 0.01)))
    result = simulate_price_change(db, restaurant_id, item_id, new_price)
    if result.get("available"):
        result["change"]["type"] = "cost_change_pass_through"
        result["change"]["old_cost"] = old_cost
        result["change"]["new_cost"] = new_cost
        result["assumptions"].insert(
            0, f"Price lifted to KES {new_price // 100:,} to hold the current "
               f"{base_margin_frac * 100:.0f}% margin after the cost change.")
    return result
