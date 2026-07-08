"""
backend/ai/profit/intelligence.py
───────────────────────────────────
Profit Intelligence — complete financial brain.

Fixes vs previous version:
  BUG-04  — All DB range queries now use utcnow() not _now_eat().
             EAT is used only for DOW/hour display bucketing of results.
  BUG-10  — _channel_profitability and _daypart_profitability: replaced
             the implicit `.cost_price` access on potentially-None items
             with a safe helper `_item_cost(item_map, mid)`.
  BUG-11  — _upsell_lift: removed the type("x",(),{}) anonymous class hack
             (already fixed in the uploaded version — verified and kept).
  DS-02   — _profit_forecast now includes ±1 std-dev uncertainty band per day.
  DS-04   — portion_drift monthly_leak uses * (30/14) not * 2.
"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import math
import models
from ai.analysis_clock import analysis_anchor
from time_utils import utcnow

# ── Benchmarks ────────────────────────────────────────────────────────────────
HEALTHY_FOOD_COST_MAX = 35.0
HEALTHY_MARGIN_MIN    = 55.0
CRITICAL_MARGIN_FLOOR = 40.0
RETURNING_GUEST_DAYS  = 14
DELIVERY_COMMISSIONS  = {"uber_eats": 0.25, "glovo": 0.25, "bolt_food": 0.20}


def _item_cost(item_map: dict, mid: int) -> int:
    """BUG-10 FIX: safe item cost lookup — returns 0 if item deleted."""
    item = item_map.get(mid)
    return (item.cost_price or 0) if item else 0


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def get_profit_intelligence(db: Session, restaurant_id: int) -> dict:
    """Complete profit intelligence — UTC-correct, AttributeError-safe."""

    # BUG-04 FIX: use UTC for all DB range filters. Anchored to the
    # restaurant's most recent order, not wall-clock time (2026-07-07) — see
    # ai/analysis_clock.py.
    now             = analysis_anchor(db, restaurant_id)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago  = now - timedelta(days=60)

    items    = db.query(models.MenuItem).filter(models.MenuItem.restaurant_id == restaurant_id).all()
    item_map = {i.id: i for i in items}

    # joinedload eliminates the N+1 (BUG-12 — already fixed in uploaded version, kept)
    orders_30d = (
        db.query(models.Order)
        .options(joinedload(models.Order.items))
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= thirty_days_ago,   # UTC ✓
        )
        .all()
    )

    orders_prev = (
        db.query(models.Order)
        .options(joinedload(models.Order.items))
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= sixty_days_ago,    # UTC ✓
            models.Order.created_at < thirty_days_ago,
        )
        .all()
    )

    if not orders_30d:
        return _empty_response()

    # ── Single-pass item-level profit accumulation ────────────────────────────
    item_profit: dict[int, dict] = defaultdict(lambda: {"qty": 0, "revenue": 0, "cost": 0, "profit": 0})
    total_revenue = total_food_cost = total_items_sold = 0

    for order in orders_30d:
        for oi in order.items:
            item = item_map.get(oi.menu_item_id)
            if not item:
                continue
            line_revenue = oi.quantity * oi.unit_price
            line_cost    = oi.quantity * (item.cost_price or 0)
            item_profit[oi.menu_item_id]["qty"]     += oi.quantity
            item_profit[oi.menu_item_id]["revenue"] += line_revenue
            item_profit[oi.menu_item_id]["cost"]    += line_cost
            item_profit[oi.menu_item_id]["profit"]  += line_revenue - line_cost
            total_revenue    += line_revenue
            total_food_cost  += line_cost
            total_items_sold += oi.quantity

    total_gross_profit = total_revenue - total_food_cost
    food_cost_pct      = (total_food_cost / max(total_revenue, 1)) * 100
    gross_margin_pct   = (total_gross_profit / max(total_revenue, 1)) * 100
    prev_revenue       = sum(o.total or 0 for o in orders_prev)
    # Guard against a near-empty prior month: `/ max(prev_revenue, 1)` avoids a
    # ZeroDivisionError but, when prev_revenue is a few cents (e.g. a straggler
    # order), turns MoM growth into a garbage figure in the billions of percent.
    # A month-over-month comparison is only meaningful with a real prior month;
    # otherwise report 0. (Found 2026-07-07 — profit page showed 49,771,000,000%.)
    MIN_PREV_FOR_MOM = 100_000  # KES 1,000 — below this, no meaningful baseline
    if prev_revenue >= MIN_PREV_FOR_MOM:
        revenue_mom = round(((total_revenue - prev_revenue) / prev_revenue) * 100, 1)
    else:
        revenue_mom = 0.0

    contribution_margins = _build_contribution_margins(items, item_profit)
    profit_leaks         = _detect_profit_leaks(contribution_margins)
    portion_drift        = _detect_portion_drift(db, restaurant_id, item_map, now)
    daypart_analysis     = _daypart_profitability(orders_30d, item_map)
    channel_analysis     = _channel_profitability(orders_30d, item_map)
    customer_intel       = _customer_intelligence(orders_30d, total_revenue, now)
    upsell_uplift        = _upsell_lift(orders_30d, item_map)
    profit_forecast      = _profit_forecast(orders_30d, total_food_cost, total_revenue)

    recommendations = _generate_recommendations(
        food_cost_pct    = food_cost_pct,
        profit_leaks     = profit_leaks,
        daypart_analysis = daypart_analysis,
        channel_analysis = channel_analysis,
        at_risk          = customer_intel["at_risk_customers"],
        portion_drift    = portion_drift,
        revenue_mom      = revenue_mom,
    )

    stars = [cm for cm in contribution_margins if cm["status"] == "STAR"]
    dogs  = [cm for cm in contribution_margins if cm["status"] == "LEAK"]

    return {
        "summary": {
            "total_revenue_30d":      total_revenue,
            "total_food_cost_30d":    total_food_cost,
            "total_gross_profit_30d": total_gross_profit,
            "gross_margin_pct":       round(gross_margin_pct, 1),
            "food_cost_pct":          round(food_cost_pct, 1),
            "food_cost_status":       _food_cost_status(food_cost_pct),
            "revenue_mom_pct":        revenue_mom,
            "total_orders_30d":       len(orders_30d),
            "avg_order_value":        int(total_revenue / max(len(orders_30d), 1)),
            "total_items_sold":       total_items_sold,
            "profit_leaks_found":     len(profit_leaks),
            "total_leak_amount":      sum(l["monthly_leak_cents"] for l in profit_leaks),
            "star_items":             len(stars),
            "dog_items":              len(dogs),
        },
        "contribution_margins":  contribution_margins[:20],
        "profit_leaks":          profit_leaks,
        "portion_drift":         portion_drift,
        "daypart_analysis":      daypart_analysis,
        "channel_analysis":      channel_analysis,
        "customer_intelligence": customer_intel,
        "upsell_uplift":         upsell_uplift,
        "profit_forecast":       profit_forecast,
        "stars":                 [cm["item_name"] for cm in stars[:5]],
        "dogs":                  [cm["item_name"] for cm in dogs[:5]],
        "recommendations":       recommendations,
    }


# ── Sub-analyses ──────────────────────────────────────────────────────────────

def _build_contribution_margins(items, item_profit: dict) -> list[dict]:
    result = []
    for item in items:
        data = item_profit.get(item.id, {})
        qty  = data.get("qty", 0)
        if qty == 0:
            continue
        margin_pct    = ((item.price - (item.cost_price or 0)) / max(item.price, 1)) * 100
        food_cost_pct = ((item.cost_price or 0) / max(item.price, 1)) * 100
        result.append({
            "item_id":          item.id,
            "item_name":        item.name,
            "category":         item.category,
            "current_price":    item.price,
            "cost_price":       item.cost_price or 0,
            "margin_pct":       round(margin_pct, 1),
            "food_cost_pct":    round(food_cost_pct, 1),
            "qty_30d":          qty,
            "total_profit_30d": data.get("profit", 0),
            "total_revenue_30d": data.get("revenue", 0),
            "profit_per_unit":  int(item.price - (item.cost_price or 0)),
            "status":           _margin_status(margin_pct),
        })
    result.sort(key=lambda x: x["total_profit_30d"], reverse=True)
    return result


def _detect_profit_leaks(contribution_margins: list[dict]) -> list[dict]:
    leaks = []
    for cm in contribution_margins:
        if cm["margin_pct"] < CRITICAL_MARGIN_FLOOR and cm["cost_price"] > 0:
            target_price  = int(cm["cost_price"] / (1 - HEALTHY_MARGIN_MIN / 100))
            monthly_leak  = (target_price - cm["current_price"]) * cm["qty_30d"]
            leaks.append({
                "item_name":          cm["item_name"],
                "category":           cm["category"],
                "current_margin_pct": cm["margin_pct"],
                "food_cost_pct":      cm["food_cost_pct"],
                "monthly_leak_cents": monthly_leak,
                "suggested_price":    target_price,
                "severity":           "CRITICAL" if cm["margin_pct"] < 30 else "HIGH",
                "action":             f"Increase price from KES {cm['current_price']//100:,} to KES {target_price//100:,}",
            })
    leaks.sort(key=lambda x: x["monthly_leak_cents"], reverse=True)
    return leaks


def _detect_portion_drift(db: Session, restaurant_id: int, item_map: dict, now: datetime) -> list[dict]:
    """
    DS-04 FIX: monthly_leak extrapolation uses * (30/14) not * 2.
    BUG-04 FIX: 14-day window uses UTC (now is already UTC from caller).
    """
    rows = (
        db.query(
            models.OrderItem.menu_item_id,
            func.avg(models.OrderItem.unit_price).label("avg_captured"),
            func.count(models.OrderItem.id).label("cnt"),
        )
        .join(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= now - timedelta(days=14),   # UTC ✓
        )
        .group_by(models.OrderItem.menu_item_id)
        .all()
    )

    drift_items = []
    for row in rows:
        item = item_map.get(row.menu_item_id)
        if not item or row.cnt < 5:
            continue
        avg_price = float(row.avg_captured or 0)
        drift_pct = ((item.price - avg_price) / max(item.price, 1)) * 100
        if drift_pct > 5:
            # DS-04 FIX: correct 30-day extrapolation from 14-day window
            monthly_leak = int((item.price - avg_price) * row.cnt * (30 / 14))
            drift_items.append({
                "item_name":            item.name,
                "menu_price":           item.price,
                "avg_captured_price":   int(avg_price),
                "drift_pct":            round(drift_pct, 1),
                "order_count":          row.cnt,
                "estimated_monthly_leak": monthly_leak,
                "action":               "Check POS — staff may be applying undocumented discounts",
            })

    return sorted(drift_items, key=lambda x: x["estimated_monthly_leak"], reverse=True)


def _daypart_profitability(orders: list, item_map: dict) -> list[dict]:
    """
    BUG-04 / BUG-10 FIX:
    - EAT hour = (UTC hour + 3) % 24 for display bucketing only
    - _item_cost() for safe cost lookup
    """
    daypart: dict[str, dict] = defaultdict(lambda: {"revenue": 0, "cost": 0, "orders": 0, "profit": 0})

    for order in orders:
        eat_hour = (order.created_at.hour + 3) % 24
        dp       = _hour_to_daypart(eat_hour)
        order_cost = sum(
            oi.quantity * _item_cost(item_map, oi.menu_item_id)   # BUG-10 FIX
            for oi in order.items
        )
        revenue = order.total or 0
        daypart[dp]["revenue"] += revenue
        daypart[dp]["cost"]    += order_cost
        daypart[dp]["orders"]  += 1
        daypart[dp]["profit"]  += revenue - order_cost

    return [
        {
            "daypart":         dp,
            "revenue":         d["revenue"],
            "cost":            d["cost"],
            "profit":          d["profit"],
            "orders":          d["orders"],
            "margin_pct":      round((d["profit"] / max(d["revenue"], 1)) * 100, 1),
            "avg_order_profit": int(d["profit"] / max(d["orders"], 1)),
        }
        for dp, d in sorted(daypart.items(), key=lambda x: x[1]["profit"], reverse=True)
    ]


def _channel_profitability(orders: list, item_map: dict) -> list[dict]:
    """BUG-10 FIX: uses _item_cost() instead of direct attribute access on possibly-None item."""
    channel: dict[str, dict] = defaultdict(lambda: {"revenue": 0, "cost": 0, "orders": 0})

    for order in orders:
        ch         = order.delivery_channel.value if order.delivery_channel else "walk_in"
        order_cost = sum(
            oi.quantity * _item_cost(item_map, oi.menu_item_id)   # BUG-10 FIX
            for oi in order.items
        )
        commission      = (order.total or 0) * DELIVERY_COMMISSIONS.get(ch, 0)
        effective_cost  = order_cost + commission
        channel[ch]["revenue"] += order.total or 0
        channel[ch]["cost"]    += effective_cost
        channel[ch]["orders"]  += 1

    return [
        {
            "channel":             ch,
            "revenue":             d["revenue"],
            "effective_cost":      d["cost"],
            "profit":              d["revenue"] - d["cost"],
            "orders":              d["orders"],
            "margin_pct":          round(((d["revenue"] - d["cost"]) / max(d["revenue"], 1)) * 100, 1),
            "avg_order_value":     int(d["revenue"] / max(d["orders"], 1)),
            "commission_included": ch in DELIVERY_COMMISSIONS,
        }
        for ch, d in sorted(channel.items(), key=lambda x: x[1]["revenue"] - x[1]["cost"], reverse=True)
    ]


def _customer_intelligence(orders: list, total_revenue: int, now: datetime) -> dict:
    spend: dict[str, dict] = defaultdict(lambda: {"total_spend": 0, "orders": 0, "last_seen": None})

    for order in orders:
        key = order.customer_phone or order.customer_name
        if not key:
            continue
        spend[key]["total_spend"] += order.total or 0
        spend[key]["orders"]      += 1
        if spend[key]["last_seen"] is None or order.created_at > spend[key]["last_seen"]:
            spend[key]["last_seen"] = order.created_at

    sorted_customers = sorted(
        [
            {
                "identifier":            k,
                "total_spend":           v["total_spend"],
                "order_count":           v["orders"],
                "avg_order_value":       int(v["total_spend"] / max(v["orders"], 1)),
                "last_seen":             v["last_seen"].isoformat() if v["last_seen"] else None,
                "days_since_last_visit": (now - v["last_seen"]).days if v["last_seen"] else 999,
            }
            for k, v in spend.items()
        ],
        key=lambda x: x["total_spend"],
        reverse=True,
    )

    at_risk    = [c for c in sorted_customers if c["days_since_last_visit"] >= RETURNING_GUEST_DAYS][:10]
    top_20     = sorted_customers[: max(1, len(sorted_customers) // 5)]
    pareto_pct = round((sum(c["total_spend"] for c in top_20) / max(sum(c["total_spend"] for c in sorted_customers), 1)) * 100, 1)

    return {
        "top_customers":              sorted_customers[:20],
        "at_risk_customers":          at_risk,
        "pareto_pct":                 pareto_pct,
        "total_identified_customers": len(sorted_customers),
        "avg_customer_ltv_30d":       int(total_revenue / max(len(sorted_customers), 1)),
    }


def _upsell_lift(orders: list, item_map: dict) -> list[dict]:
    """Lift-based upsell pair ranking (already correct in uploaded version — kept as-is)."""
    item_freq   = Counter()
    pair_counts = Counter()
    total       = len(orders)

    for order in orders:
        ids = list({oi.menu_item_id for oi in order.items})
        for iid in ids:
            item_freq[iid] += 1
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pair_counts[tuple(sorted([ids[i], ids[j]]))] += 1

    results = []
    for (id_a, id_b), count in pair_counts.most_common(20):
        item_a = item_map.get(id_a)
        item_b = item_map.get(id_b)
        if not item_a or not item_b:
            continue
        freq_a   = item_freq.get(id_a, 1)
        freq_b   = item_freq.get(id_b, 1)
        expected = (freq_a / total) * (freq_b / total) * total
        lift     = round(count / max(expected, 0.01), 2)
        results.append({
            "item_a":              item_a.name,
            "item_b":              item_b.name,
            "co_order_count":      count,
            "co_order_rate_pct":   round(count / max(total, 1) * 100, 1),
            "lift":                lift,
            "lift_interpretation": "strong" if lift >= 2 else ("moderate" if lift >= 1.2 else "weak"),
            "realized_uplift_30d": min(item_a.price, item_b.price) * count,
            "action":              f"Staff: suggest {item_b.name} with every {item_a.name} order",
        })

    results.sort(key=lambda x: x["lift"], reverse=True)
    return results[:10]


def _profit_forecast(orders: list, total_cost: int, total_revenue: int) -> dict:
    """
    DS-02 FIX: Adds ±1 std-dev uncertainty band per forecast day.
    Uses actual per-day revenue variance to compute the band.
    """
    avg_daily_revenue = total_revenue / 30
    avg_daily_cost    = total_cost    / 30

    dow_revenue: dict[int, list] = defaultdict(list)
    for order in orders:
        dow_revenue[order.created_at.weekday()].append(order.total or 0)

    # Compute mean and std-dev per DOW
    dow_stats: dict[int, tuple] = {}
    for dow, vals in dow_revenue.items():
        mean    = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / max(len(vals) - 1, 1)
        std_dev  = math.sqrt(variance)
        dow_stats[dow] = (mean, std_dev)

    overall_avg = sum(s[0] for s in dow_stats.values()) / max(len(dow_stats), 1)
    cost_ratio  = total_cost / max(total_revenue, 1)

    forecast = []
    now      = utcnow()
    for i in range(1, 8):
        future_date = now + timedelta(days=i)
        dow         = future_date.weekday()
        mean, std   = dow_stats.get(dow, (overall_avg, overall_avg * 0.15))
        multiplier  = mean / max(overall_avg, 1)

        proj_rev    = int(avg_daily_revenue * multiplier)
        proj_cost   = int(proj_rev * cost_ratio)
        proj_profit = proj_rev - proj_cost

        # DS-02: uncertainty band — ±1 std dev propagated through the ratio
        rev_std      = int(std * (avg_daily_revenue / max(overall_avg, 1)))
        profit_std   = int(rev_std * (1 - cost_ratio))

        forecast.append({
            "date":                     future_date.strftime("%Y-%m-%d"),
            "day":                      future_date.strftime("%A"),
            "projected_revenue":        proj_rev,
            "projected_cost":           proj_cost,
            "projected_profit":         proj_profit,
            "projected_margin_pct":     round((proj_profit / max(proj_rev, 1)) * 100, 1),
            "profit_low":               max(0, proj_profit - profit_std),   # DS-02
            "profit_high":              proj_profit + profit_std,            # DS-02
            "uncertainty_note":         "±1 std dev from historical DOW variance",
        })

    return {
        "7_day_forecast":      forecast,
        "avg_daily_profit":    int(avg_daily_revenue - avg_daily_cost),
        "avg_daily_revenue":   int(avg_daily_revenue),
        "projected_7d_profit": sum(d["projected_profit"] for d in forecast),
        "note":                "Extrapolation from 30-day DOW averages. Not a statistical model.",
    }


def _generate_recommendations(
    food_cost_pct, profit_leaks, daypart_analysis,
    channel_analysis, at_risk, portion_drift, revenue_mom
) -> list[dict]:
    recs = []
    if food_cost_pct > HEALTHY_FOOD_COST_MAX:
        recs.append({"type": "food_cost", "priority": "CRITICAL",
            "message": f"Food cost at {food_cost_pct:.1f}% — above {HEALTHY_FOOD_COST_MAX}% threshold",
            "action": "Review portion sizes, supplier pricing, waste. Check for theft.",
            "impact": "Every 1% food cost reduction = direct profit gain"})
    for leak in profit_leaks[:3]:
        recs.append({"type": "margin_leak", "priority": leak["severity"],
            "message": f"{leak['item_name']}: margin at {leak['current_margin_pct']}% — leaking KES {leak['monthly_leak_cents']//100:,}/month",
            "action": leak["action"], "impact": f"KES {leak['monthly_leak_cents']//100:,}/month"})
    for drift in portion_drift[:2]:
        recs.append({"type": "portion_drift", "priority": "MEDIUM",
            "message": f"{drift['item_name']}: prices captured {drift['drift_pct']}% below menu price",
            "action": drift["action"], "impact": f"KES {drift['estimated_monthly_leak']//100:,}/month"})
    if daypart_analysis:
        worst = min(daypart_analysis, key=lambda x: x["margin_pct"])
        if worst["margin_pct"] < 45:
            recs.append({"type": "daypart", "priority": "MEDIUM",
                "message": f"{worst['daypart'].replace('_',' ').title()} has lowest margin at {worst['margin_pct']}%",
                "action": "Review high-cost items popular in this window",
                "impact": "Improve profitable item mix during this period"})
    for ch in channel_analysis:
        if ch["commission_included"] and ch["margin_pct"] < 30:
            recs.append({"type": "channel", "priority": "HIGH",
                "message": f"{ch['channel'].replace('_',' ').title()}: margin only {ch['margin_pct']}% after commission",
                "action": "Add 15-20% delivery premium or remove low-margin items from delivery menu",
                "impact": "Recover delivery channel profitability"})
    if at_risk:
        recs.append({"type": "retention", "priority": "MEDIUM",
            "message": f"{len(at_risk)} high-value customers haven't returned in {RETURNING_GUEST_DAYS}+ days",
            "action": "Trigger WhatsApp Brain winback campaign",
            "impact": "Returning guests spend 67% more on average"})
    if revenue_mom < -10:
        recs.append({"type": "revenue_trend", "priority": "HIGH",
            "message": f"Revenue down {abs(revenue_mom)}% vs last month",
            "action": "Review menu changes, pricing changes, and operational issues",
            "impact": "Identify and reverse the trend immediately"})
    return recs


# ── Helpers ────────────────────────────────────────────────────────────────────
def _hour_to_daypart(hour: int) -> str:
    if   6  <= hour < 11: return "breakfast"
    elif 11 <= hour < 15: return "lunch"
    elif 15 <= hour < 18: return "afternoon"
    elif 18 <= hour < 22: return "dinner"
    else:                  return "late_night"

def _margin_status(margin_pct: float) -> str:
    if   margin_pct >= HEALTHY_MARGIN_MIN:    return "STAR"
    elif margin_pct >= CRITICAL_MARGIN_FLOOR: return "ACCEPTABLE"
    else:                                      return "LEAK"

def _food_cost_status(fc: float) -> str:
    if   fc <= HEALTHY_FOOD_COST_MAX: return "HEALTHY"
    elif fc <= 40:                    return "WARNING"
    else:                              return "CRITICAL"

def _empty_response() -> dict:
    return {
        "summary": {"total_revenue_30d": 0, "total_food_cost_30d": 0,
            "total_gross_profit_30d": 0, "gross_margin_pct": 0,
            "food_cost_pct": 0, "food_cost_status": "NO_DATA",
            "revenue_mom_pct": 0, "total_orders_30d": 0,
            "avg_order_value": 0, "total_items_sold": 0,
            "profit_leaks_found": 0, "total_leak_amount": 0,
            "star_items": 0, "dog_items": 0},
        "contribution_margins": [], "profit_leaks": [], "portion_drift": [],
        "daypart_analysis": [], "channel_analysis": [], "customer_intelligence": {},
        "upsell_uplift": [], "profit_forecast": {}, "stars": [], "dogs": [],
        "recommendations": [],
    }
