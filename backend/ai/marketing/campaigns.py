"""
backend/ai/marketing/campaigns.py
───────────────────────────────────
Autonomous Marketing Agent — Layer 6.

Triggered automatically by:
  - Inventory surplus (avoid waste → flash special)
  - Low demand forecast (below avg → lunch deal push)
  - Lapsed high-value customers (winback campaigns)
  - Weekly high-margin item promotion (push Stars on WhatsApp)

All campaigns go through the WhatsApp Brain's send engine so they're
logged, audited, and rate-limited.

Campaign types:
  SURPLUS_SPECIAL    — "We have extra [X], 15% off today only"
  SLOW_DAY_DEAL      — "Slow afternoon, come in for our lunch special"
  WINBACK            — Individual message to lapsed customers
  WEEKLY_STAR        — Push highest-margin item of the week
"""

import os
import logging
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import models
from events.bus import emit, EventType
from ai.evaluation.tracker import write_audit_log
from time_utils import utcnow

logger = logging.getLogger("ai.marketing")

MAX_WINBACK_PER_RUN = 5      # Don't spam — max 5 winback messages per campaign run
MIN_DAYS_BETWEEN_CAMPAIGNS = 3  # Don't send to same restaurant more than once every 3 days


def run_daily_campaigns(db: Session, restaurant_id: int) -> dict:
    """
    Entry point: run all campaign checks for today.
    Called by APScheduler at 10am EAT daily.
    Returns summary of campaigns triggered.
    """
    if not _can_send_campaign(db, restaurant_id):
        return {"status": "rate_limited", "message": "Campaign already sent in last 3 days"}

    triggered = []
    owner_phone = os.getenv(f"OWNER_PHONE_{restaurant_id}", os.getenv("OWNER_PHONE", ""))

    # Check 1: Surplus inventory
    surplus = _find_surplus_inventory(db, restaurant_id)
    if surplus:
        msg = _compose_surplus_special(surplus, db, restaurant_id)
        if msg and owner_phone:
            from ai.whatsapp import send_whatsapp_message
            send_whatsapp_message(owner_phone, msg, db=db,
                                  restaurant_id=restaurant_id, message_type="campaign_surplus")
            triggered.append({"type": "SURPLUS_SPECIAL", "item": surplus["item_name"]})
            emit(EventType.CAMPAIGN_LAUNCHED, {"restaurant_id": restaurant_id, "type": "SURPLUS_SPECIAL"})

    # Check 2: Winback candidates
    winback_count = _run_winback_campaign(db, restaurant_id)
    if winback_count > 0:
        triggered.append({"type": "WINBACK", "count": winback_count})

    # Check 3: Weekly Star promotion
    star_campaign = _run_star_promotion(db, restaurant_id)
    if star_campaign:
        triggered.append({"type": "WEEKLY_STAR", "item": star_campaign})

    if triggered:
        write_audit_log(
            db, restaurant_id, "campaign_launched", "marketing_agent",
            reasoning=f"Auto-triggered campaigns: {[t['type'] for t in triggered]}",
            data_sources=["inventory_predictor", "profit_intelligence", "whatsapp_brain"],
        )

    return {"status": "completed", "campaigns_triggered": triggered}


def _can_send_campaign(db: Session, restaurant_id: int) -> bool:
    """Check if we've sent a campaign recently — rate limit."""
    cutoff = utcnow() - timedelta(days=MIN_DAYS_BETWEEN_CAMPAIGNS)
    recent = db.query(models.AgentMessage).filter(
        models.AgentMessage.restaurant_id == restaurant_id,
        models.AgentMessage.message_type.like("campaign_%"),
        models.AgentMessage.created_at    >= cutoff,
        models.AgentMessage.status        == "sent",
    ).count()
    return recent == 0


