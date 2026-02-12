"""
Revenue Forecasting Intelligence — EXHAUSTIVE
================================================================================
Full-depth revenue analytics including:
  1. Daily revenue time series (last 30 days)
  2. Hourly heatmap (24-hour revenue distribution)
  3. Weekly patterns (day-of-week performance)
  4. Moving averages (7-day, 14-day smoothing)
  5. Week-over-week and month-over-month growth
  6. Revenue by order type (dine-in vs takeout vs delivery)
  7. Revenue by category breakdown
  8. Average check / basket size analysis
  9. Customer spending segments (high/medium/low spenders)
  10. Anomaly detection (days significantly above/below average)
  11. 7-day forward forecast with confidence intervals
  12. Peak/off-peak period identification
  13. Revenue velocity (orders per hour)
================================================================================
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import defaultdict
from datetime import datetime, timedelta
import math
import models


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def get_revenue_forecast(db: Session, restaurant_id: int) -> dict:
    """Exhaustive revenue intelligence."""
    orders = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.status != models.OrderStatus.CANCELLED,
    ).all()

    if not orders:
        return _empty_response()

    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    # ── Build Time Series ──
    daily = defaultdict(lambda: {"revenue": 0, "orders": 0, "items": 0})
    hourly = defaultdict(lambda: {"revenue": 0, "orders": 0})
    weekly = defaultdict(lambda: {"revenue": 0, "orders": 0, "days_seen": set()})
    by_type = defaultdict(lambda: {"revenue": 0, "orders": 0})
    by_category = defaultdict(lambda: {"revenue": 0, "qty": 0})
    check_sizes = []

    for order in orders:
        date_str = order.created_at.strftime("%Y-%m-%d")
        revenue = order.total or 0
        daily[date_str]["revenue"] += revenue
        daily[date_str]["orders"] += 1
        daily[date_str]["items"] += sum(oi.quantity for oi in order.items)

        hour = order.created_at.hour
        hourly[hour]["revenue"] += revenue
        hourly[hour]["orders"] += 1

        weekday = order.created_at.strftime("%A")
        weekly[weekday]["revenue"] += revenue
        weekly[weekday]["orders"] += 1
        weekly[weekday]["days_seen"].add(date_str)

        # By order type
        otype = order.order_type.value if order.order_type else "dine_in"
        by_type[otype]["revenue"] += revenue
        by_type[otype]["orders"] += 1

        # By category (from order items)
        for oi in order.items:
            cat = oi.menu_item.category if oi.menu_item else "Unknown"
            by_category[cat]["revenue"] += oi.quantity * oi.unit_price
            by_category[cat]["qty"] += oi.quantity

        check_sizes.append(revenue)

    # Sort time series
    sorted_daily = sorted(daily.items())
    total_days = max(len(sorted_daily), 1)

    # ── Daily Revenue Data ──
    daily_revenue = []
    revenues = [r for _, r in [(d, daily[d]["revenue"]) for d in sorted(daily.keys())]]

    # Compute 7-day and 14-day moving averages
    for i, (d, data) in enumerate(sorted_daily):
        rev = data["revenue"]
        ma7 = int(sum(revenues[max(0, i-6):i+1]) / min(i+1, 7)) if i >= 0 else rev
        ma14 = int(sum(revenues[max(0, i-13):i+1]) / min(i+1, 14)) if i >= 0 else rev

        daily_revenue.append({
            "date": d,
            "revenue": rev,
            "orders": data["orders"],
            "items": data["items"],
            "avg_check": int(rev / max(data["orders"], 1)),
            "ma_7": ma7,
            "ma_14": ma14,
        })

    # ── Hourly Heatmap ──
    total_active_days = max(len(sorted_daily), 1)
    hourly_pattern = []
    for h in range(24):
        data = hourly[h]
        avg_rev = int(data["revenue"] / total_active_days)
        avg_orders = round(data["orders"] / total_active_days, 1)
        hourly_pattern.append({
            "hour": h,
            "label": f"{h:02d}:00",
            "avg_revenue": avg_rev,
            "avg_orders": avg_orders,
            "total_revenue": data["revenue"],
            "total_orders": data["orders"],
        })

    # Peak/off-peak identification
    peak_threshold = sum(h["avg_revenue"] for h in hourly_pattern) / 24 * 1.5
    for h in hourly_pattern:
        h["is_peak"] = h["avg_revenue"] >= peak_threshold
        h["period"] = _classify_period(h["hour"])

    # ── Weekly Pattern ──
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekly_pattern = []
    for day in day_order:
        data = weekly[day]
        num_days = max(len(data["days_seen"]), 1)
        weekly_pattern.append({
            "day": day,
            "avg_revenue": int(data["revenue"] / num_days),
            "avg_orders": round(data["orders"] / num_days, 1),
            "total_revenue": data["revenue"],
            "total_orders": data["orders"],
            "days_sampled": num_days,
        })

    # ── Revenue by Order Type ──
    total_rev = sum(d["revenue"] for d in by_type.values()) or 1
    revenue_by_type = [
        {
            "type": t,
            "revenue": data["revenue"],
            "orders": data["orders"],
            "share_pct": round((data["revenue"] / total_rev) * 100, 1),
            "avg_check": int(data["revenue"] / max(data["orders"], 1)),
        }
        for t, data in sorted(by_type.items(), key=lambda x: x[1]["revenue"], reverse=True)
    ]

    # ── Revenue by Category ──
    cat_total = sum(d["revenue"] for d in by_category.values()) or 1
    revenue_by_category = [
        {
            "category": cat,
            "revenue": data["revenue"],
            "share_pct": round((data["revenue"] / cat_total) * 100, 1),
            "qty_sold": data["qty"],
        }
        for cat, data in sorted(by_category.items(), key=lambda x: x[1]["revenue"], reverse=True)
    ]

    # ── Check Size Distribution ──
    if check_sizes:
        sorted_checks = sorted(check_sizes)
        avg_check = int(sum(check_sizes) / len(check_sizes))
        median_check = sorted_checks[len(sorted_checks) // 2]
        p25 = sorted_checks[int(len(sorted_checks) * 0.25)]
        p75 = sorted_checks[int(len(sorted_checks) * 0.75)]
    else:
        avg_check = median_check = p25 = p75 = 0

    check_analysis = {
        "avg_check": avg_check,
        "median_check": median_check,
        "p25": p25,
        "p75": p75,
        "min_check": min(check_sizes) if check_sizes else 0,
        "max_check": max(check_sizes) if check_sizes else 0,
    }

    # ── Customer Spending Segments ──
    if check_sizes:
        high_spend_threshold = int(p75 * 1.5)
        low_spend_threshold = int(p25 * 0.8)
        segments = {
            "high_spenders": {"count": sum(1 for c in check_sizes if c >= high_spend_threshold), "threshold": high_spend_threshold},
            "medium_spenders": {"count": sum(1 for c in check_sizes if low_spend_threshold < c < high_spend_threshold)},
            "low_spenders": {"count": sum(1 for c in check_sizes if c <= low_spend_threshold), "threshold": low_spend_threshold},
        }
    else:
        segments = {}

    # ── Anomaly Detection ──
    anomalies = _detect_anomalies(daily_revenue)

    # ── Trend Analysis ──
    trends = _compute_trends(sorted_daily, orders, hourly_pattern, weekly_pattern, check_analysis, daily_revenue)

    # ── 7-Day Forecast ──
    forecast = _forecast_next_7(weekly_pattern, daily_revenue, trends)

    return {
        "daily_revenue": daily_revenue[-30:],
        "hourly_pattern": hourly_pattern,
        "weekly_pattern": weekly_pattern,
        "revenue_by_type": revenue_by_type,
        "revenue_by_category": revenue_by_category,
        "check_analysis": check_analysis,
        "spending_segments": segments,
        "anomalies": anomalies,
        "forecast": forecast,
        "trends": trends,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TREND CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────
def _compute_trends(sorted_daily, orders, hourly_pattern, weekly_pattern, check_analysis, daily_revenue):
    """Compute comprehensive trend metrics."""
    revs = [d[1]["revenue"] for d in sorted_daily]
    total_revenue = sum(revs)
    total_orders = len(orders)
    avg_daily = total_revenue / max(len(sorted_daily), 1)

    # WoW growth
    if len(revs) >= 14:
        recent_7 = sum(revs[-7:])
        previous_7 = sum(revs[-14:-7])
        wow_growth = round(((recent_7 - previous_7) / max(previous_7, 1)) * 100, 1)
    elif len(revs) >= 7:
        recent_7 = sum(revs[-7:])
        wow_growth = 0
    else:
        recent_7 = sum(revs)
        wow_growth = 0

    # MoM growth (if enough data)
    if len(revs) >= 28:
        recent_14 = sum(revs[-14:])
        previous_14 = sum(revs[-28:-14])
        mom_growth = round(((recent_14 - previous_14) / max(previous_14, 1)) * 100, 1)
    else:
        mom_growth = None

    # Revenue velocity (average orders per peak hour)
    peak_hours = [h for h in hourly_pattern if h.get("is_peak")]
    avg_peak_velocity = round(
        sum(h["avg_orders"] for h in peak_hours) / max(len(peak_hours), 1), 1
    ) if peak_hours else 0

    # Best/worst days
    if daily_revenue:
        best_day = max(daily_revenue, key=lambda x: x["revenue"])
        worst_day = min(daily_revenue, key=lambda x: x["revenue"])
    else:
        best_day = worst_day = {"date": "N/A", "revenue": 0}

    return {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "avg_daily_revenue": int(avg_daily),
        "avg_order_value": check_analysis["avg_check"],
        "median_order_value": check_analysis["median_check"],
        "last_7_days_revenue": recent_7 if len(revs) >= 7 else total_revenue,
        "week_over_week_growth": wow_growth,
        "month_over_month_growth": mom_growth,
        "revenue_velocity_peak": avg_peak_velocity,
        "peak_hour": max(hourly_pattern, key=lambda x: x["avg_revenue"])["label"] if hourly_pattern else "N/A",
        "peak_day": max(weekly_pattern, key=lambda x: x["avg_revenue"])["day"] if weekly_pattern else "N/A",
        "best_day": {"date": best_day["date"], "revenue": best_day["revenue"]},
        "worst_day": {"date": worst_day["date"], "revenue": worst_day["revenue"]},
    }


# ─────────────────────────────────────────────────────────────────────────────
# ANOMALY DETECTION
# ─────────────────────────────────────────────────────────────────────────────
def _detect_anomalies(daily_revenue):
    """Flag days with revenue significantly above or below the norm (2 std devs)."""
    if len(daily_revenue) < 7:
        return []

    revs = [d["revenue"] for d in daily_revenue]
    mean = sum(revs) / len(revs)
    variance = sum((r - mean) ** 2 for r in revs) / len(revs)
    std_dev = math.sqrt(variance) if variance > 0 else 1

    anomalies = []
    for d in daily_revenue:
        z_score = (d["revenue"] - mean) / std_dev
        if abs(z_score) >= 2:
            anomalies.append({
                "date": d["date"],
                "revenue": d["revenue"],
                "expected": int(mean),
                "deviation_pct": round(((d["revenue"] - mean) / mean) * 100, 1),
                "type": "spike" if z_score > 0 else "dip",
                "z_score": round(z_score, 2),
            })

    return sorted(anomalies, key=lambda x: abs(x["z_score"]), reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# 7-DAY FORECAST
# ─────────────────────────────────────────────────────────────────────────────
def _forecast_next_7(weekly_pattern, daily_revenue, trends):
    """Enhanced forecast with confidence intervals."""
    today = datetime.utcnow()
    day_map = {p["day"]: p["avg_revenue"] for p in weekly_pattern}

    # Calculate daily variance for confidence intervals
    revs = [d["revenue"] for d in daily_revenue]
    if revs:
        mean_rev = sum(revs) / len(revs)
        std_dev = math.sqrt(sum((r - mean_rev) ** 2 for r in revs) / len(revs)) if len(revs) > 1 else mean_rev * 0.1
    else:
        mean_rev = 0
        std_dev = 0

    # Apply growth trend to forecast
    growth_factor = 1 + (trends.get("week_over_week_growth", 0) / 100 * 0.3)  # Dampened growth

    forecast = []
    for i in range(1, 8):
        future_date = today + timedelta(days=i)
        day_name = future_date.strftime("%A")
        base_prediction = day_map.get(day_name, int(mean_rev))
        adjusted = int(base_prediction * growth_factor)

        # Confidence interval (±1 std dev)
        ci_low = max(0, int(adjusted - std_dev * 0.7))
        ci_high = int(adjusted + std_dev * 0.7)

        # Confidence score based on data quality
        data_points = next((p["days_sampled"] for p in weekly_pattern if p["day"] == day_name), 0)
        confidence = min(95, 60 + data_points * 8)

        forecast.append({
            "date": future_date.strftime("%Y-%m-%d"),
            "day": day_name,
            "predicted_revenue": adjusted,
            "confidence_low": ci_low,
            "confidence_high": ci_high,
            "confidence_pct": confidence,
        })

    return forecast


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _classify_period(hour):
    if 6 <= hour < 11:
        return "breakfast"
    elif 11 <= hour < 15:
        return "lunch"
    elif 15 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 22:
        return "dinner"
    else:
        return "off-peak"


def _empty_response():
    return {
        "daily_revenue": [], "hourly_pattern": [], "weekly_pattern": [],
        "revenue_by_type": [], "revenue_by_category": [],
        "check_analysis": {}, "spending_segments": {},
        "anomalies": [], "forecast": [], "trends": {},
    }
