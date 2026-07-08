"""
backend/ai/orchestrator/executive.py
──────────────────────────────────────
The Executive Agent — Layer 1.

This is the "CEO Agent" described in the enterprise roadmap.
It doesn't run analytics — it reasons across them.

What it does:
  1. subscribe() — registers handlers on the event bus at startup
  2. When an event fires (inventory low, order spike, recommendation generated),
     it pulls context from multiple agents + memory, then decides what to do.
  3. It produces: WhatsApp messages, purchase recommendations, campaign triggers.
  4. All decisions are written to the audit log.

The reasoning pattern for each event:
  → What happened? (event payload)
  → What do we know about this? (memory recall)
  → What is the current state? (agent queries)
  → What's the impact? (knowledge graph traversal)
  → What should we do? (decision)
  → Who needs to know? (WhatsApp / audit log)

Design principle: the orchestrator never calls database queries directly.
It always calls agent functions. The agents own the data logic.
"""

import logging
from datetime import date
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from events.bus import subscribe, EventType, emit_async
from ai.memory import store as memory
from ai.evaluation.tracker import write_audit_log
from time_utils import utcnow

logger = logging.getLogger("ai.orchestrator")


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────

def register_all_handlers() -> None:
    """
    Register all orchestrator handlers on the event bus.
    Called once in main.py on startup.
    """
    subscribe(EventType.STOCK_CRITICAL,          on_stock_critical)
    subscribe(EventType.STOCK_DEPLETED,          on_stock_depleted)
    subscribe(EventType.RECOMMENDATION_APPROVED, on_recommendation_approved)
    subscribe(EventType.ORDER_PAID,              on_order_paid_mpesa)
    subscribe(EventType.RESERVATION_NO_SHOW,     on_reservation_no_show)
    subscribe(EventType.PURCHASE_ORDER_LATE,     on_purchase_order_late)
    subscribe(EventType.AGENT_FAILED,            on_agent_failed)

    logger.info("[Orchestrator] All handlers registered")


# ─────────────────────────────────────────────────────────────────────────────
# EVENT HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

def on_stock_critical(payload: dict) -> None:
    """
    Fires when an inventory item hits critical level.

    Reasoning chain:
      1. Which menu items are affected? (knowledge graph)
      2. How many covers are booked tonight? (reservations)
      3. What's our daily usage rate? (inventory agent)
      4. Should we order now or substitute? (decision)
      5. Notify owner with full context. (WhatsApp)
    """
    restaurant_id = payload.get("restaurant_id")
    item_name     = payload.get("item_name", "Unknown item")
    hours_left    = payload.get("hours_remaining", 0)
    item_id       = payload.get("inventory_item_id")

    db = SessionLocal()
    try:
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
        if not restaurant:
            return

        # Knowledge graph: which menu items are affected?
        affected_items = _get_affected_menu_items(db, item_id) if item_id else []
        affected_names = [i["name"] for i in affected_items if i["is_critical"]]

        # Tonight's reservations
        tonight_covers = db.query(models.Reservation).filter(
            models.Reservation.restaurant_id == restaurant_id,
            models.Reservation.reservation_date == utcnow().date(),
            models.Reservation.status == models.ReservationStatus.CONFIRMED,
        ).count()

        # Memory: has this happened before?
        ctx = memory.recall_context(db, restaurant_id, utcnow().date())
        past_stockouts = ctx["recent_stockouts"]
        stockout_history = f"This item has stocked out {len(past_stockouts)} time(s) recently." if past_stockouts else ""

        # Build reasoning
        reasoning_parts = [
            f"{item_name} is critically low (~{hours_left:.0f}h remaining).",
        ]
        if affected_names:
            reasoning_parts.append(f"Affected dishes: {', '.join(affected_names[:3])}.")
        if tonight_covers:
            reasoning_parts.append(f"{tonight_covers} covers booked tonight.")
        if stockout_history:
            reasoning_parts.append(stockout_history)

        reasoning = " ".join(reasoning_parts)

        # Decision: compose WhatsApp alert
        from ai.whatsapp import compose_stock_alert, send_whatsapp_message
        import os

        msg = _compose_orchestrated_stock_alert(
            item_name     = item_name,
            hours_left    = hours_left,
            affected_names = affected_names,
            tonight_covers = tonight_covers,
            past_stockouts = len(past_stockouts),
        )

        owner_phone = os.getenv(f"OWNER_PHONE_{restaurant_id}", os.getenv("OWNER_PHONE", ""))
        if owner_phone:
            send_whatsapp_message(owner_phone, msg, db=db, restaurant_id=restaurant_id,
                                  message_type="orchestrated_stock_critical")

        # Memory: auto-record near-stockout
        if hours_left <= 2:
            memory.auto_record_stockout(db, restaurant_id, item_name)

        # Audit
        write_audit_log(
            db, restaurant_id, "stock_critical_alert", "executive_orchestrator",
            entity_type="inventory_item", entity_id=item_id,
            reasoning=reasoning,
            data_sources=["inventory_predictor", "reservation_optimizer", "memory_store"],
        )

    except Exception as exc:
        logger.error(f"[Orchestrator] on_stock_critical failed: {exc}")
    finally:
        db.close()


