"""
backend/ai/simulation/twin.py
───────────────────────────────
The Digital Twin — a forward projection of revenue that combines the
restaurant's own sales-history baseline (from revenue_forecaster) with the
exogenous calendar signals from signals.py (public holidays, school breaks, and
— once configured — weather/sports).

Deterministic. No LLM. The baseline and the exogenous adjustment are reported
SEPARATELY (baseline vs projected vs uplift) so the owner can always see how
much of the forecast is "your normal pattern" vs "because of the holiday."

Grounding: the baseline comes straight from revenue_forecaster (the same numbers
the /ai/revenue-forecast endpoint shows); the signal factors are the documented,
conservative assumptions in signals.py. Nothing is invented here.
"""

from __future__ import annotations

import math
from datetime import timedelta

from sqlalchemy.orm import Session

from time_utils import utcnow
from ai.revenue_forecaster import get_revenue_forecast
from .signals import demand_signals

MAX_HORIZON_DAYS = 90
GROWTH_DAMPENING = 0.3   # same dampening the 7-day forecaster uses


def forecast_twin(db: Session, restaurant_id: int, horizon_days: int = 30) -> dict:
    """Project revenue `horizon_days` forward with calendar signals applied."""
    horizon_days = max(1, min(MAX_HORIZON_DAYS, int(horizon_days)))

    base = get_revenue_forecast(db, restaurant_id)
    if not isinstance(base, dict) or base.get("error"):
        return {"available": False, "error": "Not enough revenue history to project."}

    weekly_pattern = base.get("weekly_pattern", [])
    daily_revenue = base.get("daily_revenue", [])
    trends = base.get("trends", {})

    day_map = {p["day"]: p["avg_revenue"] for p in weekly_pattern}
    revs = [d["revenue"] for d in daily_revenue]
    if not revs or not day_map:
        return {"available": False, "error": "Not enough revenue history to project."}

    mean_rev = sum(revs) / len(revs)
    std_dev = math.sqrt(sum((r - mean_rev) ** 2 for r in revs) / len(revs)) if len(revs) > 1 else mean_rev * 0.1
    growth_factor = 1 + (trends.get("week_over_week_growth", 0) / 100 * GROWTH_DAMPENING)

    today = utcnow()
    daily: list[dict] = []
    baseline_total = projected_total = 0
    low_total = high_total = 0
    signal_confidences: list[int] = []

    for i in range(1, horizon_days + 1):
        d = (today + timedelta(days=i)).date()
        day_name = (today + timedelta(days=i)).strftime("%A")
        base_day = day_map.get(day_name, int(mean_rev)) * growth_factor

        sig = demand_signals(d)
        factor = sig["factor"]
        projected_day = base_day * factor

        # ±0.7σ band, then widened by the signal's own uncertainty on signal days.
        spread = std_dev * 0.7
        if sig["reasons"]:
            spread += abs(projected_day - base_day)
            signal_confidences.append(sig["confidence"])

        baseline_total += base_day
        projected_total += projected_day
        low_total += max(0, projected_day - spread)
        high_total += projected_day + spread

        daily.append({
            "date": d.isoformat(),
            "day": day_name,
            "baseline_cents": int(base_day),
            "projected_cents": int(projected_day),
            "factor": factor,
            "reasons": sig["reasons"],
        })

    confidence = _confidence(len(revs), horizon_days, signal_confidences)
    factors = [row for row in daily if row["reasons"]]

    return {
        "available": True,
        "horizon_days": horizon_days,
        "generated_from": today.date().isoformat(),
        "summary": {
            "baseline_revenue_cents": int(baseline_total),
            "projected_revenue_cents": int(projected_total),
            "uplift_cents": int(projected_total - baseline_total),
            "uplift_pct": round((projected_total / baseline_total - 1) * 100, 1) if baseline_total else 0.0,
            "low_cents": int(low_total),
            "high_cents": int(high_total),
            "confidence_pct": confidence,
            "signal_days": len(factors),
        },
        "contributing_factors": factors,
        "daily": daily,
    }


def _confidence(data_points: int, horizon_days: int, signal_confidences: list[int]) -> int:
    """
    Blend three things: how much history backs the baseline, how far out we're
    projecting (further = less certain), and how sure we are about the calendar
    signals we applied. Bounded [20, 90].
    """
    data_conf = min(90, 40 + data_points * 2)
    horizon_penalty = min(30, horizon_days // 3)
    signal_conf = min(signal_confidences) if signal_confidences else 100
    return int(max(20, min(data_conf, signal_conf) - horizon_penalty))
