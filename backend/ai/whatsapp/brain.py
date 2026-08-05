"""
backend/ai/whatsapp/brain.py
─────────────────────────────
WhatsApp Brain — business logic. Pure composition + DB reads. No Twilio here.

Fixes vs previous version:
  BUG-02  — Removed the dead `from database import SessionLocal as _SL` import
             that shadowed the function parameter. Scheduler functions now
             correctly document their call pattern.
  BUG-05  — compose_slow_day_alert: replaced fragile `func.extract("hour"...)`
             filter (which had midnight crossover bugs) with full UTC datetime
             range filter — compares 00:00 to current UTC hour, not extracted hours.
  BUG-11  — get_winback_candidates now passes restaurant.name to compose_winback_message
             instead of the hardcoded "us" string.
  SCALE-02 — get_critical_stock_alerts: batched the per-item usage query into a
             single GROUP BY query instead of one query per item.
  SCALE-03 — _cmd_pending_pricing: added joinedload on menu_item to prevent N+1.
"""

import os
import time
import logging
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
import models
import notifications
from time_utils import utcnow
from . import twilio_client

logger = logging.getLogger("ai.whatsapp.brain")

# ── Config ────────────────────────────────────────────────────────────────────
WINBACK_DAYS         = 21
SLOW_DAY_THRESHOLD   = 20    # % below average to trigger alert
STOCK_CRITICAL_HOURS = 6

# Quiet hours: don't nudge owners with non-urgent alerts outside service hours.
# Expressed in EAT (UTC+3). A stock alert at 3am helps no one and trains owners
# to mute the assistant. Fully-depleted items are exempt (handled at the call site).
SERVICE_START_EAT    = 7     # 07:00 EAT
SERVICE_END_EAT      = 22    # 22:00 EAT
# How many recent days a customer counts as "reachable" for a promo broadcast.
PROMO_AUDIENCE_DAYS  = 60
# Safety cap + throttle so one PROMO can't fire thousands of messages at once or
# trip the provider's per-second rate limit. The send runs in the background.
PROMO_MAX_RECIPIENTS = 500
PROMO_SEND_INTERVAL_S = 0.2


def _eat_hour(now_utc: datetime) -> int:
    return (now_utc.hour + 3) % 24


def within_service_hours(now_utc: datetime | None = None) -> bool:
    """True if the current EAT hour is inside service hours (quiet-hours gate)."""
    h = _eat_hour(now_utc or utcnow())
    return SERVICE_START_EAT <= h < SERVICE_END_EAT

# Minimum gap between two owner alerts about the SAME inventory item.
# run_stock_check fires every 2h across a 14h service day, so an item that stays
# low — which is the normal case, since restocking takes a delivery, not a
# minute — used to generate 7 identical WhatsApps a day. Pricing has had a
# 7-day cooldown since day one; stock had none. 12h means at most one nudge per
# service day per item, which is what an owner can actually act on.
STOCK_ALERT_COOLDOWN_HOURS = 12


def owner_phone_for(restaurant) -> str:
    """
    Resolve a restaurant's owner WhatsApp number. Prefers the DB column
    (models.Restaurant.owner_phone); falls back to the legacy
    OWNER_PHONE_{id} / OWNER_PHONE env vars for backward compatibility.
    """
    if getattr(restaurant, "owner_phone", None):
        return restaurant.owner_phone
    return os.getenv(f"OWNER_PHONE_{restaurant.id}", os.getenv("OWNER_PHONE", ""))


# ─────────────────────────────────────────────────────────────────────────────
# MORNING BRIEFING
# ─────────────────────────────────────────────────────────────────────────────

def compose_morning_briefing(db: Session, restaurant_id: int) -> str:
    now_utc   = utcnow()
    yesterday = (now_utc - timedelta(days=1)).date()
    lw_date   = (now_utc - timedelta(days=7)).date()

    restaurant      = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    restaurant_name = restaurant.name if restaurant else "your restaurant"

    yesterday_orders = (
        db.query(models.Order)
        .options(joinedload(models.Order.items).joinedload(models.OrderItem.menu_item))
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            func.date(models.Order.created_at) == yesterday,
        )
        .all()
    )

    yesterday_revenue = sum(o.total or 0 for o in yesterday_orders)
    yesterday_count   = len(yesterday_orders)

    lw_revenue = db.query(func.sum(models.Order.total)).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.status != models.OrderStatus.CANCELLED,
        func.date(models.Order.created_at) == lw_date,
    ).scalar() or 0

    wow_pct   = round(((yesterday_revenue - lw_revenue) / max(lw_revenue, 1)) * 100, 1)
    wow_emoji = "📈" if wow_pct >= 0 else "📉"
    wow_str   = f"+{wow_pct}%" if wow_pct >= 0 else f"{wow_pct}%"

    item_counts: dict[str, int]  = defaultdict(int)
    payment_totals: dict[str, int] = defaultdict(int)
    for order in yesterday_orders:
        method = order.payment_method.value if order.payment_method else "unknown"
        payment_totals[method] += order.total or 0
        for oi in order.items:
            name = oi.menu_item.name if oi.menu_item else "Unknown"
            item_counts[name] += oi.quantity

    top_sellers = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_str     = "\n".join(f"{i+1}. {name} — {qty} orders" for i, (name, qty) in enumerate(top_sellers)) or "No sales data"

    total_pay = sum(payment_totals.values()) or 1
    pay_str   = (
        f"M-Pesa: {round(payment_totals.get('mpesa',0)/total_pay*100)}% | "
        f"Cash: {round(payment_totals.get('cash',0)/total_pay*100)}% | "
        f"Card: {round(payment_totals.get('card',0)/total_pay*100)}%"
    )

    stock_alerts = get_critical_stock_alerts(db, restaurant_id)
    stock_str    = f"\n\n⚠️ *Stock Alert:* {stock_alerts[0]['item_name']} is low — {stock_alerts[0]['action']}" if stock_alerts else ""

    pending_count = db.query(models.PricingRecommendation).filter(
        models.PricingRecommendation.restaurant_id == restaurant_id,
        models.PricingRecommendation.status == "PENDING",
        models.PricingRecommendation.created_at >= utcnow() - timedelta(hours=48),
    ).count()
    pricing_str = f"\n\n💡 *{pending_count} pricing recommendation(s) awaiting your approval.* Reply PENDING to review." if pending_count > 0 else ""

    today_res = db.query(models.Reservation).filter(
        models.Reservation.restaurant_id == restaurant_id,
        models.Reservation.reservation_date == now_utc.date(),
        models.Reservation.status == models.ReservationStatus.CONFIRMED,
    ).count()
    res_str = f"\n\n📅 *Today:* {today_res} reservation(s) booked." if today_res > 0 else ""

    focus = _daily_focus(db, restaurant_id, now_utc)

    from ai.data_quality import cost_price_briefing_line
    data_check_str = cost_price_briefing_line(db, restaurant_id)

    # Plain-language "why" clauses on each section so the briefing itself teaches
    # a non-analyst owner what the numbers mean — the same explain-it-simply goal
    # as the dashboard "How this works" panels, in the channel they read daily.
    return (
        f"🌅 *Good morning! Here's {restaurant_name}*\n\n"
        f"📊 *Yesterday's Performance*\n"
        f"Revenue: KES {yesterday_revenue // 100:,} {wow_emoji} ({wow_str} vs the same day last week)\n"
        f"Orders: {yesterday_count}\n\n"
        f"🏆 *Top Sellers* — your best-moving dishes; keep these stocked and pushed\n{top_str}\n\n"
        f"💳 *Payments* — how customers paid\n{pay_str}"
        f"{stock_str}{pricing_str}{res_str}{data_check_str}\n\n"
        f"🎯 *Today's Focus* — the one move with the biggest payoff today\n{focus}\n\n"
        f"_Powered by {restaurant_name} AI_ 🤖\n"
        f"_Reply SALES, STOCK, PENDING, or TONIGHT for live data · HELP for all commands_"
    )