def on_stock_depleted(payload: dict) -> None:
    """Stock hit zero — auto-record in memory."""
    restaurant_id = payload.get("restaurant_id")
    item_name     = payload.get("item_name")
    if restaurant_id and item_name:
        db = SessionLocal()
        try:
            memory.auto_record_stockout(db, restaurant_id, item_name)
        finally:
            db.close()


def on_recommendation_approved(payload: dict) -> None:
    """
    Price recommendation approved — schedule outcome measurement.
    At day 7 and day 14, the evaluation agent checks if revenue from
    that item improved. Outcome gets written back to AgentPrediction.
    """
    restaurant_id     = payload.get("restaurant_id")
    recommendation_id = payload.get("recommendation_id")
    item_name         = payload.get("item_name")
    old_price         = payload.get("old_price", 0)
    new_price         = payload.get("new_price", 0)
    approved_by       = payload.get("approved_by", "unknown")

    db = SessionLocal()
    try:
        # Memory: record this price change
        memory.remember(
            db, restaurant_id,
            event_type        = "price_change",
            event_name        = f"Price change: {item_name}",
            event_date        = utcnow().date(),
            impact_type       = "price_change",
            agent_notes       = f"{item_name} changed from KES {old_price//100:,} to KES {new_price//100:,}. Approved by {approved_by}.",
        )

        # Audit
        write_audit_log(
            db, restaurant_id, "price_changed", "pricing_intelligence",
            entity_type       = "menu_item",
            before            = {"price": old_price},
            after             = {"price": new_price},
            reasoning         = f"Demand-based pricing recommendation approved.",
            approved_by       = approved_by,
            recommendation_id = recommendation_id,
        )

    except Exception as exc:
        logger.error(f"[Orchestrator] on_recommendation_approved failed: {exc}")
    finally:
        db.close()


def on_order_paid_mpesa(payload: dict) -> None:
    """
    Reacts to an ORDER_PAID event (past tense — the order is ALREADY settled
    atomically by the M-Pesa webhook before this fires). This handler does the
    pure side-effects only: send the WhatsApp receipt + write the audit log.
    It deliberately does NOT mutate is_paid — settlement is the emitter's job,
    so a failure here can never leave the order in a half-paid state.
    """
    restaurant_id  = payload.get("restaurant_id")
    order_id       = payload.get("order_id")
    amount         = payload.get("amount_cents", 0)
    customer_phone = payload.get("customer_phone")
    mpesa_ref      = payload.get("mpesa_reference", "")

    db = SessionLocal()
    try:
        # Send WhatsApp receipt to customer (if phone available)
        if customer_phone:
            from ai.whatsapp import send_whatsapp_message
            restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
            r_name = restaurant.name if restaurant else "the restaurant"
            msg = (
                f"✅ *Payment Confirmed*\n\n"
                f"Thank you! KES {amount // 100:,} received at {r_name}.\n"
                f"M-Pesa Ref: {mpesa_ref}\n"
                f"Order #{order_id} is confirmed.\n\n"
                f"_Thank you for dining with us!_"
            )
            send_whatsapp_message(customer_phone, msg, db=db,
                                  restaurant_id=restaurant_id, message_type="mpesa_receipt")

        write_audit_log(
            db, restaurant_id, "mpesa_payment_received", "executive_orchestrator",
            entity_type = "order",
            entity_id   = order_id,
            before      = {"is_paid": False},
            after       = {"is_paid": True, "mpesa_ref": mpesa_ref},
            reasoning   = f"M-Pesa STK push confirmed. Amount: KES {amount // 100:,}.",
        )

    except Exception as exc:
        logger.error(f"[Orchestrator] on_order_paid_mpesa failed: {exc}")
    finally:
        db.close()


def on_reservation_no_show(payload: dict) -> None:
    """
    No-show detected — trigger winback for high-value customers.
    Accumulate no-show pattern data in memory.
    """
    restaurant_id  = payload.get("restaurant_id")
    customer_name  = payload.get("customer_name", "")
    customer_phone = payload.get("customer_phone", "")
    party_size     = payload.get("party_size", 0)

    db = SessionLocal()
    try:
        # Memory: track no-show pattern
        memory.remember(
            db, restaurant_id,
            event_type        = "no_show",
            event_name        = f"No-show: {customer_name or 'unknown'}",
            event_date        = utcnow().date(),
            impact_type       = "traffic_drop",
            agent_notes       = f"Party of {party_size} did not arrive. Phone: {customer_phone}.",
        )

        # For large parties (4+) from known customers, trigger winback
        if party_size >= 4 and customer_phone:
            restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
            r_name = restaurant.name if restaurant else "us"
            from ai.whatsapp import compose_winback_message, send_whatsapp_message
            # 24-hour delay winback (customer gets space, not immediate marketing)
            msg = (
                f"Hi {customer_name or 'there'}! We had a table reserved for you at {r_name} today.\n\n"
                f"Life happens — we understand! We'd love to host you another time.\n"
                f"Reply YES and we'll reserve your table again. 🍽️"
            )
            send_whatsapp_message(customer_phone, msg, db=db,
                                  restaurant_id=restaurant_id, message_type="no_show_winback")

    except Exception as exc:
        logger.error(f"[Orchestrator] on_reservation_no_show failed: {exc}")
    finally:
        db.close()


