"""
backend/ai/pricing/recommendations.py
───────────────────────────────────────
DB write layer for Pricing Intelligence. All reads are in analysis.py.

Fixes vs previous version:
  BUG-06  — db.rollback() inside IntegrityError handler wiped ALL previously
             flushed recommendations in the same transaction. Fixed by using
             db.begin_nested() (savepoints) so only the failing INSERT is
             rolled back, not the entire batch.
  BUG-03  — items_on_cooldown now calls the correct function with restaurant_id
  CLEAN   — removed the broken items_on_cooldown() stub (no restaurant_id filter)
"""

from datetime import timedelta
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
import models
from time_utils import utcnow
from .analysis import (
    fetch_item_velocities,
    items_on_cooldown_for_restaurant,
    analyse_item,
    check_delivery_margins,
)


def get_pricing_intelligence(db: Session, restaurant_id: int) -> dict:
    """Full pricing analysis — read-only."""
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

    velocities  = fetch_item_velocities(db, restaurant_id)
    on_cooldown = items_on_cooldown_for_restaurant(db, restaurant_id)   # BUG-03 FIX

    recommendations = []
    item_analyses   = []

    for item in items:
        vel = velocities.get(item.id)
        if vel is None:
            continue
        result = analyse_item(item, vel, on_cooldown=item.id in on_cooldown)
        item_analyses.append(result)
        if result.get("type"):
            recommendations.append(result)

    recommendations.sort(key=lambda x: x["monthly_impact_cents"], reverse=True)
    delivery_gaps     = check_delivery_margins(items, velocities)
    total_opportunity = sum(r["monthly_impact_cents"] for r in recommendations)

    return {
        "summary": {
            "total_recommendations":           len(recommendations),
            "total_revenue_opportunity_cents": total_opportunity,
            "surge_opportunities":             sum(1 for r in recommendations if r["type"] == "SURGE"),
            "reprice_needed":                  sum(1 for r in recommendations if r["type"] == "REPRICE"),
            "stimulate_candidates":            sum(1 for r in recommendations if r["type"] == "STIMULATE"),
            "items_below_margin_floor":        sum(1 for a in item_analyses if a["margin_pct"] < 40 and a["cost_price"] > 0),
            "items_analysed":                  len(item_analyses),
            "analysis_window_days":            30,
        },
        "recommendations": recommendations,
        "delivery_gaps":   delivery_gaps,
        "item_analyses":   sorted(item_analyses, key=lambda x: x["revenue_30d"], reverse=True),
    }


def generate_and_store_recommendations(db: Session, restaurant_id: int) -> list[int]:
    """
    Run pricing analysis and persist new recommendations.

    BUG-06 FIX: Use savepoints (db.begin_nested()) so an IntegrityError on
    one item only rolls back that single INSERT, not the entire batch.

    Previous code used db.rollback() which wiped all items flushed earlier
    in the same transaction, then db.commit() on an empty transaction.
    """
    data    = get_pricing_intelligence(db, restaurant_id)
    new_ids = []

    for rec in data["recommendations"]:
        if not rec.get("type"):
            continue

        db_rec = models.PricingRecommendation(
            restaurant_id           = restaurant_id,
            menu_item_id            = rec["item_id"],
            recommendation_type     = rec["type"],
            current_price           = rec["current_price"],
            suggested_price         = rec["suggested_price"],
            reason                  = rec["reason"],
            when_to_apply           = rec["when"],
            monthly_impact_cents    = rec["monthly_impact_cents"],
            recommendation_strength = rec["recommendation_strength"],
            status                  = "PENDING",
        )
        db.add(db_rec)

        # BUG-06 FIX: savepoint — only this INSERT is rolled back on conflict
        savepoint = db.begin_nested()
        try:
            db.flush()
            new_ids.append(db_rec.id)
            savepoint.commit()
        except IntegrityError:
            savepoint.rollback()   # Only rolls back THIS item, not the batch
            db.expunge(db_rec)     # Remove the failed object from the session

    db.commit()
    return new_ids