def _find_surplus_inventory(db: Session, restaurant_id: int) -> dict | None:
    """
    Find inventory items that are high-stock but close to expiry.
    These are waste-risk items — a flash special moves them.
    """
    now = utcnow()
    items = db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant_id,
        models.InventoryItem.quantity      > 0,
    ).all()

    for item in items:
        if not item.expiry_days:
            continue
        days_to_expiry = item.expiry_days

        # Recent inflow (received in last 48h = fresh stock)
        recent_in = db.query(func.sum(models.StockMovement.quantity)).filter(
            models.StockMovement.inventory_item_id == item.id,
            models.StockMovement.movement_type     == models.StockMovementType.IN,
            models.StockMovement.created_at        >= now - timedelta(hours=48),
        ).scalar() or 0

        # High stock (>3x low threshold) AND short shelf life (<5 days)
        if (item.quantity > (item.low_stock_threshold or 10) * 3 and
                days_to_expiry <= 5 and recent_in > 0):
            return {
                "item_name":      item.item_name,
                "quantity":       item.quantity,
                "unit":           item.unit,
                "days_to_expiry": days_to_expiry,
            }

    return None


def _compose_surplus_special(surplus: dict, db: Session, restaurant_id: int) -> str | None:
    """
    Find a menu item that uses this surplus ingredient and compose a special.
    """
    inventory_item = db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant_id,
        models.InventoryItem.item_name     == surplus["item_name"],
    ).first()
    if not inventory_item:
        return None

    link = db.query(models.MenuIngredient).filter(
        models.MenuIngredient.inventory_item_id == inventory_item.id,
    ).first()
    if not link or not link.menu_item:
        return None

    item = link.menu_item
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    r_name = restaurant.name if restaurant else "us"

    discounted_price = int(item.price * 0.85)  # 15% off
    return (
        f"🔥 *Today's Special at {r_name}*\n\n"
        f"*{item.name}* — 15% off today only!\n"
        f"KES ~~{item.price // 100:,}~~ → KES {discounted_price // 100:,}\n\n"
        f"Limited time offer. Come in and enjoy!\n"
        f"_Valid today only while stock lasts_"
    )


def _run_winback_campaign(db: Session, restaurant_id: int) -> int:
    """Send winback messages to lapsed customers. Returns count sent."""
    from ai.whatsapp import get_winback_candidates, send_whatsapp_message

    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    r_name = restaurant.name if restaurant else "us"

    candidates = get_winback_candidates(db, restaurant_id)
    sent = 0

    for candidate in candidates[:MAX_WINBACK_PER_RUN]:
        if not candidate.get("phone"):
            continue
        msg = candidate.get("message", "")
        if not msg:
            continue
        # Replace "us" placeholder with actual restaurant name
        msg = msg.replace("at us!", f"at {r_name}!").replace("We miss you at us", f"We miss you at {r_name}")
        result = send_whatsapp_message(
            candidate["phone"], msg, db=db,
            restaurant_id=restaurant_id, message_type="campaign_winback",
        )
        if result.get("status") == "sent":
            sent += 1
            emit(EventType.WINBACK_TRIGGERED, {
                "restaurant_id": restaurant_id,
                "customer_phone": candidate["phone"],
            })

    return sent


def _run_star_promotion(db: Session, restaurant_id: int) -> str | None:
    """Push the highest-margin available item as a weekly special."""
    # Only run on Mondays (start of week push)
    if utcnow().weekday() != 0:
        return None

    items = db.query(models.MenuItem).filter(
        models.MenuItem.restaurant_id == restaurant_id,
        models.MenuItem.is_available  == True,
        models.MenuItem.cost_price    > 0,
    ).all()
    if not items:
        return None

    star = max(items, key=lambda i: (i.price - (i.cost_price or 0)) / max(i.price, 1))
    margin = round(((star.price - (star.cost_price or 0)) / max(star.price, 1)) * 100)

    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    r_name = restaurant.name if restaurant else "us"
    owner_phone = os.getenv(f"OWNER_PHONE_{restaurant_id}", os.getenv("OWNER_PHONE", ""))

    if not owner_phone:
        return None

    msg = (
        f"🌟 *This Week's Star — {r_name}*\n\n"
        f"Your highest-margin dish this week: *{star.name}*\n"
        f"Margin: {margin}% | Price: KES {star.price // 100:,}\n\n"
        f"💡 *Tip:* Train staff to suggest {star.name} with every main order.\n"
        f"Each upsell adds KES {(star.price - (star.cost_price or 0)) // 100:,} pure profit."
    )

    from ai.whatsapp import send_whatsapp_message
    send_whatsapp_message(owner_phone, msg, db=db,
                          restaurant_id=restaurant_id, message_type="campaign_weekly_star")
    return star.name