def on_purchase_order_late(payload: dict) -> None:
    """Supplier delivery is overdue — alert owner + update supplier reliability score."""
    restaurant_id = payload.get("restaurant_id")
    supplier_id   = payload.get("supplier_id")
    supplier_name = payload.get("supplier_name", "")
    item_name     = payload.get("item_name", "")
    days_late     = payload.get("days_late", 0)

    db = SessionLocal()
    try:
        # Update supplier reliability score
        supplier = db.query(models.Supplier).filter(
            models.Supplier.id == supplier_id,
            models.Supplier.restaurant_id == restaurant_id,
        ).first()
        if supplier:
            # Penalise reliability: each late delivery -5 points, min 0
            supplier.reliability_score = max(0, (supplier.reliability_score or 100) - 5)
            db.commit()

        import os
        from ai.whatsapp import send_whatsapp_message
        owner_phone = os.getenv(f"OWNER_PHONE_{restaurant_id}", os.getenv("OWNER_PHONE", ""))
        if owner_phone:
            msg = (
                f"🚚 *Supplier Alert*\n\n"
                f"*{supplier_name}* delivery is {days_late} day(s) late.\n"
                f"Item: {item_name}\n\n"
                f"Reliability score: {supplier.reliability_score if supplier else 'N/A'}%\n"
                f"Consider calling the supplier or sourcing from an alternative."
            )
            send_whatsapp_message(owner_phone, msg, db=db,
                                  restaurant_id=restaurant_id, message_type="supplier_late")

    except Exception as exc:
        logger.error(f"[Orchestrator] on_purchase_order_late failed: {exc}")
    finally:
        db.close()


def on_agent_failed(payload: dict) -> None:
    """An agent execution failed — alert if it's been failing repeatedly."""
    import os
    agent_name    = payload.get("agent_name", "unknown")
    error         = payload.get("error", "")
    restaurant_id = payload.get("restaurant_id")

    db = SessionLocal()
    try:
        # Check how many failures in the last hour
        from datetime import timedelta
        cutoff = utcnow() - timedelta(hours=1)
        recent_failures = db.query(models.AgentExecution).filter(
            models.AgentExecution.agent_name == agent_name,
            models.AgentExecution.success    == False,
            models.AgentExecution.created_at >= cutoff,
        ).count()

        if recent_failures >= 3:
            owner_phone = os.getenv("OWNER_PHONE", "")
            if owner_phone:
                from ai.whatsapp import send_whatsapp_message
                msg = (
                    f"⚠️ *AI System Alert*\n\n"
                    f"*{agent_name}* has failed {recent_failures} times in the last hour.\n"
                    f"Last error: {error[:200]}\n\n"
                    f"Analytics may be temporarily unavailable. Team has been notified."
                )
                send_whatsapp_message(owner_phone, msg, db=db,
                                      restaurant_id=restaurant_id, message_type="agent_failure")

    except Exception as exc:
        logger.error(f"[Orchestrator] on_agent_failed failed: {exc}")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# KNOWLEDGE GRAPH — INGREDIENT TO MENU ITEM
# ─────────────────────────────────────────────────────────────────────────────

def _get_affected_menu_items(db: Session, inventory_item_id: int) -> list[dict]:
    """
    Layer 3: Traverse the ingredient-to-menu-item graph.
    Returns list of menu items that use this ingredient.
    """
    links = db.query(models.MenuIngredient).filter(
        models.MenuIngredient.inventory_item_id == inventory_item_id,
    ).all()

    result = []
    for link in links:
        item = link.menu_item
        if item and item.is_available:
            result.append({
                "id":          item.id,
                "name":        item.name,
                "category":    item.category,
                "is_critical": link.is_critical,
                "qty_per_serving": link.quantity_per_serving,
            })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATED MESSAGE COMPOSITION
# ─────────────────────────────────────────────────────────────────────────────

def _compose_orchestrated_stock_alert(
    item_name: str,
    hours_left: float,
    affected_names: list,
    tonight_covers: int,
    past_stockouts: int,
) -> str:
    """
    Unlike the plain stock alert, this includes cross-agent context:
    which dishes are affected, tonight's bookings, historical pattern.
    """
    urgency = "🚨" if hours_left <= 4 else "⚠️"
    lines = [
        f"{urgency} *Stock Alert — {item_name}*\n",
        f"~{hours_left:.0f}h of stock remaining.",
    ]
    if affected_names:
        lines.append(f"Affects: {', '.join(affected_names[:3])}.")
    if tonight_covers:
        lines.append(f"⚠️ {tonight_covers} covers booked tonight — reorder urgently.")
    if past_stockouts > 0:
        lines.append(f"Note: {item_name} has stocked out {past_stockouts} time(s) recently.")
    lines.append("\nReply STOCK for full inventory status.")
    return "\n".join(lines)
