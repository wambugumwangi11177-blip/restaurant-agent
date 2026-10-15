"""
backend/ai/labor/intelligence.py
──────────────────────────────────
Labor Intelligence Agent — Layer 4.

What it does:
  1. Labor cost % analysis (labor cost / revenue) — target <30%
  2. Sales per employee hour (productivity metric)
  3. Overtime detection and cost projection
  4. Understaffed / overstaffed period identification
  5. Shift coverage recommendations based on revenue forecast

Why this matters:
  Labor is 25-35% of restaurant revenue. A restaurant doing
  KES 500k/month with 35% labor cost is KES 25k above target.
  That's the difference between profit and loss.
"""

from datetime import datetime, timedelta, date
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func
import models
from ai.analysis_clock import analysis_anchor
from owner.settings import Settings, resolve
from time_utils import eat_date

# The wages target (default 30% of sales — a placeholder to confirm with the first owner) and the hour after
# which overtime applies (default 8) are the owner's settings: labour_target_pct, overtime_after_hours.


def get_labor_intelligence(db: Session, restaurant_id: int, settings: Settings | None = None) -> dict:
    """Complete labor analytics for the last 30 days. `settings` defaults to the restaurant's saved thresholds."""
    settings = resolve(db, restaurant_id, settings)
    # Anchored to the restaurant's most recent order, not wall-clock time —
    # see ai/analysis_clock.py.
    now              = analysis_anchor(db, restaurant_id)
    thirty_days_ago  = now - timedelta(days=30)

    shifts = db.query(models.LaborShift).filter(
        models.LaborShift.restaurant_id == restaurant_id,
        models.LaborShift.shift_date    >= thirty_days_ago.date(),
    ).all()

    revenue_30d = db.query(func.sum(models.Order.total)).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.status        != models.OrderStatus.CANCELLED,
        models.Order.created_at    >= thirty_days_ago,
    ).scalar() or 0

    if not shifts:
        return _empty_response(revenue_30d)

    # ── Core metrics ──────────────────────────────────────────────────────────
    total_labor_cost  = sum(s.labor_cost or 0 for s in shifts)
    total_hours       = sum(s.actual_hours or s.scheduled_hours or 0 for s in shifts)
    labor_pct         = (total_labor_cost / max(revenue_30d, 1)) * 100
    sales_per_hour    = revenue_30d / max(total_hours, 1)

    # ── Overtime analysis ─────────────────────────────────────────────────────
    overtime_shifts   = [s for s in shifts if (s.actual_hours or 0) > settings.overtime_after_hours]
    overtime_hours    = sum(max(0, (s.actual_hours or 0) - settings.overtime_after_hours) for s in overtime_shifts)
    # D10: the overtime hours at the shift's own hourly rate (cost ÷ hours worked), not the whole shift's cost.
    overtime_cost     = int(round(sum(
        (max(0, (s.actual_hours or 0) - settings.overtime_after_hours)) * ((s.labor_cost or 0) / (s.actual_hours or 1))
        for s in overtime_shifts)))

    # ── Daily labor vs revenue ─────────────────────────────────────────────────
    daily_data: dict[date, dict] = defaultdict(lambda: {"labor": 0, "hours": 0, "revenue": 0})
    for s in shifts:
        d = s.shift_date
        daily_data[d]["labor"]  += s.labor_cost or 0
        daily_data[d]["hours"]  += s.actual_hours or s.scheduled_hours or 0

    # Fill in revenue per day
    # D17: bucket into the owner's (Nairobi) days in Python. `func.date(created_at)` over the naive-UTC column
    # returns the UTC date, which puts everything sold between 00:00 and 03:00 Nairobi time on the wrong day.
    daily_rev: dict[date, int] = defaultdict(int)
    for created_at, total in db.query(models.Order.created_at, models.Order.total).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.status        != models.OrderStatus.CANCELLED,
        models.Order.created_at    >= thirty_days_ago,
    ).all():
        daily_rev[eat_date(created_at)] += total or 0

    for d, rev in daily_rev.items():
        daily_data[d]["revenue"] = rev

    daily_breakdown = sorted([
        {
            "date":       str(d),
            "day":        d.strftime("%A"),
            "labor_cost": data["labor"],
            "hours":      round(data["hours"], 1),
            "revenue":    data["revenue"],
            "labor_pct":  round((data["labor"] / max(data["revenue"], 1)) * 100, 1),
        }
        for d, data in daily_data.items()
    ], key=lambda x: x["date"])

    # ── Staff productivity ─────────────────────────────────────────────────────
    staff_metrics = _staff_productivity(db, shifts, thirty_days_ago, restaurant_id)

    # ── Recommendations ────────────────────────────────────────────────────────
    recommendations = _generate_recommendations(
        labor_pct, overtime_hours, staff_metrics, daily_breakdown, settings
    )

    return {
        "summary": {
            "total_labor_cost_30d":  total_labor_cost,
            "total_hours_30d":       round(total_hours, 1),
            "total_revenue_30d":     revenue_30d,
            "labor_pct":             round(labor_pct, 1),
            "labor_status":          "HEALTHY" if labor_pct <= settings.labour_target_pct else "HIGH",
            "sales_per_hour":        int(sales_per_hour),
            "overtime_hours_30d":    round(overtime_hours, 1),
            "overtime_cost_30d":     overtime_cost,
            "shifts_logged":         len(shifts),
        },
        "daily_breakdown":   daily_breakdown[-14:],   # Last 14 days
        "staff_productivity": staff_metrics,
        "recommendations":   recommendations,
    }