def _daily_focus(db: Session, restaurant_id: int, now: datetime) -> str:
    items = db.query(models.MenuItem).filter(
        models.MenuItem.restaurant_id == restaurant_id,
        models.MenuItem.is_available == True,
        models.MenuItem.cost_price > 0,
    ).all()
    if not items:
        return "Focus on delivering great service today."
    best   = max(items, key=lambda i: ((i.price - (i.cost_price or 0)) / max(i.price, 1)))
    margin = round(((best.price - (best.cost_price or 0)) / max(best.price, 1)) * 100)
    dow    = now.weekday()
    is_weekend = dow >= 4
    day_name   = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][dow]
    if is_weekend:
        return f"Weekend rush incoming 🔥 Prep extra {best.name} (your {margin}% margin star). Fully stocked before 5pm."
    return f"{day_name} tip: Push {best.name} — {margin}% margin. Train staff to suggest it with every main order."


# ─────────────────────────────────────────────────────────────────────────────
# STOCK ALERTS  (SCALE-02 FIX: batched usage query)
# ─────────────────────────────────────────────────────────────────────────────

def get_critical_stock_alerts(db: Session, restaurant_id: int) -> list[dict]:
    """
    SCALE-02 FIX: Replaced N+1 per-item usage query with a single
    GROUP BY query that fetches 3-day OUT movements for ALL items at once.
    """
    items = db.query(models.InventoryItem).filter(
        models.InventoryItem.restaurant_id == restaurant_id,
    ).all()

    below_threshold = [i for i in items if i.quantity <= (i.low_stock_threshold or 0)]
    if not below_threshold:
        return []

    item_ids      = [i.id for i in below_threshold]
    three_days_ago = utcnow() - timedelta(days=3)

    # Single batched query for all at-risk items
    usage_rows = (
        db.query(
            models.StockMovement.inventory_item_id,
            func.sum(models.StockMovement.quantity).label("total_out"),
        )
        .filter(
            models.StockMovement.inventory_item_id.in_(item_ids),
            models.StockMovement.movement_type == models.StockMovementType.OUT,
            models.StockMovement.created_at >= three_days_ago,
        )
        .group_by(models.StockMovement.inventory_item_id)
        .all()
    )
    usage_map = {row.inventory_item_id: float(row.total_out or 0) for row in usage_rows}

    alerts = []
    for item in below_threshold:
        avg_daily_usage = usage_map.get(item.id, 0) / 3
        hours_remaining = (item.quantity / max(avg_daily_usage, 0.01)) * 24 if avg_daily_usage > 0 else 999
        severity = "URGENT" if hours_remaining <= STOCK_CRITICAL_HOURS else "WARNING"
        action   = f"Reorder now — ~{int(hours_remaining)}h remaining" if hours_remaining < 24 else "Reorder today"
        alerts.append({
            "inventory_item_id": item.id,
            "item_name":       item.item_name,
            "current_qty":     item.quantity,
            "unit":            item.unit,
            "threshold":       item.low_stock_threshold,
            "hours_remaining": round(hours_remaining, 1),
            "severity":        severity,
            "action":          action,
        })

    return sorted(alerts, key=lambda x: x["hours_remaining"])


