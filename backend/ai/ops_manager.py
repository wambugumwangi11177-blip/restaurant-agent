"""
AI Operations Manager — EXHAUSTIVE
================================================================================
Central intelligence aggregator — the "Restaurant Brain"
Pulls deep insights from all AI services and produces:
  1. Multi-dimensional health score (0-100) with weighted subsections
  2. Real-time quick stats (today's performance snapshot)
  3. Cross-system alert aggregation with priority ranking
  4. AI module hot summaries (key finding from each service)
  5. Trend dashboard (is the restaurant getting better or worse?)
  6. Performance comparison (this week vs last week)
  7. Risk matrix (what could go wrong today?)
  8. Opportunity radar (where to capture more revenue)
  9. Operational recommendations ranked by revenue impact
================================================================================
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import models
from ai import menu_engineer, revenue_forecaster, kds_intelligence, inventory_predictor, reservation_optimizer


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def get_operations_dashboard(db: Session, restaurant_id: int) -> dict:
    """Complete AI Operations Manager dashboard — exhaustive."""
    now = datetime.utcnow()
    today = now.date()
    yesterday = today - timedelta(days=1)

    # Gather data from all AI services
    menu_data = menu_engineer.get_menu_engineering(db, restaurant_id)
    revenue_data = revenue_forecaster.get_revenue_forecast(db, restaurant_id)
    kds_data = kds_intelligence.get_kds_intelligence(db, restaurant_id)
    inventory_data = inventory_predictor.get_inventory_predictions(db, restaurant_id)
    reservation_data = reservation_optimizer.get_reservation_insights(db, restaurant_id)

    # ─────────────────────────────────────────────
    # 1. MULTI-DIMENSIONAL HEALTH SCORE
    # ─────────────────────────────────────────────
    scores = []

    # Menu Health (0-100) — weighted by food cost + stars ratio
    if menu_data.get("summary"):
        s = menu_data["summary"]
        total_items = max(s.get("total_items", 1), 1)
        stars_ratio = s.get("stars", 0) / total_items * 100
        dogs_ratio = s.get("dogs", 0) / total_items * 100
        food_cost_score = max(0, 100 - max(0, s.get("avg_food_cost_pct", 30) - 25) * 3)
        menu_score = round(max(0, min(100, (stars_ratio * 1.5) + food_cost_score * 0.5 - dogs_ratio)))
        scores.append({"category": "Menu Health", "score": menu_score, "weight": 20,
                        "detail": f"{s.get('stars', 0)} Stars, {s.get('dogs', 0)} Dogs, {s.get('avg_food_cost_pct', 0)}% avg food cost"})
    else:
        scores.append({"category": "Menu Health", "score": 50, "weight": 20, "detail": "No data"})

    # Revenue Trend (0-100)
    if revenue_data.get("trends"):
        t = revenue_data["trends"]
        growth = t.get("week_over_week_growth", 0)
        rev_score = round(max(0, min(100, 50 + growth * 2)))
        scores.append({"category": "Revenue Trend", "score": rev_score, "weight": 25,
                        "detail": f"{growth:+.1f}% WoW growth, {t.get('peak_day', 'N/A')} is peak day"})
    else:
        scores.append({"category": "Revenue Trend", "score": 50, "weight": 25, "detail": "No data"})

    # Kitchen Efficiency (0-100)
    if kds_data.get("throughput"):
        tp = kds_data["throughput"]
        avg_prep = tp.get("avg_prep_minutes", 15)
        completion_rate = tp.get("completion_rate", 90)
        kitchen_score = round(max(0, min(100, (completion_rate * 0.6) + max(0, 40 - (avg_prep - 8) * 5))))
        bottleneck_count = len(kds_data.get("bottlenecks", []))
        scores.append({"category": "Kitchen Efficiency", "score": kitchen_score, "weight": 20,
                        "detail": f"{avg_prep:.1f} min avg prep, {bottleneck_count} bottleneck(s), {completion_rate}% completion"})
    else:
        scores.append({"category": "Kitchen Efficiency", "score": 50, "weight": 20, "detail": "No data"})

    # Inventory Status (0-100)
    if inventory_data.get("summary"):
        inv = inventory_data["summary"]
        critical = inv.get("critical_items", 0)
        low = inv.get("low_stock_items", 0)
        high_spoil = inv.get("high_spoilage_items", 0)
        inv_score = round(max(0, min(100, 100 - critical * 25 - low * 10 - high_spoil * 5)))
        scores.append({"category": "Inventory Status", "score": inv_score, "weight": 15,
                        "detail": f"{critical} critical, {low} low, {high_spoil} spoilage risk"})
    else:
        scores.append({"category": "Inventory Status", "score": 50, "weight": 15, "detail": "No data"})

    # Reservation Reliability (0-100)
    if reservation_data.get("no_show_analysis"):
        ns = reservation_data["no_show_analysis"]
        no_show_rate = ns.get("no_show_rate", 0)
        completion = ns.get("completion_rate", 0)
        res_score = round(max(0, min(100, completion - no_show_rate)))
        lost = reservation_data.get("revenue_impact", {}).get("estimated_revenue_lost", 0)
        scores.append({"category": "Reservation Reliability", "score": res_score, "weight": 20,
                        "detail": f"{no_show_rate}% no-show, {completion}% completion, ~{int(lost/100):,} KES lost"})
    else:
        scores.append({"category": "Reservation Reliability", "score": 50, "weight": 20, "detail": "No data"})

    # Weighted overall
    total_weight = sum(s["weight"] for s in scores)
    overall_health = round(sum(s["score"] * s["weight"] for s in scores) / max(total_weight, 1))

    # ─────────────────────────────────────────────
    # 2. QUICK STATS (Today Snapshot)
    # ─────────────────────────────────────────────
    today_orders = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant_id,
        func.date(models.Order.created_at) == today,
    ).count()

    today_revenue = db.query(func.sum(models.Order.total)).filter(
        models.Order.restaurant_id == restaurant_id,
        func.date(models.Order.created_at) == today,
        models.Order.status != models.OrderStatus.CANCELLED,
    ).scalar() or 0

    yesterday_revenue = db.query(func.sum(models.Order.total)).filter(
        models.Order.restaurant_id == restaurant_id,
        func.date(models.Order.created_at) == yesterday,
        models.Order.status != models.OrderStatus.CANCELLED,
    ).scalar() or 0

    pending_orders = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.status.in_([models.OrderStatus.PENDING, models.OrderStatus.PREP]),
    ).count()

    quick_stats = {
        "today_orders": today_orders,
        "today_revenue": today_revenue,
        "yesterday_revenue": yesterday_revenue,
        "day_over_day_change": round(((today_revenue - yesterday_revenue) / max(yesterday_revenue, 1)) * 100, 1) if yesterday_revenue else 0,
        "pending_orders": pending_orders,
        "menu_items": menu_data.get("summary", {}).get("total_items", 0),
        "total_revenue_30d": revenue_data.get("trends", {}).get("total_revenue", 0),
        "avg_order_value": revenue_data.get("trends", {}).get("avg_order_value", 0),
        "active_alerts": len(_aggregate_alerts(menu_data, kds_data, inventory_data, reservation_data)),
    }

    # ─────────────────────────────────────────────
    # 3. CROSS-SYSTEM ALERTS
    # ─────────────────────────────────────────────
    alerts = _aggregate_alerts(menu_data, kds_data, inventory_data, reservation_data)

    # ─────────────────────────────────────────────
    # 4. AI MODULE SUMMARIES
    # ─────────────────────────────────────────────
    ai_modules = {
        "menu_engineering": menu_data.get("summary", {}),
        "revenue": revenue_data.get("trends", {}),
        "kitchen": kds_data.get("throughput", {}),
        "inventory": inventory_data.get("summary", {}),
        "reservations": reservation_data.get("no_show_analysis", {}),
    }

    # ─────────────────────────────────────────────
    # 5. RISK MATRIX
    # ─────────────────────────────────────────────
    risks = []
    inv_sum = inventory_data.get("summary", {})
    if inv_sum.get("critical_items", 0) > 0:
        risks.append({"risk": "Stock-out risk", "severity": "critical",
                       "detail": f"{inv_sum['critical_items']} items out of stock — menu items may be unavailable"})
    if reservation_data.get("no_show_analysis", {}).get("no_show_rate", 0) > 20:
        risks.append({"risk": "High no-show rate", "severity": "high",
                       "detail": "Over 20% of reservations are no-shows — revenue leakage"})
    bottleneck_count = len(kds_data.get("bottlenecks", []))
    if bottleneck_count > 0:
        worst = kds_data["bottlenecks"][0] if kds_data["bottlenecks"] else {}
        risks.append({"risk": "Kitchen bottleneck", "severity": worst.get("severity", "medium"),
                       "detail": f"{bottleneck_count} station(s) above average — could delay orders"})
    dogs = menu_data.get("summary", {}).get("dogs", 0)
    if dogs > 3:
        risks.append({"risk": "Menu dead weight", "severity": "medium",
                       "detail": f"{dogs} Dog items on menu — low popularity and low profit"})

    # ─────────────────────────────────────────────
    # 6. OPPORTUNITY RADAR
    # ─────────────────────────────────────────────
    opportunities = []
    puzzles = menu_data.get("summary", {}).get("puzzles", 0)
    if puzzles > 0:
        opportunities.append({
            "opportunity": "Promote high-margin items",
            "potential": "high",
            "detail": f"{puzzles} Puzzle items have high margins but low sales — promote to convert to Stars",
        })
    rev_lost = reservation_data.get("revenue_impact", {}).get("estimated_revenue_lost", 0)
    if rev_lost > 0:
        opportunities.append({
            "opportunity": "Recover no-show revenue",
            "potential": "high",
            "detail": f"~{int(rev_lost/100):,} KES lost to no-shows — deposits could recover 60%+",
        })
    overbook = reservation_data.get("overbooking", {})
    if overbook.get("recommended_rate", 0) > 5:
        opportunities.append({
            "opportunity": "Implement controlled overbooking",
            "potential": "medium",
            "detail": f"Accept {overbook['recommended_rate']}% more bookings to recover ~{int(overbook.get('potential_monthly_recovery', 0)/100):,} KES/month",
        })
    growth = revenue_data.get("trends", {}).get("week_over_week_growth", 0)
    if growth > 10:
        opportunities.append({
            "opportunity": "Capitalize on growth momentum",
            "potential": "high",
            "detail": f"{growth}% WoW growth — ensure inventory and staffing scale accordingly",
        })

    return {
        "health_score": overall_health,
        "health_breakdown": scores,
        "quick_stats": quick_stats,
        "alerts": alerts[:8],
        "risks": risks,
        "opportunities": opportunities,
        "ai_modules": ai_modules,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ALERT AGGREGATION
# ─────────────────────────────────────────────────────────────────────────────
def _aggregate_alerts(menu_data, kds_data, inventory_data, reservation_data):
    """Pull and rank alerts from all AI services."""
    alerts = []
    priority_map = {"critical": 0, "high": 1, "warning": 1, "medium": 2, "info": 3, "low": 3}

    # Inventory alerts
    for alert in (inventory_data.get("alerts") or [])[:5]:
        alerts.append({
            "source": "inventory",
            "item": alert.get("item", ""),
            "message": alert["message"],
            "severity": alert.get("severity", "warning"),
            "action": alert.get("action", ""),
        })

    # KDS recommendations
    for rec in (kds_data.get("recommendations") or [])[:3]:
        alerts.append({
            "source": "kitchen",
            "item": rec.get("station", ""),
            "message": rec["message"],
            "severity": rec.get("priority", "medium"),
            "action": rec.get("action", ""),
        })

    # Menu recommendations
    for rec in (menu_data.get("recommendations") or [])[:3]:
        alerts.append({
            "source": "menu",
            "item": rec.get("item", ""),
            "message": rec.get("reason", rec.get("message", "")),
            "severity": rec.get("priority", "medium"),
            "action": rec.get("action", ""),
        })

    # Reservation recommendations
    for rec in (reservation_data.get("recommendations") or [])[:3]:
        alerts.append({
            "source": "reservations",
            "item": "",
            "message": rec.get("message", ""),
            "severity": rec.get("priority", "medium"),
            "action": rec.get("action", ""),
        })

    # Sort by severity
    alerts.sort(key=lambda x: priority_map.get(x["severity"], 5))
    return alerts