def _staff_productivity(
    db: Session,
    shifts: list,
    since: datetime,
    restaurant_id: int,
) -> list[dict]:
    """Revenue-per-hour by staff member."""
    staff_map: dict[int, dict] = {}
    for s in shifts:
        if s.staff_member_id not in staff_map:
            staff_map[s.staff_member_id] = {"hours": 0, "cost": 0, "name": ""}
        staff_map[s.staff_member_id]["hours"] += s.actual_hours or s.scheduled_hours or 0
        staff_map[s.staff_member_id]["cost"]  += s.labor_cost or 0
        if s.staff_member:
            staff_map[s.staff_member_id]["name"] = s.staff_member.name

    # Revenue during their shifts (approximation: total revenue / total hours * their hours)
    total_hours = sum(v["hours"] for v in staff_map.values()) or 1
    total_revenue = db.query(func.sum(models.Order.total)).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.status        != models.OrderStatus.CANCELLED,
        models.Order.created_at    >= since,
    ).scalar() or 0

    revenue_per_hour = total_revenue / max(total_hours, 1)

    return sorted([
        {
            "staff_name":    data["name"] or f"Staff #{sid}",
            "hours_worked":  round(data["hours"], 1),
            "labor_cost":    data["cost"],
            "est_revenue_generated": int(data["hours"] * revenue_per_hour),
            "cost_pct_of_revenue":   round((data["cost"] / max(data["hours"] * revenue_per_hour, 1)) * 100, 1),
        }
        for sid, data in staff_map.items()
    ], key=lambda x: x["hours_worked"], reverse=True)


def _generate_recommendations(
    labor_pct: float,
    overtime_hours: float,
    staff_metrics: list,
    daily_breakdown: list,
    settings: Settings,
) -> list[dict]:
    recs = []
    if labor_pct > settings.labour_target_pct:
        excess_pct = round(labor_pct - settings.labour_target_pct, 1)
        recs.append({
            "priority": "HIGH",
            "message": f"Labor cost at {labor_pct:.1f}% — {excess_pct}% above {settings.labour_target_pct:g}% target",
            "action":  "Review scheduling: cut low-traffic shifts, reduce overtime",
        })
    if overtime_hours > 20:
        recs.append({
            "priority": "MEDIUM",
            "message": f"{overtime_hours:.0f} overtime hours in 30 days — costly and risks burnout",
            "action":  "Add part-time staff for peak periods instead of overtime",
        })
    # Find days with high labor % to identify over-staffing
    high_labor_days = [d for d in daily_breakdown if d["labor_pct"] > 40]
    if high_labor_days:
        days_str = ", ".join([d["day"] for d in high_labor_days[:3]])
        recs.append({
            "priority": "MEDIUM",
            "message": f"{len(high_labor_days)} days with >40% labor cost ({days_str})",
            "action":  "Review staffing levels on these days — revenue may not justify it",
        })
    return recs


def _empty_response(revenue_30d: int) -> dict:
    return {
        "summary": {
            "total_labor_cost_30d": 0, "total_hours_30d": 0,
            "total_revenue_30d": revenue_30d, "labor_pct": 0,
            "labor_status": "NO_DATA", "sales_per_hour": 0,
            "overtime_hours_30d": 0, "overtime_cost_30d": 0, "shifts_logged": 0,
        },
        "daily_breakdown": [], "staff_productivity": [],
        "recommendations": [{
            "priority": "INFO",
            "message": "No shift data recorded yet",
            "action": "Start logging staff shifts to unlock labor intelligence",
        }],
    }