def compose_stock_alert(alert: dict) -> str:
    emoji = "🚨" if alert["severity"] == "URGENT" else "⚠️"
    return (
        f"{emoji} *Stock Alert*\n\n"
        f"*{alert['item_name']}* is critically low\n"
        f"Current: {alert['current_qty']} {alert['unit']}\n"
        f"~{alert['hours_remaining']:.0f}h of service remaining\n\n"
        f"*Action:* {alert['action']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# SLOW DAY ALERT  (BUG-05 FIX: full UTC datetime range, no extracted hours)
# ─────────────────────────────────────────────────────────────────────────────

def compose_slow_day_alert(db: Session, restaurant_id: int) -> str | None:
    """
    BUG-05 FIX: Use full UTC datetime range instead of func.extract("hour").
    The original `(current_hour - 3) % 24` had midnight crossover bugs and
    included all hours at edge-of-day times.

    Correct approach: compare today's revenue from UTC midnight to now,
    vs same window on previous same-DOW dates.
    """
    now_utc      = utcnow()
    eat_hour     = (now_utc.hour + 3) % 24
    if eat_hour < 14:
        return None   # Only check after 2pm EAT

    today_start  = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's revenue from midnight UTC to now
    today_revenue = db.query(func.sum(models.Order.total)).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= today_start,
        models.Order.created_at <= now_utc,
    ).scalar() or 0

    # Same UTC window (midnight to now) on the same DOW for the last 4 weeks
    hours_elapsed = (now_utc - today_start).seconds / 3600
    past_revenues = []
    for weeks_back in range(1, 5):
        past_start = today_start - timedelta(weeks=weeks_back)
        past_end   = past_start + timedelta(hours=hours_elapsed)
        rev = db.query(func.sum(models.Order.total)).filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= past_start,
            models.Order.created_at <= past_end,
        ).scalar() or 0
        if rev > 0:
            past_revenues.append(rev)

    if not past_revenues:
        return None

    avg_revenue = sum(past_revenues) / len(past_revenues)
    gap_pct     = ((avg_revenue - today_revenue) / max(avg_revenue, 1)) * 100

    if gap_pct < SLOW_DAY_THRESHOLD:
        return None

    dow      = now_utc.weekday()
    day_name = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][dow]
    return (
        f"📊 *Slow Day Alert*\n\n"
        f"Revenue at {eat_hour:02d}:00 EAT: KES {today_revenue // 100:,}\n"
        f"Usual {day_name} by now: KES {int(avg_revenue) // 100:,}\n"
        f"Gap: {gap_pct:.0f}% below average\n\n"
        f"*Suggestion:* Consider a quick special or push high-margin items on social media now.\n"
        f"💬 Reply *PROMO <your offer>* to text a special to your regulars right now "
        f"(e.g. PROMO 15% off all mains till 9pm)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# PROMO BROADCAST  (owner-triggered blast to reachable customers)
# ─────────────────────────────────────────────────────────────────────────────

def promo_audience_count(db: Session, restaurant_id: int) -> int:
    """
    Fast count of who a promo would reach: customers who ordered in the last
    PROMO_AUDIENCE_DAYS, gave consent, and haven't opted out. Used to reply to the
    owner instantly before the (backgrounded) send runs.
    """
    return len(_promo_recipients(db, restaurant_id))


def _promo_recipients(db: Session, restaurant_id: int) -> list[str]:
    """De-duplicated, consented, non-opted-out phone list for a promo blast."""
    from .optout import canonical, is_opted_out

    cutoff = utcnow() - timedelta(days=PROMO_AUDIENCE_DAYS)
    rows = (
        db.query(models.Order.customer_phone)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.customer_phone != "",
            models.Order.customer_phone.isnot(None),
            models.Order.created_at >= cutoff,
        )
        .distinct()
        .all()
    )
    # Marketing gate: only message customers with a recorded consent (any purpose).
    # Stricter than the STOP-only opt-out used for transactional messages —
    # a promo is marketing, so it needs a positive consent signal, not just the
    # absence of an opt-out. See models.CustomerConsent.
    consented = {
        canonical(c.customer_phone)
        for c in db.query(models.CustomerConsent.customer_phone)
        .filter(models.CustomerConsent.restaurant_id == restaurant_id)
        .all()
    }

    seen: set[str] = set()
    recipients: list[str] = []
    for (phone,) in rows:
        key = canonical(phone)
        if not key or key in seen:
            continue
        seen.add(key)
        if key not in consented:
            continue
        if is_opted_out(db, phone):
            continue
        recipients.append(phone)
    return recipients


def broadcast_promo(db: Session, restaurant_id: int, offer_text: str) -> dict:
    """
    Send a one-off promo to consented, non-opted-out customers who ordered in the
    last PROMO_AUDIENCE_DAYS. Capped at PROMO_MAX_RECIPIENTS with a light throttle
    so a large list can't hammer the provider. Returns {sent, skipped, audience}.

    Intended to run in the BACKGROUND (see _cmd_promo) — the send loop is too slow
    to block the inbound webhook.
    """
    restaurant      = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    restaurant_name = restaurant.name if restaurant else "us"

    recipients = _promo_recipients(db, restaurant_id)
    capped = recipients[:PROMO_MAX_RECIPIENTS]

    message = (
        f"📣 *{restaurant_name}*\n\n{offer_text}\n\n"
        f"See you soon! 🍽️\n_Reply STOP to opt out._"
    )

    sent = skipped = 0
    for phone in capped:
        result = send_whatsapp_message(
            phone, message, db=db, restaurant_id=restaurant_id,
            message_type="promo", channel="whatsapp", fallback_sms=True,
        )
        if result["status"] == "sent":
            sent += 1
        else:
            skipped += 1
        time.sleep(PROMO_SEND_INTERVAL_S)   # gentle throttle for provider rate limits
    return {"sent": sent, "skipped": skipped, "audience": len(recipients)}


def compose_receipt(db: Session, order, mpesa_ref: str = "") -> str:
    """
    Itemized customer receipt for a paid order. Works for any payment method —
    M-Pesa ref line only shows when present. Renders rich for WhatsApp; the SMS
    transport auto-strips formatting (twilio_client.to_sms).
    """
    restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == order.restaurant_id).first()
    r_name = restaurant.name if restaurant else "the restaurant"
    method = order.payment_method.value.replace("_", " ").title() if order.payment_method else "Paid"

    lines = [f"🧾 *{r_name} — Receipt*\n"]
    for oi in order.items:
        name = oi.menu_item.name if oi.menu_item else "Item"
        line_total = (oi.quantity or 0) * (oi.unit_price or 0)
        lines.append(f"{int(oi.quantity)}× {name} — KES {line_total // 100:,}")

    lines.append(f"\n*Total: KES {(order.total or 0) // 100:,}*")
    lines.append(f"Paid by: {method}")
    if mpesa_ref:
        lines.append(f"M-Pesa Ref: {mpesa_ref}")
    lines.append(f"Order #{order.id}")
    lines.append(f"\nThank you for dining with us! 🍽️")
    lines.append("_Reply REORDER to order the same again · STOP to opt out._")
    return "\n".join(lines)


def compose_pricing_approved_message(item_name: str, old_price: int, new_price: int) -> str:
    change_pct = round(((new_price - old_price) / max(old_price, 1)) * 100, 1)
    direction  = "increased" if new_price > old_price else "decreased"
    return (
        f"✅ *Price Updated*\n\n"
        f"*{item_name}* {direction} from KES {old_price // 100:,} → KES {new_price // 100:,} "
        f"({'+' if change_pct > 0 else ''}{change_pct}%)\n\n"
        f"I'll include the demand impact in tomorrow's morning briefing."
    )


# ─────────────────────────────────────────────────────────────────────────────
# WINBACK  (BUG-11 FIX: pass restaurant_name from DB)
# ─────────────────────────────────────────────────────────────────────────────

