"""
backend/ai/pricing/analysis.py
───────────────────────────────
Pure analytics layer for the Pricing Intelligence agent.
No DB writes. Read and compute only.

Fixes vs previous version:
  BUG-03  — All DB queries now use UTC (datetime.utcnow()) not EAT.
             EAT is used ONLY for display strings and DOW/hour bucketing
             of results. Mixing naive EAT with naive UTC in SQLAlchemy
             filter() caused a silent 3-hour window drop on every query.
  DS-01   — Cold-start guard: items with <14 days of data are restricted
             to REPRICE-only recommendations (margin floor violations).
             Velocity-based SURGE/STIMULATE require 14+ days of history
             to avoid false positives from brand-new items.
  DS-03   — Delivery margin check uses per-channel commission rates.
             (was already correct in the previous version — kept as-is)
  CLEAN   — Removed unused `timezone` import (EAT conversion now done
             with simple +3h offset on display, not on DB queries)
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import defaultdict
from datetime import datetime, timedelta
from typing import NamedTuple
import models
from ai.analysis_clock import analysis_anchor

# ── Constants ────────────────────────────────────────────────────────────────
SURGE_THRESHOLD         = 1.30
SLOW_THRESHOLD          = 0.60
MIN_MARGIN_PCT          = 40.0
MAX_FOOD_COST_PCT       = 35.0
MIN_ORDERS_FOR_VELOCITY = 5     # Minimum orders to compute velocity at all
MIN_DAYS_FOR_VELOCITY   = 14    # DS-01 FIX: minimum days of history for SURGE/STIMULATE
COOLDOWN_DAYS           = 7

DELIVERY_COMMISSIONS = {
    "uber_eats":  0.25,
    "glovo":      0.25,
    "bolt_food":  0.20,
}


class ItemVelocity(NamedTuple):
    item_id:             int
    qty_30d:             int
    data_days:           int       # DS-01: actual days with order data
    avg_daily_baseline:  float
    ewm_velocity:        float
    velocity_ratio:      float
    dow_qty:             dict
    hour_qty:            dict
    revenue_30d:         int
    recent_qty_7d:       int


def fetch_item_velocities(
    db: Session,
    restaurant_id: int,
) -> dict[int, ItemVelocity]:
    """
    Compute velocity metrics for every menu item.

    BUG-03 FIX: Uses datetime.utcnow() for all DB range filters.
    created_at is stored as naive UTC in the DB — never compare it to
    a naive EAT datetime or you silently lose 3 hours of data.

    EWM formula:
        recent_daily  = qty in last 7 days / 7
        prior_daily   = qty in days 8-30 / 23
        ewm = 0.7 * recent_daily + 0.3 * prior_daily
    """
    # Anchored to the restaurant's most recent order, not wall-clock time —
    # see ai/analysis_clock.py. Still UTC (BUG-03 fix preserved): orders are
    # stored as naive UTC, so the anchor and the comparison below must stay
    # in the same timezone-naive UTC space.
    now             = analysis_anchor(db, restaurant_id)
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago  = now - timedelta(days=7)
    alpha           = 0.7

    rows = (
        db.query(
            models.OrderItem.menu_item_id,
            models.OrderItem.quantity,
            models.OrderItem.unit_price,
            models.Order.created_at,
        )
        .join(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= thirty_days_ago,   # UTC comparison ✓
        )
        .all()
    )

    total_qty:    dict[int, int]            = defaultdict(int)
    recent_qty:   dict[int, int]            = defaultdict(int)
    prior_qty:    dict[int, int]            = defaultdict(int)
    dow_qty:      dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    hour_qty:     dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    item_revenue: dict[int, int]            = defaultdict(int)
    # DS-01: track distinct order dates per item to compute actual data age
    item_dates:   dict[int, set]            = defaultdict(set)

    for mid, qty, unit_price, created_at in rows:
        total_qty[mid]    += qty
        item_revenue[mid] += qty * unit_price
        item_dates[mid].add(created_at.date())

        # BUG-03: DOW/hour bucketing uses UTC hour offset by +3 for EAT display
        # The offset is applied only to the bucket label, not to the filter above
        eat_hour = (created_at.hour + 3) % 24
        dow_qty[mid][created_at.weekday()] += qty
        hour_qty[mid][eat_hour]            += qty    # Store in EAT hours for display

        if created_at >= seven_days_ago:             # UTC comparison ✓
            recent_qty[mid] += qty
        else:
            prior_qty[mid]  += qty

    velocities: dict[int, ItemVelocity] = {}
    for mid, qty_30d in total_qty.items():
        if qty_30d < MIN_ORDERS_FOR_VELOCITY:
            continue

        data_days    = len(item_dates[mid])
        recent_daily = recent_qty.get(mid, 0) / 7
        prior_daily  = prior_qty.get(mid, 0)  / 23
        ewm          = alpha * recent_daily + (1 - alpha) * prior_daily
        baseline     = qty_30d / 30
        ratio        = ewm / max(baseline, 0.001)

        velocities[mid] = ItemVelocity(
            item_id            = mid,
            qty_30d            = qty_30d,
            data_days          = data_days,
            avg_daily_baseline = baseline,
            ewm_velocity       = ewm,
            velocity_ratio     = ratio,
            dow_qty            = dict(dow_qty[mid]),
            hour_qty           = dict(hour_qty[mid]),
            revenue_30d        = item_revenue[mid],
            recent_qty_7d      = recent_qty.get(mid, 0),
        )

    return velocities


def items_on_cooldown(db: Session, restaurant_id: int) -> set[int]:
    """Return set of menu_item_ids with a PENDING/APPROVED rec in the last 7 days."""
    cutoff = datetime.utcnow() - timedelta(days=COOLDOWN_DAYS)   # BUG-03 FIX: UTC
    recs = (
        db.query(models.PricingRecommendation.menu_item_id)
        .filter(
            models.PricingRecommendation.restaurant_id == None,  # handled by caller
            models.PricingRecommendation.created_at >= cutoff,
            models.PricingRecommendation.status.in_(["PENDING", "APPROVED"]),
        )
        .all()
    )
    return {r.menu_item_id for r in recs}


def items_on_cooldown_for_restaurant(
    db: Session, restaurant_id: int
) -> set[int]:
    """Correct version with restaurant_id filter."""
    cutoff = datetime.utcnow() - timedelta(days=COOLDOWN_DAYS)
    recs = (
        db.query(models.PricingRecommendation.menu_item_id)
        .filter(
            models.PricingRecommendation.restaurant_id == restaurant_id,
            models.PricingRecommendation.created_at >= cutoff,
            models.PricingRecommendation.status.in_(["PENDING", "APPROVED"]),
        )
        .all()
    )
    return {r.menu_item_id for r in recs}


def analyse_item(
    item: models.MenuItem,
    vel: ItemVelocity,
    on_cooldown: bool,
) -> dict | None:
    """
    Compute a single pricing recommendation for one item.

    DS-01 FIX: Velocity-based recommendations (SURGE, STIMULATE) require
    at least MIN_DAYS_FOR_VELOCITY (14) days of actual order history.
    Items newer than this get only REPRICE recommendations (hard floor
    violations are always valid regardless of data age).
    """
    current_price = item.price
    cost          = item.cost_price or 0
    margin_pct    = ((current_price - cost) / max(current_price, 1)) * 100
    food_cost_pct = (cost / max(current_price, 1)) * 100

    is_weekend_heavy = (
        (vel.dow_qty.get(4, 0) + vel.dow_qty.get(5, 0) + vel.dow_qty.get(6, 0))
        > vel.qty_30d * 0.5
    ) if vel.qty_30d > 0 else False

    lunch_qty  = sum(vel.hour_qty.get(h, 0) for h in range(11, 15))
    dinner_qty = sum(vel.hour_qty.get(h, 0) for h in range(18, 23))
    daypart    = "dinner" if dinner_qty > lunch_qty else ("lunch" if lunch_qty > dinner_qty else "all_day")

    has_velocity_data = vel.data_days >= MIN_DAYS_FOR_VELOCITY   # DS-01

    base = {
        "item_id":            item.id,
        "item_name":          item.name,
        "category":           item.category,
        "current_price":      current_price,
        "cost_price":         cost,
        "margin_pct":         round(margin_pct, 1),
        "food_cost_pct":      round(food_cost_pct, 1),
        "qty_30d":            vel.qty_30d,
        "data_days":          vel.data_days,
        "avg_daily":          round(vel.avg_daily_baseline, 1),
        "ewm_velocity":       round(vel.ewm_velocity, 2),
        "velocity_ratio":     round(vel.velocity_ratio, 2),
        "is_weekend_heavy":   is_weekend_heavy,
        "dominant_daypart":   daypart,
        "revenue_30d":        vel.revenue_30d,
        "on_cooldown":        on_cooldown,
        "has_velocity_data":  has_velocity_data,
    }

    if on_cooldown:
        return base

    # ── SURGE (requires velocity data — DS-01) ───────────────────────────────
    if has_velocity_data and vel.velocity_ratio >= SURGE_THRESHOLD and margin_pct >= MIN_MARGIN_PCT:
        surge_pct       = min(15, round((vel.velocity_ratio - 1) * 20))
        suggested_price = _round_price(current_price * (1 + surge_pct / 100))
        new_food_cost   = (cost / max(suggested_price, 1)) * 100
        new_margin      = ((suggested_price - cost) / max(suggested_price, 1)) * 100

        if new_food_cost <= MAX_FOOD_COST_PCT and new_margin >= MIN_MARGIN_PCT:
            monthly_impact = int((suggested_price - current_price) * vel.avg_daily_baseline * 30)
            return {
                **base,
                "type":                    "SURGE",
                "suggested_price":         suggested_price,
                "price_change_pct":        round(surge_pct, 1),
                "reason":                  f"Selling {round(vel.velocity_ratio, 1)}x above baseline (EWM-smoothed) this week",
                "when":                    _describe_when(is_weekend_heavy, daypart),
                "monthly_impact_cents":    monthly_impact,
                "recommendation_strength": _surge_strength(vel.velocity_ratio, vel.qty_30d),
                "new_margin_pct":          round(new_margin, 1),
                "new_food_cost_pct":       round(new_food_cost, 1),
            }

    # ── REPRICE — margin floor violation (always valid, no velocity required) ─
    if margin_pct < MIN_MARGIN_PCT and cost > 0:
        target_price   = _round_price(cost / (1 - MIN_MARGIN_PCT / 100))
        new_food_cost  = (cost / max(target_price, 1)) * 100
        new_margin     = ((target_price - cost) / max(target_price, 1)) * 100
        monthly_impact = int((target_price - current_price) * vel.avg_daily_baseline * 30)

        return {
            **base,
            "type":                    "REPRICE",
            "suggested_price":         target_price,
            "price_change_pct":        round(((target_price - current_price) / max(current_price, 1)) * 100, 1),
            "reason":                  f"Margin at {round(margin_pct, 1)}% — below {MIN_MARGIN_PCT}% floor",
            "when":                    "All times",
            "monthly_impact_cents":    monthly_impact,
            "recommendation_strength": 85,
            "new_margin_pct":          round(new_margin, 1),
            "new_food_cost_pct":       round(new_food_cost, 1),
        }

    # ── STIMULATE (requires velocity data — DS-01) ───────────────────────────
    if has_velocity_data and 0 < vel.velocity_ratio <= SLOW_THRESHOLD and margin_pct >= 55:
        discount_pct    = 10
        suggested_price = _round_price(current_price * (1 - discount_pct / 100))
        new_margin      = ((suggested_price - cost) / max(suggested_price, 1)) * 100
        new_food_cost   = (cost / max(suggested_price, 1)) * 100

        if new_margin >= MIN_MARGIN_PCT and new_food_cost <= MAX_FOOD_COST_PCT:
            # DS-04 FIX: correct monthly impact extrapolation
            projected_daily = vel.avg_daily_baseline * 1.30
            monthly_impact  = int(
                ((projected_daily * suggested_price) - (vel.avg_daily_baseline * current_price)) * 30
            )
            return {
                **base,
                "type":                    "STIMULATE",
                "suggested_price":         suggested_price,
                "price_change_pct":        round(-discount_pct, 1),
                "reason":                  f"Selling {round(vel.velocity_ratio, 1)}x below baseline — discount to stimulate demand",
                "when":                    "This week only",
                "monthly_impact_cents":    monthly_impact,
                "recommendation_strength": _slow_strength(vel.velocity_ratio, vel.qty_30d),
                "new_margin_pct":          round(new_margin, 1),
                "new_food_cost_pct":       round(new_food_cost, 1),
            }

    return base   # Analytics only, no recommendation generated


def check_delivery_margins(
    items: list,
    velocities: dict[int, ItemVelocity],
) -> list[dict]:
    """Per-channel delivery margin check."""
    gaps = []
    for channel, commission in DELIVERY_COMMISSIONS.items():
        for item in items:
            if not item.cost_price:
                continue
            vel = velocities.get(item.id)
            if not vel or vel.qty_30d < MIN_ORDERS_FOR_VELOCITY:
                continue

            margin_pct       = ((item.price - item.cost_price) / max(item.price, 1)) * 100
            effective_margin = margin_pct - (commission * 100)
            required_price   = _round_price(
                item.cost_price / (1 - (MIN_MARGIN_PCT + commission * 100) / 100)
            )

            if effective_margin < MIN_MARGIN_PCT:
                gaps.append({
                    "channel":                    channel,
                    "item_name":                  item.name,
                    "current_price":              item.price,
                    "current_margin_pct":         round(margin_pct, 1),
                    "commission_pct":             round(commission * 100),
                    "effective_delivery_margin":  round(effective_margin, 1),
                    "recommended_delivery_price": required_price,
                    "issue": f"{channel.replace('_',' ').title()} commission erodes margin below {MIN_MARGIN_PCT}% floor",
                })

    gaps.sort(key=lambda x: x["effective_delivery_margin"])
    return gaps[:10]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _round_price(price_cents: float) -> int:
    rounded = round(price_cents / 50) * 50
    return int(max(rounded, 100))


def _describe_when(is_weekend_heavy: bool, daypart: str) -> str:
    parts = []
    if is_weekend_heavy:
        parts.append("weekends")
    if daypart == "dinner":
        parts.append("evenings")
    elif daypart == "lunch":
        parts.append("lunch hours")
    return (" & ".join(parts) or "all times").capitalize()


def _surge_strength(velocity_ratio: float, qty_30d: int) -> int:
    base         = min(90, int((velocity_ratio - 1) * 60 + 50))
    sample_bonus = min(10, qty_30d // 10)
    return min(98, base + sample_bonus)


def _slow_strength(velocity_ratio: float, qty_30d: int) -> int:
    base         = min(80, int((1 - velocity_ratio) * 70 + 40))
    sample_bonus = min(10, qty_30d // 10)
    return min(90, base + sample_bonus)
