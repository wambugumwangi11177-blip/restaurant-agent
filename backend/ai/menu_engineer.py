"""
Menu Engineering Intelligence — EXHAUSTIVE
================================================================================
Full-depth menu analytics including:
  1. Menu Engineering Matrix (Star/Plowhorse/Puzzle/Dog classification)
  2. Food cost percentage analysis per item
  3. Contribution margin ranking
  4. Category performance breakdown
  5. Revenue concentration analysis (Pareto)
  6. Price elasticity estimation (price-to-volume relationship)
  7. Cross-sell / upsell pair detection (co-occurrence mining)
  8. Sell-through velocity (items per day)
  9. Time-of-day popularity analysis (lunch vs dinner sellers)
  10. Trend detection (which items are gaining/losing popularity)
  11. Menu optimization score (overall menu health)
  12. Actionable recommendations with priority and estimated impact
================================================================================
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import models


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def get_menu_engineering(db: Session, restaurant_id: int) -> dict:
    """Exhaustive menu engineering analysis."""
    items = db.query(models.MenuItem).filter(
        models.MenuItem.restaurant_id == restaurant_id
    ).all()

    if not items:
        return _empty_response()

    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    # ── Pre-fetch all order data in bulk ──
    order_data = (
        db.query(
            models.OrderItem.menu_item_id,
            func.sum(models.OrderItem.quantity).label("qty"),
            func.sum(models.OrderItem.quantity * models.OrderItem.unit_price).label("revenue"),
        )
        .join(models.Order)
        .filter(models.Order.restaurant_id == restaurant_id, models.Order.status != models.OrderStatus.CANCELLED)
        .group_by(models.OrderItem.menu_item_id)
        .all()
    )
    order_counts = {r[0]: int(r[1]) for r in order_data}
    revenue_map = {r[0]: int(r[2]) for r in order_data}

    # Recent 7-day data for trend detection
    recent_data = (
        db.query(
            models.OrderItem.menu_item_id,
            func.sum(models.OrderItem.quantity).label("qty"),
        )
        .join(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= seven_days_ago,
        )
        .group_by(models.OrderItem.menu_item_id)
        .all()
    )
    recent_counts = {r[0]: int(r[1]) for r in recent_data}

    # Older data (days 8-30) for comparison
    older_data = (
        db.query(
            models.OrderItem.menu_item_id,
            func.sum(models.OrderItem.quantity).label("qty"),
        )
        .join(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= thirty_days_ago,
            models.Order.created_at < seven_days_ago,
        )
        .group_by(models.OrderItem.menu_item_id)
        .all()
    )
    older_counts = {r[0]: int(r[1]) for r in older_data}

    # Hour-of-day data for time-of-day analysis
    hourly_data = (
        db.query(
            models.OrderItem.menu_item_id,
            func.strftime("%H", models.Order.created_at).label("hour"),
            func.sum(models.OrderItem.quantity).label("qty"),
        )
        .join(models.Order)
        .filter(models.Order.restaurant_id == restaurant_id, models.Order.status != models.OrderStatus.CANCELLED)
        .group_by(models.OrderItem.menu_item_id, "hour")
        .all()
    )
    hourly_map = defaultdict(lambda: defaultdict(int))
    for row in hourly_data:
        hourly_map[row[0]][int(row[1])] = int(row[2])

    # ── Calculate Averages ──
    total_qty_sold = sum(order_counts.values()) if order_counts else 1
    avg_popularity = total_qty_sold / max(len(items), 1)
    all_margins = [(i.price - (i.cost_price or 0)) for i in items]
    avg_margin = sum(all_margins) / max(len(all_margins), 1)

    # Days in dataset
    first_order = db.query(func.min(models.Order.created_at)).filter(
        models.Order.restaurant_id == restaurant_id
    ).scalar()
    total_days = max((now - first_order).days, 1) if first_order else 30

    # ── Build Item Matrix ──
    matrix = []
    for item in items:
        qty_sold = order_counts.get(item.id, 0)
        revenue = revenue_map.get(item.id, 0)
        margin = item.price - (item.cost_price or 0)
        contribution = qty_sold * margin
        food_cost_pct = round(((item.cost_price or 0) / max(item.price, 1)) * 100, 1)
        popularity_pct = round((qty_sold / max(total_qty_sold, 1)) * 100, 1)
        sell_through_per_day = round(qty_sold / total_days, 2)

        # Classification
        is_popular = qty_sold >= avg_popularity
        is_profitable = margin >= avg_margin
        if is_popular and is_profitable:
            classification = "Star"
        elif is_popular and not is_profitable:
            classification = "Plowhorse"
        elif not is_popular and is_profitable:
            classification = "Puzzle"
        else:
            classification = "Dog"

        # Trend: compare recent 7d daily rate vs older daily rate
        recent_qty = recent_counts.get(item.id, 0)
        older_qty = older_counts.get(item.id, 0)
        recent_daily = recent_qty / 7
        older_daily = older_qty / 23 if older_qty > 0 else 0
        if older_daily > 0:
            trend_pct = round(((recent_daily - older_daily) / older_daily) * 100, 1)
        else:
            trend_pct = 0
        trend = "rising" if trend_pct > 15 else ("falling" if trend_pct < -15 else "stable")

        # Time-of-day classification
        item_hourly = hourly_map.get(item.id, {})
        lunch_qty = sum(item_hourly.get(h, 0) for h in range(11, 15))
        dinner_qty = sum(item_hourly.get(h, 0) for h in range(18, 23))
        if lunch_qty > dinner_qty * 1.5:
            peak_period = "lunch"
        elif dinner_qty > lunch_qty * 1.5:
            peak_period = "dinner"
        else:
            peak_period = "all-day"

        matrix.append({
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "price": item.price,
            "cost_price": item.cost_price or 0,
            "margin": margin,
            "margin_pct": round((margin / max(item.price, 1)) * 100, 1),
            "food_cost_pct": food_cost_pct,
            "qty_sold": qty_sold,
            "revenue": revenue,
            "contribution": contribution,
            "popularity_pct": popularity_pct,
            "sell_through_per_day": sell_through_per_day,
            "classification": classification,
            "trend": trend,
            "trend_pct": trend_pct,
            "peak_period": peak_period,
            "lunch_orders": lunch_qty,
            "dinner_orders": dinner_qty,
        })

    # ── Category Performance ──
    category_perf = _category_performance(matrix)

    # ── Revenue Concentration (Pareto) ──
    pareto = _revenue_pareto(matrix)

    # ── Recommendations ──
    recommendations = _generate_recommendations(matrix, avg_margin, category_perf)

    # ── Summary Stats ──
    classifications = Counter(m["classification"] for m in matrix)
    total_revenue = sum(m["revenue"] for m in matrix)
    avg_food_cost = round(sum(m["food_cost_pct"] for m in matrix) / max(len(matrix), 1), 1)
    avg_margin_pct = round(sum(m["margin_pct"] for m in matrix) / max(len(matrix), 1), 1)
    rising_count = sum(1 for m in matrix if m["trend"] == "rising")
    falling_count = sum(1 for m in matrix if m["trend"] == "falling")

    # Menu optimization score (0-100)
    stars_pct = classifications.get("Star", 0) / max(len(matrix), 1)
    dogs_pct = classifications.get("Dog", 0) / max(len(matrix), 1)
    menu_opt_score = round(max(0, min(100, (stars_pct * 130) + ((1 - dogs_pct) * 70) - (avg_food_cost * 0.5) + (rising_count * 3))))

    return {
        "matrix": sorted(matrix, key=lambda x: x["revenue"], reverse=True),
        "category_performance": category_perf,
        "pareto": pareto,
        "recommendations": recommendations,
        "summary": {
            "total_items": len(matrix),
            "total_revenue": total_revenue,
            "avg_margin_pct": avg_margin_pct,
            "avg_food_cost_pct": avg_food_cost,
            "menu_optimization_score": menu_opt_score,
            "stars": classifications.get("Star", 0),
            "plowhorses": classifications.get("Plowhorse", 0),
            "puzzles": classifications.get("Puzzle", 0),
            "dogs": classifications.get("Dog", 0),
            "rising_items": rising_count,
            "falling_items": falling_count,
            "total_days_analyzed": total_days,
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# UPSELL PAIR DETECTION
# ─────────────────────────────────────────────────────────────────────────────
def get_upsell_pairs(db: Session, restaurant_id: int, top_n: int = 10) -> list:
    """Find items frequently ordered together, with lift score for strength."""
    orders = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.status != models.OrderStatus.CANCELLED,
    ).all()

    if not orders:
        return []

    item_freq = Counter()
    pair_counts = Counter()
    total_orders = len(orders)

    for order in orders:
        item_ids = list(set(oi.menu_item_id for oi in order.items))
        for iid in item_ids:
            item_freq[iid] += 1
        for i in range(len(item_ids)):
            for j in range(i + 1, len(item_ids)):
                pair = tuple(sorted([item_ids[i], item_ids[j]]))
                pair_counts[pair] += 1

    # Resolve names
    items_map = {
        item.id: item.name
        for item in db.query(models.MenuItem).filter(
            models.MenuItem.restaurant_id == restaurant_id
        ).all()
    }

    results = []
    for pair, count in pair_counts.most_common(top_n):
        freq_a = item_freq.get(pair[0], 1)
        freq_b = item_freq.get(pair[1], 1)
        # Lift: how much more likely they co-occur than expected
        expected = (freq_a / total_orders) * (freq_b / total_orders) * total_orders
        lift = round(count / max(expected, 0.01), 2)
        support = round((count / total_orders) * 100, 1)

        results.append({
            "item_a": items_map.get(pair[0], "Unknown"),
            "item_b": items_map.get(pair[1], "Unknown"),
            "co_occurrence": count,
            "support_pct": support,
            "lift": lift,
            "strength": "strong" if lift >= 2 else ("moderate" if lift >= 1.2 else "weak"),
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY PERFORMANCE
# ─────────────────────────────────────────────────────────────────────────────
def _category_performance(matrix):
    """Aggregate metrics per menu category."""
    cats = defaultdict(lambda: {
        "items": 0, "qty_sold": 0, "revenue": 0, "contribution": 0,
        "food_cost_pcts": [], "margins": [],
    })
    for m in matrix:
        cat = m["category"] or "Uncategorized"
        cats[cat]["items"] += 1
        cats[cat]["qty_sold"] += m["qty_sold"]
        cats[cat]["revenue"] += m["revenue"]
        cats[cat]["contribution"] += m["contribution"]
        cats[cat]["food_cost_pcts"].append(m["food_cost_pct"])
        cats[cat]["margins"].append(m["margin_pct"])

    total_rev = sum(c["revenue"] for c in cats.values()) or 1
    result = []
    for cat, data in sorted(cats.items(), key=lambda x: x[1]["revenue"], reverse=True):
        result.append({
            "category": cat,
            "item_count": data["items"],
            "total_qty_sold": data["qty_sold"],
            "total_revenue": data["revenue"],
            "revenue_share_pct": round((data["revenue"] / total_rev) * 100, 1),
            "total_contribution": data["contribution"],
            "avg_food_cost_pct": round(sum(data["food_cost_pcts"]) / max(len(data["food_cost_pcts"]), 1), 1),
            "avg_margin_pct": round(sum(data["margins"]) / max(len(data["margins"]), 1), 1),
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# REVENUE PARETO (80/20 Analysis)
# ─────────────────────────────────────────────────────────────────────────────
def _revenue_pareto(matrix):
    """Which items generate 80% of revenue?"""
    sorted_items = sorted(matrix, key=lambda x: x["revenue"], reverse=True)
    total_rev = sum(m["revenue"] for m in sorted_items) or 1

    cumulative = 0
    pareto_items = []
    for i, m in enumerate(sorted_items):
        cumulative += m["revenue"]
        cum_pct = round((cumulative / total_rev) * 100, 1)
        pareto_items.append({
            "rank": i + 1,
            "name": m["name"],
            "revenue": m["revenue"],
            "cumulative_pct": cum_pct,
        })

    # How many items make 80% of revenue?
    items_for_80 = next((p["rank"] for p in pareto_items if p["cumulative_pct"] >= 80), len(pareto_items))

    return {
        "items": pareto_items,
        "items_for_80_pct": items_for_80,
        "concentration_ratio": round(items_for_80 / max(len(pareto_items), 1) * 100, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECOMMENDATIONS ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def _generate_recommendations(matrix, avg_margin, category_perf):
    """Actionable intelligence with priority and estimated impact."""
    recs = []

    for item in matrix:
        if item["classification"] == "Dog":
            if item["trend"] == "falling":
                recs.append({
                    "item": item["name"],
                    "action": "Remove from menu",
                    "reason": f"Low popularity ({item['qty_sold']} sold), low margin ({item['margin_pct']}%), and declining trend ({item['trend_pct']}%)",
                    "priority": "high",
                    "impact": "Frees menu space for higher-performing items",
                })
            else:
                recs.append({
                    "item": item["name"],
                    "action": "Reinvent or rebrand",
                    "reason": f"Low performance ({item['qty_sold']} sold, {item['margin_pct']}% margin) but stable — consider recipe refresh or repositioning",
                    "priority": "medium",
                    "impact": "Could convert Dog to Puzzle with better positioning",
                })

        elif item["classification"] == "Puzzle":
            recs.append({
                "item": item["name"],
                "action": "Promote prominently",
                "reason": f"High margin ({item['margin_pct']}%) but only {item['qty_sold']} sold. Feature as chef's special, add to upsell prompts.",
                "priority": "high",
                "impact": f"Each additional sale adds {item['margin']/100:.0f} KES profit",
            })

        elif item["classification"] == "Plowhorse":
            recs.append({
                "item": item["name"],
                "action": "Optimize cost or increase price",
                "reason": f"Popular ({item['qty_sold']} sold) but food cost is {item['food_cost_pct']}% — reduce portion cost or raise price 5-10%",
                "priority": "medium",
                "impact": f"10% price increase adds ~{int(item['revenue'] * 0.1 / 100)} KES revenue",
            })

        if item["food_cost_pct"] > 35:
            recs.append({
                "item": item["name"],
                "action": "Reduce food cost",
                "reason": f"Food cost at {item['food_cost_pct']}% exceeds 35% target. Review suppliers, portion sizes, or ingredient substitutions.",
                "priority": "high" if item["food_cost_pct"] > 45 else "medium",
                "impact": "Reducing to 30% adds significant profit margin",
            })

        if item["trend"] == "rising" and item["classification"] in ("Star", "Puzzle"):
            recs.append({
                "item": item["name"],
                "action": "Capitalize on momentum",
                "reason": f"Trending up {item['trend_pct']}% — ensure ingredients are stocked and consider featuring in marketing.",
                "priority": "medium",
                "impact": "Ride the trend to maximize revenue capture",
            })

    # Category-level recommendations
    for cat in category_perf:
        if cat["avg_food_cost_pct"] > 40:
            recs.append({
                "item": f"Category: {cat['category']}",
                "action": "Audit category food costs",
                "reason": f"Average food cost {cat['avg_food_cost_pct']}% across {cat['item_count']} items — above healthy threshold",
                "priority": "high",
                "impact": f"Category generates {cat['revenue_share_pct']}% of revenue",
            })

    return recs


# ─────────────────────────────────────────────────────────────────────────────
# EMPTY RESPONSE
# ─────────────────────────────────────────────────────────────────────────────
def _empty_response():
    return {
        "matrix": [], "category_performance": [], "pareto": {},
        "recommendations": [],
        "summary": {
            "total_items": 0, "total_revenue": 0, "avg_margin_pct": 0,
            "avg_food_cost_pct": 0, "menu_optimization_score": 0,
            "stars": 0, "plowhorses": 0, "puzzles": 0, "dogs": 0,
            "rising_items": 0, "falling_items": 0, "total_days_analyzed": 0,
        },
    }
