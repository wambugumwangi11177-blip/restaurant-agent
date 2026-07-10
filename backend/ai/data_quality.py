"""
backend/ai/data_quality.py
───────────────────────────
Cost-price data-quality agent.

Every profit and pricing number this platform produces is only as good as the
`cost_price` the owner typed for each menu item (see ai/profit/intelligence.py
and ai/pricing/analysis.py — both divide by, or compare against, cost_price).
An item with a missing or nonsensical cost price silently distorts margin, food
cost %, profit leaks, and every pricing recommendation — without ever raising an
error. This module surfaces those items so the owner can fix the input before
trusting the output.

Pure reads, deterministic thresholds — no LLM, no writes. Same shape as the
other ai/* analytics modules (summary + list), and it prioritises by real
30-day sales volume (anchored, like the rest, via analysis_clock) so the dish
that is both mis-costed AND high-selling floats to the top.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import timedelta
import models
from ai.analysis_clock import analysis_anchor

# A dish whose ingredients cost 90%+ of its price is almost always a data-entry
# error (a decimal slip), not a real menu item — genuine dishes rarely run below
# a 10% margin and would be flagged as leaks long before this. Kept deliberately
# conservative so this agent complains about typos, not about thin-margin dishes
# the profit engine already reports.
THIN_MARGIN_PCT = 10.0
# A cost price under ~3% of the sale price is very likely a units/decimal typo
# (e.g. cost entered in shillings while price is in cents, or a trailing zero
# dropped). Real food cost floors sit far above this.
SUSPICIOUS_LOW_FOOD_COST_PCT = 3.0


def get_cost_price_quality(db: Session, restaurant_id: int) -> dict:
    """
    Flag menu items whose cost_price is missing or implausible.

    Returns {summary, issues[]} where each issue carries a severity and a plain
    explanation of what it breaks, most-sold-first.
    """
    items = (
        db.query(models.MenuItem)
        .filter(
            models.MenuItem.restaurant_id == restaurant_id,
            models.MenuItem.is_available == True,
        )
        .all()
    )

    if not items:
        return _empty_response()

    # 30-day sales volume per item — anchored to the restaurant's most recent
    # order (not wall-clock), matching every other analytics module here.
    thirty_days_ago = analysis_anchor(db, restaurant_id) - timedelta(days=30)
    qty_rows = (
        db.query(
            models.OrderItem.menu_item_id,
            func.sum(models.OrderItem.quantity).label("qty"),
        )
        .join(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= thirty_days_ago,
        )
        .group_by(models.OrderItem.menu_item_id)
        .all()
    )
    qty_map = {r[0]: int(r[1] or 0) for r in qty_rows}

    issues = []
    for item in items:
        price = item.price or 0
        cost = item.cost_price or 0
        qty_30d = qty_map.get(item.id, 0)

        severity = issue = explanation = None

        if cost <= 0:
            severity = "HIGH" if qty_30d > 0 else "MEDIUM"
            issue = "MISSING_COST"
            explanation = ("No cost price set — this dish is left out of your profit "
                           "figures and can't get a margin-based price suggestion.")
        elif price <= 0:
            severity = "MEDIUM"
            issue = "MISSING_PRICE"
            explanation = "No sale price set — margin can't be computed for this dish."
        elif cost >= price:
            severity = "HIGH"
            issue = "SELLING_AT_LOSS"
            explanation = ("Ingredients cost as much as (or more than) the price — you "
                           "lose money on every one sold. Check the cost or raise the price.")
        else:
            food_cost_pct = (cost / price) * 100
            margin_pct = 100 - food_cost_pct
            if food_cost_pct < SUSPICIOUS_LOW_FOOD_COST_PCT:
                severity = "MEDIUM"
                issue = "SUSPICIOUSLY_LOW_COST"
                explanation = (f"Cost is only {round(food_cost_pct, 1)}% of the price — likely a "
                               "typo (wrong units or a missing digit). Double-check it.")
            elif margin_pct < THIN_MARGIN_PCT:
                severity = "LOW"
                issue = "THIN_MARGIN"
                explanation = (f"Only {round(margin_pct, 1)}% margin — if that cost is right this "
                               "dish barely earns; if it's a typo, fix it.")

        if issue:
            issues.append({
                "item_id": item.id,
                "item_name": item.name,
                "category": item.category,
                "price": price,
                "cost_price": cost,
                "qty_30d": qty_30d,
                "issue": issue,
                "severity": severity,
                "explanation": explanation,
            })

    # Most-sold first within severity, so the costliest data gaps lead.
    sev_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    issues.sort(key=lambda x: (sev_rank.get(x["severity"], 3), -x["qty_30d"]))

    missing = sum(1 for i in issues if i["issue"] == "MISSING_COST")
    total_items = len(items)
    priced_items = total_items - missing
    return {
        "summary": {
            "total_items": total_items,
            "items_with_issues": len(issues),
            "missing_cost_count": missing,
            "coverage_pct": round(100 * priced_items / max(total_items, 1), 1),
            "high_severity_count": sum(1 for i in issues if i["severity"] == "HIGH"),
        },
        "issues": issues,
    }


def cost_price_briefing_line(db: Session, restaurant_id: int) -> str:
    """
    One plain-language line for the morning briefing when cost-price gaps are
    material enough to distort the numbers. Empty string when data is clean.
    """
    data = get_cost_price_quality(db, restaurant_id)
    s = data["summary"]
    if s["missing_cost_count"] == 0 and s["high_severity_count"] == 0:
        return ""
    if s["missing_cost_count"] > 0:
        return (f"\n\n🧮 *Data check:* {s['missing_cost_count']} dish(es) have no cost price, "
                f"so your profit figures leave them out. Reply COSTS to see which.")
    return ("\n\n🧮 *Data check:* some dishes have cost prices that look off and may skew "
            "your profit numbers. Reply COSTS to review.")


def _empty_response() -> dict:
    return {
        "summary": {
            "total_items": 0, "items_with_issues": 0, "missing_cost_count": 0,
            "coverage_pct": 0, "high_severity_count": 0,
        },
        "issues": [],
    }