def get_winback_candidates(db: Session, restaurant_id: int) -> list[dict]:
    """
    BUG-11 FIX: passes restaurant.name to compose_winback_message instead of "us".
    BUG-15 (already fixed in uploaded version): favourite item fetched in batch.
    """
    cutoff = utcnow() - timedelta(days=WINBACK_DAYS)

    restaurant      = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
    restaurant_name = restaurant.name if restaurant else "us"

    customer_rows = (
        db.query(
            models.Order.customer_phone,
            models.Order.customer_name,
            func.max(models.Order.created_at).label("last_order"),
            func.sum(models.Order.total).label("total_spend"),
            func.count(models.Order.id).label("order_count"),
        )
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.customer_phone != "",
            models.Order.customer_phone.isnot(None),
        )
        .group_by(models.Order.customer_phone, models.Order.customer_name)
        .having(func.max(models.Order.created_at) <= cutoff)
        .order_by(func.sum(models.Order.total).desc())
        .limit(50)
        .all()
    )

    if not customer_rows:
        return []

    phones = [r.customer_phone for r in customer_rows]

    fav_rows = (
        db.query(
            models.Order.customer_phone,
            models.MenuItem.name,
            func.sum(models.OrderItem.quantity).label("qty"),
        )
        .join(models.OrderItem, models.Order.id == models.OrderItem.order_id)
        .join(models.MenuItem, models.OrderItem.menu_item_id == models.MenuItem.id)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.customer_phone.in_(phones),
        )
        .group_by(models.Order.customer_phone, models.MenuItem.name)
        .order_by(func.sum(models.OrderItem.quantity).desc())
        .all()
    )

    fav_map: dict[str, str] = {}
    for row in fav_rows:
        if row.customer_phone not in fav_map:
            fav_map[row.customer_phone] = row.name

    # Honour opt-outs at selection time too (the send engine also gates, but
    # filtering here keeps opted-out customers out of counts and message logs).
    from .optout import is_opted_out

    now_utc    = utcnow()
    candidates = []
    for row in customer_rows:
        if is_opted_out(db, row.customer_phone):
            continue
        days_away = (now_utc - row.last_order).days
        fav_item  = fav_map.get(row.customer_phone)
        candidates.append({
            "phone":       row.customer_phone,
            "name":        row.customer_name,
            "last_order":  row.last_order.isoformat(),
            "days_away":   days_away,
            "total_spend": row.total_spend,
            "order_count": row.order_count,
            "fav_item":    fav_item,
            "message":     compose_winback_message(
                restaurant_name = restaurant_name,   # BUG-11 FIX: real name
                name      = row.customer_name or "valued customer",
                fav_item  = fav_item,
                days_away = days_away,
            ),
        })

    return candidates


# ─────────────────────────────────────────────────────────────────────────────
# RESERVATION REMINDERS  (cut no-shows — the dashboard recommends these)
# ─────────────────────────────────────────────────────────────────────────────

def compose_reservation_reminder(reservation, restaurant_name: str) -> str:
    t = reservation.reservation_time.strftime("%H:%M") if reservation.reservation_time else "your booked time"
    return (
        f"📅 *Reservation reminder — {restaurant_name}*\n\n"
        f"Hi {reservation.customer_name or 'there'}, we're holding a table for "
        f"{reservation.party_size} today at {t} EAT.\n\n"
        f"Reply *YES* to confirm or *NO* to cancel. See you soon! 🍽️"
    )


def run_reservation_reminders(SessionLocal) -> None:
    """
    Send a same-day reminder to each confirmed reservation with a phone number.
    Idempotent within the day: `reminder_sent_at` is stamped once the reminder is
    sent and re-checked here, so a scheduler misfire or restart can't double-send.
    Tries WhatsApp, falls back to SMS; opt-out is honoured at the send choke point.
    """
    db = SessionLocal()
    try:
        now = utcnow()
        today = now.date()
        day_start = datetime(today.year, today.month, today.day)
        for restaurant in db.query(models.Restaurant).all():
            r_name = restaurant.name
            reservations = db.query(models.Reservation).filter(
                models.Reservation.restaurant_id == restaurant.id,
                models.Reservation.reservation_date == today,
                models.Reservation.status == models.ReservationStatus.CONFIRMED,
                models.Reservation.customer_phone != "",
                # Not already reminded today (NULL, or stamped on a previous day).
                (models.Reservation.reminder_sent_at.is_(None))
                | (models.Reservation.reminder_sent_at < day_start),
            ).all()
            for res in reservations:
                msg = compose_reservation_reminder(res, r_name)
                send_whatsapp_message(
                    res.customer_phone, msg, db=db, restaurant_id=restaurant.id,
                    message_type="reservation_reminder", channel="whatsapp", fallback_sms=True,
                )
                res.reminder_sent_at = now
            db.commit()
    finally:
        db.close()


def compose_winback_message(restaurant_name: str, name: str, fav_item: str | None, days_away: int) -> str:
    fav_str = f"Your favourite *{fav_item}* is waiting for you." if fav_item else "We have something special waiting."
    return (
        f"👋 Hi {name}!\n\n"
        f"We miss you at {restaurant_name}! {fav_str}\n\n"
        f"It's been {days_away} days — come back and enjoy *10% off* your next visit.\n"
        f"Just show this message when you arrive.\n\n"
        f"See you soon! 🍽️\n\n"
        f"_Reply STOP to opt out of these messages._"
    )


def winback_reachable(db: Session, restaurant_id: int) -> int:
    """
    How many lapsed regulars a win-back blast could actually reach right now:
    a candidate must have given marketing consent AND not opted out. Mirrors the
    marketing gate promo uses (positive consent, not just absence of a STOP), so
    win-back — which is marketing, not transactional — is held to the same bar.
    """
    from .optout import canonical, is_opted_out
    candidates = get_winback_candidates(db, restaurant_id)
    if not candidates:
        return 0
    consented = {
        canonical(c.customer_phone)
        for c in db.query(models.CustomerConsent.customer_phone)
        .filter(models.CustomerConsent.restaurant_id == restaurant_id)
        .all()
    }
    reachable = 0
    for c in candidates:
        key = canonical(c["phone"])
        if key and key in consented and not is_opted_out(db, c["phone"]):
            reachable += 1
    return reachable


def broadcast_winback(db: Session, restaurant_id: int) -> dict:
    """
    Send the personalised win-back message to each lapsed regular who gave
    marketing consent and hasn't opted out. Logs message_type="campaign_winback"
    at the single send choke point (which also re-checks opt-out), capped at
    PROMO_MAX_RECIPIENTS with a light throttle. Returns {sent, skipped, audience}.

    Intended to run in the BACKGROUND (see the /ai/marketing/winback route) — the
    per-customer send loop is far too slow to block a request.
    """
    import time as _time
    from .optout import canonical, is_opted_out

    candidates = get_winback_candidates(db, restaurant_id)
    if not candidates:
        return {"sent": 0, "skipped": 0, "audience": 0}

    consented = {
        canonical(c.customer_phone)
        for c in db.query(models.CustomerConsent.customer_phone)
        .filter(models.CustomerConsent.restaurant_id == restaurant_id)
        .all()
    }

    sent = skipped = audience = 0
    for c in candidates:
        key = canonical(c["phone"])
        # Marketing gate: positive consent + not opted out. Everyone else is
        # skipped silently (they were never a legal recipient).
        if not key or key not in consented or is_opted_out(db, c["phone"]):
            continue
        audience += 1
        if sent + skipped >= PROMO_MAX_RECIPIENTS:
            continue
        result = send_whatsapp_message(
            c["phone"], c["message"], db=db, restaurant_id=restaurant_id,
            message_type="campaign_winback", channel="whatsapp", fallback_sms=True,
        )
        if result["status"] == "sent":
            sent += 1
        else:
            skipped += 1
        _time.sleep(PROMO_SEND_INTERVAL_S)

    return {"sent": sent, "skipped": skipped, "audience": audience}