def get_pending_recommendations(db: Session, restaurant_id: int) -> list[dict]:
    """Fetch pending recommendations for the approval UI."""
    cutoff = utcnow() - timedelta(hours=48)
    recs = (
        db.query(models.PricingRecommendation)
        .options(joinedload(models.PricingRecommendation.menu_item))
        .filter(
            models.PricingRecommendation.restaurant_id == restaurant_id,
            models.PricingRecommendation.status == "PENDING",
            models.PricingRecommendation.created_at >= cutoff,
        )
        .order_by(models.PricingRecommendation.monthly_impact_cents.desc())
        .all()
    )

    return [
        {
            "id":                        r.id,
            "item_name":                 r.menu_item.name if r.menu_item else "Unknown",
            "category":                  r.menu_item.category if r.menu_item else "",
            "type":                      r.recommendation_type,
            "current_price":             r.current_price,
            "suggested_price":           r.suggested_price,
            "price_change_pct":          round(
                ((r.suggested_price - r.current_price) / max(r.current_price, 1)) * 100, 1
            ),
            "reason":                    r.reason,
            "when_to_apply":             r.when_to_apply,
            "monthly_impact_cents":      r.monthly_impact_cents,
            "recommendation_strength":   r.recommendation_strength,
            "created_at":                r.created_at.isoformat(),
            "expires_at":                (r.created_at + timedelta(hours=48)).isoformat(),
        }
        for r in recs
    ]


def approve_recommendation(db: Session, rec_id: int, restaurant_id: int, approved_by: str = "unknown") -> dict:
    """
    Approve a recommendation. Updates MenuItem price, marks APPROVED.
    Cross-tenant guard: validates item belongs to this restaurant.
    """
    rec = (
        db.query(models.PricingRecommendation)
        .filter(
            models.PricingRecommendation.id == rec_id,
            models.PricingRecommendation.restaurant_id == restaurant_id,
            models.PricingRecommendation.status == "PENDING",
        )
        .first()
    )
    if not rec:
        return {"error": "Recommendation not found or already processed"}

    item = (
        db.query(models.MenuItem)
        .filter(
            models.MenuItem.id == rec.menu_item_id,
            models.MenuItem.restaurant_id == restaurant_id,
        )
        .first()
    )
    if not item:
        return {"error": "Menu item not found or does not belong to this restaurant"}

    old_price       = item.price
    item.price      = rec.suggested_price
    rec.status      = "APPROVED"
    rec.actioned_at = utcnow()
    db.commit()

    # RECOMMENDATION_APPROVED was subscribed to by executive.py (records into
    # ai/memory/store.py, schedules day-7/day-14 outcome evaluation) but
    # nothing ever emitted it — found 2026-07-07 auditing the event
    # orchestration end to end.
    from events.bus import emit_async, EventType
    emit_async(EventType.RECOMMENDATION_APPROVED, {
        "restaurant_id": restaurant_id,
        "recommendation_id": rec.id,
        "item_name": item.name,
        "old_price": old_price,
        "new_price": rec.suggested_price,
        "approved_by": approved_by,
    })

    return {
        "success":    True,
        "item_name":  item.name,
        "old_price":  old_price,
        "new_price":  rec.suggested_price,
        "change_pct": round(((rec.suggested_price - old_price) / max(old_price, 1)) * 100, 1),
        "message":    f"{item.name} updated from KES {old_price // 100:,} to KES {rec.suggested_price // 100:,}",
    }


def reject_recommendation(
    db: Session, rec_id: int, restaurant_id: int, reason: str = ""
) -> dict:
    """Reject without changing price."""
    rec = (
        db.query(models.PricingRecommendation)
        .filter(
            models.PricingRecommendation.id == rec_id,
            models.PricingRecommendation.restaurant_id == restaurant_id,
            models.PricingRecommendation.status == "PENDING",
        )
        .first()
    )
    if not rec:
        return {"error": "Recommendation not found or already processed"}

    rec.status           = "REJECTED"
    rec.rejection_reason = reason
    rec.actioned_at      = utcnow()
    db.commit()
    return {"success": True, "message": "Recommendation rejected"}


def _empty_response() -> dict:
    return {
        "summary": {
            "total_recommendations": 0, "total_revenue_opportunity_cents": 0,
            "surge_opportunities": 0, "reprice_needed": 0,
            "stimulate_candidates": 0, "items_below_margin_floor": 0,
            "items_analysed": 0, "analysis_window_days": 30,
        },
        "recommendations": [], "delivery_gaps": [], "item_analyses": [],
    }
