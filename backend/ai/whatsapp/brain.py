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
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
import models
from . import twilio_client

# ── Config ────────────────────────────────────────────────────────────────────
WINBACK_DAYS         = 21
SLOW_DAY_THRESHOLD   = 20    # % below average to trigger alert
STOCK_CRITICAL_HOURS = 6


# ─────────────────────────────────────────────────────────────────────────────
# MORNING BRIEFING
# ─────────────────────────────────────────────────────────────────────────────

def compose_morning_briefing(db: Session, restaurant_id: int) -> str:
    now_utc   = datetime.utcnow()
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
        models.PricingRecommendation.created_at >= datetime.utcnow() - timedelta(hours=48),
    ).count()
    pricing_str = f"\n\n💡 *{pending_count} pricing recommendation(s) awaiting your approval.* Reply PENDING to review." if pending_count > 0 else ""

    today_res = db.query(models.Reservation).filter(
        models.Reservation.restaurant_id == restaurant_id,
        models.Reservation.reservation_date == now_utc.date(),
        models.Reservation.status == models.ReservationStatus.CONFIRMED,
    ).count()
    res_str = f"\n\n📅 *Today:* {today_res} reservation(s) booked." if today_res > 0 else ""

    focus = _daily_focus(db, restaurant_id, now_utc)

    return (
        f"🌅 *Good morning! Here's {restaurant_name}*\n\n"
        f"📊 *Yesterday's Performance*\n"
        f"Revenue: KES {yesterday_revenue // 100:,} {wow_emoji} ({wow_str} vs last week)\n"
        f"Orders: {yesterday_count}\n\n"
        f"🏆 *Top Sellers*\n{top_str}\n\n"
        f"💳 *Payments*\n{pay_str}"
        f"{stock_str}{pricing_str}{res_str}\n\n"
        f"🎯 *Today's Focus*\n{focus}\n\n"
        f"_Powered by {restaurant_name} AI_ 🤖\n"
        f"_Reply SALES, STOCK, PENDING, or TONIGHT for live data_"
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
    three_days_ago = datetime.utcnow() - timedelta(days=3)

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
    now_utc      = datetime.utcnow()
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
        f"*Suggestion:* Consider a quick special or push high-margin items on social media now."
    )


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
    cutoff = datetime.utcnow() - timedelta(days=WINBACK_DAYS)

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

    now_utc    = datetime.utcnow()
    candidates = []
    for row in customer_rows:
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


def compose_winback_message(restaurant_name: str, name: str, fav_item: str | None, days_away: int) -> str:
    fav_str = f"Your favourite *{fav_item}* is waiting for you." if fav_item else "We have something special waiting."
    return (
        f"👋 Hi {name}!\n\n"
        f"We miss you at {restaurant_name}! {fav_str}\n\n"
        f"It's been {days_away} days — come back and enjoy *10% off* your next visit.\n"
        f"Just show this message when you arrive.\n\n"
        f"See you soon! 🍽️"
    )


# ─────────────────────────────────────────────────────────────────────────────
# SEND ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def send_whatsapp_message(
    to_number: str,
    message: str,
    db: Session | None = None,
    restaurant_id: int | None = None,
    message_type: str = "general",
) -> dict:
    result = twilio_client.send(to_number, message)
    if db and restaurant_id:
        _log_message(db, restaurant_id, to_number, message, message_type, result["status"], result.get("sid"))
    return result


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
        print(f"[WhatsApp Brain] Failed to log message: {exc}")


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

    return "I didn't understand that. Reply HELP to see all commands."


def _cmd_sales_today(db: Session, restaurant_id: int) -> str:
    now_utc = datetime.utcnow()
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
            models.PricingRecommendation.created_at >= datetime.utcnow() - timedelta(hours=48),
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
        models.Reservation.reservation_date == datetime.utcnow().date(),
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


def _cmd_help(db: Session, restaurant_id: int) -> str:
    return (
        "🤖 *AI Commands*\n\n"
        "• SALES — today's revenue\n• STOCK — critical inventory\n"
        "• PENDING — pricing approvals\n• TONIGHT — tonight's bookings\n"
        "• WINBACK — lapsed customers\n• APPROVE [n] — approve rec\n• REJECT [n] — reject rec"
    )


def _cmd_approve(db: Session, restaurant_id: int, rec_id: int) -> str:
    from ai.pricing import approve_recommendation
    result = approve_recommendation(db, rec_id, restaurant_id)
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
            owner_phone = os.getenv(f"OWNER_PHONE_{restaurant.id}", os.getenv("OWNER_PHONE", ""))
            if not owner_phone:
                print(f"[WhatsApp Brain] No owner phone for restaurant {restaurant.id}")
                continue
            message = compose_morning_briefing(db, restaurant.id)
            send_whatsapp_message(owner_phone, message, db=db, restaurant_id=restaurant.id, message_type="morning_briefing")
            print(f"[WhatsApp Brain] Morning briefing sent: {restaurant.name}")
    finally:
        db.close()


def run_slow_day_check(SessionLocal) -> None:
    """Called by APScheduler at 14:00 EAT (11:00 UTC) daily."""
    db = SessionLocal()
    try:
        for restaurant in db.query(models.Restaurant).all():
            alert = compose_slow_day_alert(db, restaurant.id)
            if alert:
                owner_phone = os.getenv(f"OWNER_PHONE_{restaurant.id}", os.getenv("OWNER_PHONE", ""))
                if owner_phone:
                    send_whatsapp_message(owner_phone, alert, db=db, restaurant_id=restaurant.id, message_type="slow_day_alert")
    finally:
        db.close()


def run_stock_check(SessionLocal) -> None:
    """Called by APScheduler every 2 hours during service (08:00–22:00 EAT)."""
    db = SessionLocal()
    try:
        for restaurant in db.query(models.Restaurant).all():
            urgent = [a for a in get_critical_stock_alerts(db, restaurant.id) if a["severity"] == "URGENT"]
            if urgent:
                owner_phone = os.getenv(f"OWNER_PHONE_{restaurant.id}", os.getenv("OWNER_PHONE", ""))
                if owner_phone:
                    send_whatsapp_message(owner_phone, compose_stock_alert(urgent[0]), db=db, restaurant_id=restaurant.id, message_type="stock_alert")
    finally:
        db.close()