# ─────────────────────────────────────────────────────────────────────────────
# SEND ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def send_whatsapp_message(
    to_number: str,
    message: str,
    db: Session | None = None,
    restaurant_id: int | None = None,
    message_type: str = "general",
    channel: str = "whatsapp",
    fallback_sms: bool = False,
    media_url: str | None = None,
) -> dict:
    """
    Send an outbound message and log it. Despite the historical name this is the
    single choke point for ALL channels — pass channel="sms" to send SMS, or
    fallback_sms=True to try WhatsApp first and drop to SMS if it doesn't send
    (for the many Kenyan customers who aren't on WhatsApp). The opt-out gate is
    honoured once, up front, for every channel.
    """
    # Opt-out suppression: honour a customer's STOP everywhere. This is the
    # single choke point every outbound message passes through, so gating here
    # covers winback, campaigns, and any future sender. Requires a db handle to
    # check the suppression list; callers without one (rare) can't be filtered.
    if db is not None:
        from .optout import is_opted_out
        if is_opted_out(db, to_number):
            if restaurant_id:
                _log_message(db, restaurant_id, to_number, message, message_type, "suppressed_optout")
            return {"status": "suppressed_optout", "sid": None}

    result = twilio_client.send(to_number, message, channel=channel, media_url=media_url)

    # Fallback: if a WhatsApp send didn't actually go out (not configured / error /
    # undeliverable) and the caller allowed it, try SMS — the customer may simply
    # not be on WhatsApp. Never fall back on an opt-out suppression.
    used_channel = channel
    if fallback_sms and channel == "whatsapp" and result["status"] not in ("sent", "suppressed_optout"):
        sms_result = twilio_client.send(to_number, message, channel="sms")
        if sms_result["status"] == "sent":
            result, used_channel = sms_result, "sms"

    if db and restaurant_id:
        _log_message(db, restaurant_id, to_number, message, f"{message_type}:{used_channel}",
                     result["status"], result.get("sid"))
    return result


def owner_channel_for(restaurant) -> str:
    """Owner's preferred alert channel: 'whatsapp' (default), 'sms', or 'both'."""
    return (getattr(restaurant, "owner_channel", None) or "whatsapp").lower()


def send_to_owner(db: Session, restaurant, message: str, message_type: str) -> None:
    """
    Deliver an owner alert over their preferred channel(s). 'both' sends WhatsApp
    and SMS; 'sms' sends SMS only; anything else defaults to WhatsApp with an SMS
    fallback if WhatsApp doesn't go through. Resolves the owner phone once.
    """
    phone = owner_phone_for(restaurant)
    if not phone:
        logger.warning(f"[WhatsApp Brain] No owner phone for restaurant {restaurant.id}")
        return

    pref = owner_channel_for(restaurant)
    if pref == "sms":
        send_whatsapp_message(phone, message, db=db, restaurant_id=restaurant.id,
                              message_type=message_type, channel="sms")
    elif pref == "both":
        send_whatsapp_message(phone, message, db=db, restaurant_id=restaurant.id,
                              message_type=message_type, channel="whatsapp")
        send_whatsapp_message(phone, message, db=db, restaurant_id=restaurant.id,
                              message_type=message_type, channel="sms")
    else:
        send_whatsapp_message(phone, message, db=db, restaurant_id=restaurant.id,
                              message_type=message_type, channel="whatsapp", fallback_sms=True)


def _log_message(db, restaurant_id, to_number, message, message_type, status, sid=None):
    try:
        db.add(models.AgentMessage(
            restaurant_id = restaurant_id,
            recipient     = to_number,
            message_body  = message[:2000],
            message_type  = message_type,
            status        = status,
            twilio_sid    = sid or "",
        ))
        db.commit()
    except Exception as exc:
        logger.warning(f"[WhatsApp Brain] Failed to log message: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# OWNER COMMAND HANDLER
# ─────────────────────────────────────────────────────────────────────────────

def handle_owner_command(db: Session, restaurant_id: int, message: str) -> str:
    cmd = message.strip().lower()

    COMMANDS = {
        "sales": _cmd_sales_today, "sales today": _cmd_sales_today, "revenue": _cmd_sales_today,
        "stock": _cmd_stock, "inventory": _cmd_stock, "stock levels": _cmd_stock,
        "pending": _cmd_pending_pricing, "pricing": _cmd_pending_pricing, "approvals": _cmd_pending_pricing,
        "tonight": _cmd_tonight, "bookings": _cmd_tonight, "reservations": _cmd_tonight,
        "winback": _cmd_winback_summary, "win back": _cmd_winback_summary,
        "costs": _cmd_cost_quality, "cost": _cmd_cost_quality, "data": _cmd_cost_quality,
        "help": _cmd_help, "commands": _cmd_help, "?": _cmd_help,
    }

    if cmd in COMMANDS:
        return COMMANDS[cmd](db, restaurant_id)

    if cmd.startswith("approve "):
        try:
            return _cmd_approve(db, restaurant_id, int(cmd.split()[1]))
        except (ValueError, IndexError):
            return "❌ Invalid format. Try: APPROVE 3"

    if cmd.startswith("reject "):
        try:
            return _cmd_reject(db, restaurant_id, int(cmd.split()[1]))
        except (ValueError, IndexError):
            return "❌ Invalid format. Try: REJECT 3"

    if cmd.startswith("promo "):
        # Preserve the original casing/punctuation of the offer text.
        offer = message.strip()[len("promo "):].strip()
        if not offer:
            return "❌ Add your offer. Try: PROMO 15% off all mains till 9pm"
        return _cmd_promo(db, restaurant_id, offer)

    # Free-form text falls through to the LLM orchestrator (Phase 2 —
    # directives/012_agentic_roadmap.md). Known commands above never reach
    # here, so this only spends tokens on messages that actually need them.
    from .orchestrator import handle_natural_language
    return handle_natural_language(db, restaurant_id, message)


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMER MESSAGE HANDLER  (two-way replies from diners, not owners)
# ─────────────────────────────────────────────────────────────────────────────

def _find_last_customer_order(db: Session, restaurant_id: int, phone: str):
    """Most recent non-cancelled order for this customer at this restaurant.
    A SQL last-9-digit LIKE narrows to this customer regardless of stored format
    (0712…, +254712…, 254712…), so a returning diner is found even at a busy
    restaurant; canonical() then confirms to rule out a rare suffix collision."""
    from .optout import canonical, last9
    key = canonical(phone)
    if not key:
        return None
    q = (
        db.query(models.Order)
        .options(joinedload(models.Order.items).joinedload(models.OrderItem.menu_item))
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.customer_phone != "",
        )
    )
    suf = last9(phone)
    if suf:
        q = q.filter(models.Order.customer_phone.like(f"%{suf}%"))
    for o in q.order_by(models.Order.created_at.desc()).limit(50).all():
        if canonical(o.customer_phone) == key:
            return o
    return None


def handle_customer_message(db: Session, restaurant_id: int, phone: str, message: str) -> str:
    """
    Route an inbound message from a diner (not the owner). Supports REORDER and a
    1–5 star rating (from the receipt prompt). Anything else gets a friendly
    pointer. Ratings of 2 or below privately alert the owner for service recovery.
    """
    text = message.strip().lower()

    # Reservation confirm/cancel (reply to a reminder), keyed on today's booking.
    if text in {"yes", "y", "confirm", "no", "n", "cancel"}:
        from .optout import canonical
        key = canonical(phone)
        res = None
        if key:
            todays = db.query(models.Reservation).filter(
                models.Reservation.restaurant_id == restaurant_id,
                models.Reservation.reservation_date == utcnow().date(),
                models.Reservation.customer_phone != "",
            ).all()
            res = next((r for r in todays if canonical(r.customer_phone) == key), None)
        if res:
            if text in {"no", "n", "cancel"}:
                res.status = models.ReservationStatus.CANCELLED
                db.commit()
                return "Your reservation has been cancelled. We hope to see you another time. 🙏"
            res.status = models.ReservationStatus.CONFIRMED
            db.commit()
            return "Your reservation is confirmed — see you today! 🍽️"
        # No booking to act on; fall through to the generic pointer below.

    # Star rating: a lone digit 1–5.
    if text in {"1", "2", "3", "4", "5"}:
        rating = int(text)
        last = _find_last_customer_order(db, restaurant_id, phone)
        db.add(models.CustomerFeedback(
            restaurant_id  = restaurant_id,
            order_id       = last.id if last else None,
            customer_phone = phone,
            rating         = rating,
        ))
        db.commit()
        if rating <= 2:
            restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
            if restaurant:
                alert = (f"⚠️ *Low rating received* — {rating}/5"
                         + (f" on Order #{last.id}" if last else "")
                         + f"\nFrom: {phone}\nReach out to make it right.")
                notifications.deliver(
                    db, restaurant,
                    title=f"Low rating: {rating}/5",
                    body=(f"From {phone}" + (f" on Order #{last.id}" if last else "")
                          + ". Reach out to make it right."),
                    category="feedback_alert", severity=notifications.SEVERITY_WARNING,
                    audience=notifications.AUDIENCE_ADMIN,
                    link="/dashboard/orders", whatsapp_body=alert,
                )
            return "Thank you for the honest feedback — we're sorry we fell short and will do better. 🙏"
        return "Thank you for the *" + text + "★* rating! We'd love to see you again soon. 🍽️"

    # Reorder: acknowledge and notify staff/owner. Deliberately does NOT auto-create
    # an order (price/availability/payment need a human) — it flags intent instead.
    if text == "reorder":
        last = _find_last_customer_order(db, restaurant_id, phone)
        if not last:
            return "We couldn't find a previous order for this number yet. Reply with what you'd like, or visit us to order."
        items_str = ", ".join(
            f"{int(oi.quantity)}× {oi.menu_item.name if oi.menu_item else 'item'}" for oi in last.items
        )
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
        if restaurant:
            notice = (f"🔁 *Reorder request* from {phone}\n{items_str}\n"
                      f"Previous total: KES {(last.total or 0) // 100:,}. Confirm with the customer.")
            notifications.deliver(
                db, restaurant,
                title=f"Reorder request from {phone}",
                body=f"{items_str}. Previous total: KES {(last.total or 0) // 100:,}. Confirm with the customer.",
                category="reorder_request", severity=notifications.SEVERITY_INFO,
                audience=notifications.AUDIENCE_ALL,
                link="/dashboard/orders", whatsapp_body=notice,
            )
        return (f"Got it! We've sent your usual to the team: {items_str}.\n"
                f"They'll confirm shortly. 🍽️")

    return ("Thanks for your message! Reply *REORDER* to repeat your last order, or a number "
            "*1–5* to rate your visit. To place a new order, visit us or ask our staff.")


def _cmd_sales_today(db: Session, restaurant_id: int) -> str:
    now_utc = utcnow()
    orders  = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.status != models.OrderStatus.CANCELLED,
        func.date(models.Order.created_at) == now_utc.date(),
    ).all()
    revenue  = sum(o.total or 0 for o in orders)
    count    = len(orders)
    paid     = sum(1 for o in orders if o.is_paid)
    pending  = sum(o.total or 0 for o in orders if not o.is_paid)
    eat_time = (now_utc + timedelta(hours=3)).strftime("%H:%M")
    return (
        f"💰 *Sales Today*\n\nRevenue: KES {revenue // 100:,}\n"
        f"Orders: {count} ({paid} paid)\nPending payment: KES {pending // 100:,}\n"
        f"Avg order: KES {(revenue // max(count, 1)) // 100:,}\n_As of {eat_time} EAT_"
    )


def _cmd_stock(db: Session, restaurant_id: int) -> str:
    alerts = get_critical_stock_alerts(db, restaurant_id)
    if not alerts:
        return "✅ *All stock levels are healthy.*"
    lines = ["⚠️ *Critical Stock Levels*\n"]
    for a in alerts[:5]:
        lines.append(f"• *{a['item_name']}*: {a['current_qty']} {a['unit']} (~{a['hours_remaining']:.0f}h left)")
    return "\n".join(lines)


def _cmd_pending_pricing(db: Session, restaurant_id: int) -> str:
    """SCALE-03 FIX: joinedload on menu_item prevents N+1."""
    recs = (
        db.query(models.PricingRecommendation)
        .options(joinedload(models.PricingRecommendation.menu_item))   # SCALE-03 FIX
        .filter(
            models.PricingRecommendation.restaurant_id == restaurant_id,
            models.PricingRecommendation.status == "PENDING",
            models.PricingRecommendation.created_at >= utcnow() - timedelta(hours=48),
        )
        .order_by(models.PricingRecommendation.monthly_impact_cents.desc())
        .all()
    )
    if not recs:
        return "✅ No pending pricing recommendations right now."
    lines = ["💡 *Pending Pricing Recommendations*\n"]
    for i, r in enumerate(recs[:5], 1):
        item_name = r.menu_item.name if r.menu_item else "Unknown"
        direction = "↑" if r.suggested_price > r.current_price else "↓"
        lines.append(
            f"*{i}. {item_name}*\n"
            f"   KES {r.current_price // 100:,} → KES {r.suggested_price // 100:,} {direction}\n"
            f"   Impact: +KES {r.monthly_impact_cents // 100:,}/month\n"
            f"   Reply: APPROVE {r.id} or REJECT {r.id}"
        )
    return "\n".join(lines)


def _cmd_tonight(db: Session, restaurant_id: int) -> str:
    tonight = db.query(models.Reservation).filter(
        models.Reservation.restaurant_id == restaurant_id,
        models.Reservation.reservation_date == utcnow().date(),
        models.Reservation.status == models.ReservationStatus.CONFIRMED,
    ).order_by(models.Reservation.reservation_time).all()
    if not tonight:
        return "📅 No reservations for tonight."
    lines = [f"📅 *Tonight's Reservations ({len(tonight)} bookings)*\n"]
    for r in tonight[:10]:
        t = r.reservation_time.strftime("%H:%M") if r.reservation_time else "TBD"
        lines.append(f"• {t} — {r.customer_name}, party of {r.party_size}")
    lines.append(f"\n_Total covers: {sum(r.party_size for r in tonight)}_")
    return "\n".join(lines)


def _cmd_winback_summary(db: Session, restaurant_id: int) -> str:
    candidates = get_winback_candidates(db, restaurant_id)
    if not candidates:
        return f"✅ All regulars visited within {WINBACK_DAYS} days. No winback needed."
    total_spend = sum(c["total_spend"] for c in candidates[:10])
    lines = [
        f"🎯 *Winback Candidates*\n",
        f"{len(candidates)} customers haven't returned in {WINBACK_DAYS}+ days",
        f"Combined past spend: KES {total_spend // 100:,}\n",
    ]
    for c in candidates[:5]:
        fav = f" — loves {c['fav_item']}" if c["fav_item"] else ""
        lines.append(f"• {c['name'] or c['phone']}: {c['days_away']} days away{fav}")
    return "\n".join(lines)


def _cmd_cost_quality(db: Session, restaurant_id: int) -> str:
    from ai.data_quality import get_cost_price_quality
    data = get_cost_price_quality(db, restaurant_id)
    s = data["summary"]
    if not data["issues"]:
        return (f"✅ *Cost prices look healthy.*\n{s['coverage_pct']}% of your "
                f"{s['total_items']} dishes have a cost price set.")
    labels = {
        "MISSING_COST": "no cost price set", "MISSING_PRICE": "no price set",
        "SELLING_AT_LOSS": "sold at a loss", "SUSPICIOUSLY_LOW_COST": "cost looks like a typo",
        "THIN_MARGIN": "very thin margin",
    }
    lines = [
        "🧮 *Cost-price check*\n",
        f"{s['items_with_issues']} of {s['total_items']} dishes need attention "
        f"({s['coverage_pct']}% have a cost price).",
        "_These drive your profit & pricing numbers — fixing them makes those accurate._\n",
    ]
    for i in data["issues"][:6]:
        sold = f" ({i['qty_30d']} sold in 30d)" if i["qty_30d"] else ""
        lines.append(f"• *{i['item_name']}* — {labels.get(i['issue'], i['issue'])}{sold}")
    return "\n".join(lines)


def _cmd_promo(db: Session, restaurant_id: int, offer: str) -> str:
    """
    Kick off a promo blast in the background and reply to the owner immediately.
    The send loop is far too slow to run inside the inbound webhook (it would hit
    the provider one customer at a time and blow the webhook timeout), so it runs
    on its own thread with its own DB session.
    """
    audience = promo_audience_count(db, restaurant_id)
    if audience == 0:
        return ("No customers to send to yet — a promo only goes to diners who "
                "gave consent at checkout and haven't opted out.")

    def _run():
        from database import SessionLocal
        bg = SessionLocal()
        try:
            broadcast_promo(bg, restaurant_id, offer)
        except Exception as exc:   # background thread — never surfaces to a caller
            logger.warning(f"[WhatsApp Brain] Promo broadcast failed: {exc}")
        finally:
            bg.close()

    threading.Thread(target=_run, daemon=True).start()
    capped = min(audience, PROMO_MAX_RECIPIENTS)
    extra = "" if audience <= PROMO_MAX_RECIPIENTS else f" (capped from {audience})"
    return (f"📣 Sending your promo to {capped} customer{'s' if capped != 1 else ''}{extra} now. "
            f"Opted-out customers are skipped automatically.")


def _cmd_help(db: Session, restaurant_id: int) -> str:
    return (
        "🤖 *AI Commands*\n\n"
        "• SALES — today's revenue\n• STOCK — critical inventory\n"
        "• PENDING — pricing approvals\n• TONIGHT — tonight's bookings\n"
        "• WINBACK — lapsed customers\n• COSTS — cost-price data check\n"
        "• PROMO [offer] — text a special to your regulars\n"
        "• APPROVE [n] — approve rec\n• REJECT [n] — reject rec"
    )


def _cmd_approve(db: Session, restaurant_id: int, rec_id: int) -> str:
    from ai.pricing import approve_recommendation
    result = approve_recommendation(db, rec_id, restaurant_id, approved_by="whatsapp_owner")
    if result.get("error"):
        return f"❌ {result['error']}"
    return compose_pricing_approved_message(result["item_name"], result["old_price"], result["new_price"])


def _cmd_reject(db: Session, restaurant_id: int, rec_id: int) -> str:
    from ai.pricing import reject_recommendation
    result = reject_recommendation(db, rec_id, restaurant_id)
    if result.get("error"):
        return f"❌ {result['error']}"
    return "✅ Recommendation rejected. Won't be suggested again for 7 days."


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER ENTRY POINTS
# BUG-02 FIX: removed dead `from database import SessionLocal as _SL` import.
# Caller passes SessionLocal. Each function creates and closes its own session.
# ─────────────────────────────────────────────────────────────────────────────

def run_morning_briefing(SessionLocal) -> None:
    """
    Called by APScheduler at 08:00 EAT (05:00 UTC) daily.
    Pass your SessionLocal: scheduler.add_job(run_morning_briefing, args=[SessionLocal])
    """
    db = SessionLocal()
    try:
        for restaurant in db.query(models.Restaurant).all():
            message = compose_morning_briefing(db, restaurant.id)
            notifications.deliver(
                db, restaurant,
                title="Morning briefing",
                body=message,
                category="morning_briefing", severity=notifications.SEVERITY_INFO,
                audience=notifications.AUDIENCE_ADMIN,
                link="/dashboard", whatsapp_body=message,
            )
            logger.info(f"[WhatsApp Brain] Morning briefing sent: {restaurant.name}")
    finally:
        db.close()


def run_morning_briefing_voice(SessionLocal, tts_render=None) -> None:
    """
    Voice-note variant of the 8am briefing, for owners who'd rather listen than
    read. Requires a `tts_render(text) -> public_audio_url` callable (a TTS
    provider plus a publicly reachable hosted file) because Twilio attaches media
    by URL. Without one this no-ops and the text briefing stays the default. The
    transport already carries media (twilio_client.send(media_url=...)); plugging
    in a TTS provider is the only remaining piece.
    """
    if tts_render is None:
        logger.info("[WhatsApp Brain] Voice briefing skipped — no TTS/audio-URL provider configured")
        return
    db = SessionLocal()
    try:
        for restaurant in db.query(models.Restaurant).all():
            phone = owner_phone_for(restaurant)
            if not phone:
                continue
            text = compose_morning_briefing(db, restaurant.id)
            try:
                audio_url = tts_render(text)
            except Exception as exc:
                logger.warning(f"[WhatsApp Brain] TTS render failed for {restaurant.name}: {exc}")
                continue
            send_whatsapp_message(
                phone, "🌅 Your morning briefing (voice note)", db=db,
                restaurant_id=restaurant.id, message_type="morning_briefing_voice",
                media_url=audio_url,
            )
    finally:
        db.close()


def run_slow_day_check(SessionLocal) -> None:
    """Called by APScheduler at 14:00 EAT (11:00 UTC) daily."""
    db = SessionLocal()
    try:
        for restaurant in db.query(models.Restaurant).all():
            alert = compose_slow_day_alert(db, restaurant.id)
            if alert:
                notifications.deliver(
                    db, restaurant,
                    title="Slow day — revenue below average",
                    body=alert,
                    category="slow_day_alert", severity=notifications.SEVERITY_WARNING,
                    audience=notifications.AUDIENCE_ADMIN,
                    link="/dashboard/sales", whatsapp_body=alert,
                )
    finally:
        db.close()


def run_stock_check(SessionLocal) -> None:
    """
    Called by APScheduler every 2 hours during service (08:00-22:00 EAT).

    Emits STOCK_CRITICAL / STOCK_DEPLETED — found 2026-07-07 auditing the
    event orchestration end to end: ai/orchestrator/executive.py has
    subscribed handlers for both (which record into ai/memory/store.py) but
    this was the only place that could plausibly emit them, and it never did
    — this scheduled job itself was also never registered until the same
    audit. Both gaps had to be fixed together for either to matter.

    Two more defects fixed 2026-07-08:

      • DOUBLE SEND. This emitted STOCK_CRITICAL (whose handler,
        executive.on_stock_critical, WhatsApps the owner) and then *also* sent
        `compose_stock_alert(urgent[0])` directly — so the first urgent item
        generated two messages describing the same shortage. Notification is
        now the event handlers' job alone; this function only decides what is
        worth an event. (`on_stock_depleted` grew a send of its own: a fully
        out-of-stock item with no recent usage scores WARNING, never entered
        `urgent`, and so was silently never reported at all.)

      • NO COOLDOWN. Every item that qualified re-alerted on every 2-hourly
        cycle. `last_alerted_at` is stamped on each item we raise an event for
        and re-checked here, so a persistently low item nudges the owner at most
        once per STOCK_ALERT_COOLDOWN_HOURS.
    """
    from events.bus import emit_async, EventType

    # Quiet hours: outside service hours only fully-depleted items are worth a
    # ping; a merely-low item can wait until the restaurant reopens.
    in_hours = within_service_hours()

    db = SessionLocal()
    try:
        cooldown_cutoff = utcnow() - timedelta(hours=STOCK_ALERT_COOLDOWN_HOURS)

        for restaurant in db.query(models.Restaurant).all():
            alerts = get_critical_stock_alerts(db, restaurant.id)
            if not alerts:
                continue

            alert_ids = [a["inventory_item_id"] for a in alerts]
            recently_alerted = {
                row.id for row in db.query(models.InventoryItem.id).filter(
                    models.InventoryItem.id.in_(alert_ids),
                    models.InventoryItem.last_alerted_at.isnot(None),
                    models.InventoryItem.last_alerted_at >= cooldown_cutoff,
                ).all()
            }

            actionable = [a for a in alerts if a["inventory_item_id"] not in recently_alerted]
            depleted = [a for a in actionable if a["current_qty"] <= 0]
            # `> 0` keeps a depleted item from being reported twice, once under
            # each event — it is depleted, not merely critical. Outside service
            # hours we hold back merely-urgent (still-in-stock) items; a full
            # stock-out still fires because it blocks service the moment they open.
            urgent = [a for a in actionable
                      if a["severity"] == "URGENT" and a["current_qty"] > 0] if in_hours else []

            for item in depleted:
                emit_async(EventType.STOCK_DEPLETED, {
                    "restaurant_id": restaurant.id,
                    "item_name": item["item_name"],
                    "inventory_item_id": item["inventory_item_id"],
                })
            for item in urgent:
                emit_async(EventType.STOCK_CRITICAL, {
                    "restaurant_id": restaurant.id,
                    "item_name": item["item_name"],
                    "hours_remaining": item["hours_remaining"],
                    "inventory_item_id": item["inventory_item_id"],
                })

            notified_ids = [a["inventory_item_id"] for a in depleted + urgent]
            if notified_ids:
                db.query(models.InventoryItem).filter(
                    models.InventoryItem.id.in_(notified_ids)
                ).update({models.InventoryItem.last_alerted_at: utcnow()},
                         synchronize_session=False)
                db.commit()
    finally:
        db.close()
