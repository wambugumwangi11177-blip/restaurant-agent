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
from sqlalchemy.orm import Session, joinedload
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
    subscribe(EventType.ORDER_PAID,              on_order_paid)
    subscribe(EventType.MPESA_PAYMENT_FAILED,    on_mpesa_payment_failed)
    subscribe(EventType.RESERVATION_NO_SHOW,     on_reservation_no_show)
    subscribe(EventType.PURCHASE_ORDER_LATE,     on_purchase_order_late)
    subscribe(EventType.PURCHASE_ORDER_CREATED,  on_purchase_order_created)
    subscribe(EventType.PURCHASE_ORDER_DELIVERED, on_purchase_order_delivered)
    subscribe(EventType.AGENT_FAILED,            on_agent_failed)
    subscribe(EventType.STOCK_TRANSFER_DISCREPANCY, on_stock_transfer_discrepancy)
    subscribe(EventType.STOCK_VARIANCE_FLAGGED,      on_stock_variance_flagged)
    subscribe(EventType.STOCK_COUNT_DISCREPANCY,     on_stock_count_discrepancy)

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
        from ai.whatsapp import send_whatsapp_message

        msg = _compose_orchestrated_stock_alert(
            item_name     = item_name,
            hours_left    = hours_left,
            affected_names = affected_names,
            tonight_covers = tonight_covers,
            past_stockouts = len(past_stockouts),
        )

        # Was env-var only, so a restaurant onboarded via the owner_phone column
        # (migration 006) got no critical-stock alerts at all.
        owner_phone = _owner_phone(restaurant)
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
    """
    Stock hit zero — auto-record in memory and tell the owner.

    The WhatsApp send was added 2026-07-08 alongside removing brain.run_stock_check's
    duplicate direct send. A depleted item whose recent usage is zero scores
    WARNING (hours_remaining defaults to 999), so it never entered the `urgent`
    list and never emitted STOCK_CRITICAL — the only handler that notified. Such
    an item could sit at zero indefinitely and the owner would never be told.
    Being out of stock is strictly more urgent than being nearly out.
    """
    restaurant_id = payload.get("restaurant_id")
    item_name     = payload.get("item_name")
    if not (restaurant_id and item_name):
        return

    db = SessionLocal()
    try:
        memory.auto_record_stockout(db, restaurant_id, item_name)

        restaurant = db.query(models.Restaurant).filter(
            models.Restaurant.id == restaurant_id
        ).first()
        owner_phone = _owner_phone(restaurant)
        if owner_phone:
            from ai.whatsapp import send_whatsapp_message
            msg = (
                f"🚨 *Out of Stock*\n\n"
                f"{item_name} has hit zero.\n"
                f"Dishes using it cannot be served until it's restocked."
            )
            send_whatsapp_message(owner_phone, msg, db=db, restaurant_id=restaurant_id,
                                  message_type="stock_depleted")
    except Exception as exc:
        logger.error(f"[Orchestrator] on_stock_depleted failed: {exc}")
    finally:
        db.close()


def on_stock_transfer_discrepancy(payload: dict) -> None:
    """
    A store->kitchen StockTransfer was confirmed with a quantity that
    doesn't match what the sender declared (directive 016). Fires once per
    confirm action — inherently non-repeating, so unlike the 2-hourly stock
    check this needs no cooldown column to avoid re-alerting.
    """
    restaurant_id       = payload.get("restaurant_id")
    transfer_id         = payload.get("transfer_id")
    item_name           = payload.get("item_name", "Unknown item")
    declared_quantity   = payload.get("declared_quantity", 0)
    confirmed_quantity  = payload.get("confirmed_quantity", 0)
    unit                = payload.get("unit", "")

    db = SessionLocal()
    try:
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
        if not restaurant:
            return

        owner_phone = _owner_phone(restaurant)
        if owner_phone:
            direction = "less" if confirmed_quantity < declared_quantity else "more"
            gap = abs(confirmed_quantity - declared_quantity)
            from ai.whatsapp import send_whatsapp_message
            msg = (
                f"⚠️ *Stock Transfer Mismatch*\n\n"
                f"Transfer #{transfer_id} of {item_name}: sender declared "
                f"{declared_quantity}{unit}, receiver confirmed {confirmed_quantity}{unit} "
                f"({gap}{unit} {direction} than declared).\n"
                f"Flagged for review — not auto-corrected."
            )
            send_whatsapp_message(owner_phone, msg, db=db, restaurant_id=restaurant_id,
                                  message_type="stock_transfer_discrepancy")

        write_audit_log(
            db, restaurant_id, "stock_transfer_discrepancy_alerted", "executive_orchestrator",
            entity_type="stock_transfer", entity_id=transfer_id,
            reasoning=f"{item_name}: declared {declared_quantity}{unit} vs confirmed {confirmed_quantity}{unit}.",
            data_sources=["stock_custody_router"],
        )
    except Exception as exc:
        logger.error(f"[Orchestrator] on_stock_transfer_discrepancy failed: {exc}")
    finally:
        db.close()


def on_stock_variance_flagged(payload: dict) -> None:
    """
    Daily variance job (main.py: run_variance_check) found at least one item
    whose theoretical-vs-actual usage gap exceeds the threshold (directive
    016). One summary message per restaurant per day — matches the "alert on
    the report, not on every movement" philosophy from the
    stock-loss-prevention skill, and avoids needing a per-item cooldown.
    """
    restaurant_id = payload.get("restaurant_id")
    items         = payload.get("items", [])   # [{item_name, variance_pct, theoretical, actual}, ...]
    if not items:
        return

    db = SessionLocal()
    try:
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
        if not restaurant:
            return

        owner_phone = _owner_phone(restaurant)
        if owner_phone:
            from ai.stock_custody import VARIANCE_THRESHOLD
            lines = [
                f"• {i['item_name']}: {i['variance_pct']*100:.1f}% variance "
                f"(expected ~{i['theoretical']:.1f}, actual {i['actual']:.1f})"
                for i in items[:5]
            ]
            more = f"\n…and {len(items) - 5} more" if len(items) > 5 else ""
            from ai.whatsapp import send_whatsapp_message
            msg = (
                f"📊 *Stock Variance Report*\n\n"
                f"{len(items)} item(s) over the {VARIANCE_THRESHOLD*100:.0f}% variance threshold "
                f"in the last 24h:\n\n" + "\n".join(lines) + more +
                f"\n\nWorth a physical count if this keeps recurring on the same item."
            )
            send_whatsapp_message(owner_phone, msg, db=db, restaurant_id=restaurant_id,
                                  message_type="stock_variance_flagged")

        write_audit_log(
            db, restaurant_id, "stock_variance_alerted", "executive_orchestrator",
            entity_type="inventory_variance_report", entity_id=None,
            reasoning=f"{len(items)} item(s) flagged over variance threshold.",
            data_sources=["ai.stock_custody"],
        )
    except Exception as exc:
        logger.error(f"[Orchestrator] on_stock_variance_flagged failed: {exc}")
    finally:
        db.close()


def on_stock_count_discrepancy(payload: dict) -> None:
    """
    A physical count (directive 017) found a real gap against what the
    system expected. This is the independent check — the one number that
    isn't derived from the recipe math auto-deduction relies on — so a
    mismatch here is the closest thing this system has to catching real
    shrinkage rather than a bookkeeping artifact.
    """
    restaurant_id      = payload.get("restaurant_id")
    item_name          = payload.get("item_name", "Unknown item")
    expected_quantity  = payload.get("expected_quantity", 0)
    counted_quantity   = payload.get("counted_quantity", 0)
    unit               = payload.get("unit", "")

    db = SessionLocal()
    try:
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
        if not restaurant:
            return

        owner_phone = _owner_phone(restaurant)
        if owner_phone:
            direction = "less" if counted_quantity < expected_quantity else "more"
            gap = abs(counted_quantity - expected_quantity)
            from ai.whatsapp import send_whatsapp_message
            msg = (
                f"🔍 *Stock Count Discrepancy*\n\n"
                f"{item_name}: system expected {expected_quantity}{unit}, physical count found "
                f"{counted_quantity}{unit} ({gap}{unit} {direction} than expected).\n"
                f"Worth investigating if this isn't a one-off."
            )
            send_whatsapp_message(owner_phone, msg, db=db, restaurant_id=restaurant_id,
                                  message_type="stock_count_discrepancy")

        write_audit_log(
            db, restaurant_id, "stock_count_discrepancy_alerted", "executive_orchestrator",
            entity_type="stock_count", entity_id=None,
            reasoning=f"{item_name}: expected {expected_quantity}{unit} vs counted {counted_quantity}{unit}.",
            data_sources=["stock_custody_router"],
        )
    except Exception as exc:
        logger.error(f"[Orchestrator] on_stock_count_discrepancy failed: {exc}")
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


def on_order_paid(payload: dict) -> None:
    """
    Reacts to an ORDER_PAID event (past tense — the order is ALREADY settled by
    the emitter, whether the M-Pesa webhook or the POS payment endpoint, before
    this fires). Side-effects only: send an itemized customer receipt + write the
    audit log. It deliberately does NOT mutate is_paid — settlement is the
    emitter's job, so a failure here can never leave the order half-paid.

    Channel: tries WhatsApp, falls back to SMS (many Kenyan customers aren't on
    WhatsApp). Opt-out (STOP) is honoured by the send choke point. The receipt is
    itemized via brain.compose_receipt and works for any payment method.
    """
    restaurant_id  = payload.get("restaurant_id")
    order_id       = payload.get("order_id")
    amount         = payload.get("amount_cents", 0)
    customer_phone = payload.get("customer_phone")
    mpesa_ref      = payload.get("mpesa_reference", "")
    method         = payload.get("payment_method", "mpesa" if mpesa_ref else "unknown")

    db = SessionLocal()
    try:
        if customer_phone:
            from ai.whatsapp import send_whatsapp_message
            from ai.whatsapp.brain import compose_receipt
            order = (
                db.query(models.Order)
                .options(
                    joinedload(models.Order.items).joinedload(models.OrderItem.menu_item)
                )
                .filter(models.Order.id == order_id)
                .first()
            )
            if order:
                msg = compose_receipt(db, order, mpesa_ref=mpesa_ref)
                send_whatsapp_message(customer_phone, msg, db=db,
                                      restaurant_id=restaurant_id, message_type="receipt",
                                      channel="whatsapp", fallback_sms=True)

        write_audit_log(
            db, restaurant_id, "payment_received", "executive_orchestrator",
            entity_type = "order",
            entity_id   = order_id,
            before      = {"is_paid": False},
            after       = {"is_paid": True, "payment_method": method, "mpesa_ref": mpesa_ref},
            reasoning   = f"Payment confirmed ({method}). Amount: KES {amount // 100:,}.",
        )

    except Exception as exc:
        logger.error(f"[Orchestrator] on_order_paid failed: {exc}")
    finally:
        db.close()


def _owner_phone(restaurant) -> str:
    """
    The owner's WhatsApp number, or "" if none is configured. Delegates to
    `brain.owner_phone_for` (DB column first, legacy OWNER_PHONE_{id} /
    OWNER_PHONE env vars as fallback) rather than re-implementing that
    precedence — it must stay identical to the inbound resolution in
    `routers/webhooks._resolve_restaurant_by_phone`, or an owner who can reply
    to the bot can't be reached by it.
    """
    if restaurant is None:
        return ""
    from ai.whatsapp.brain import owner_phone_for
    return owner_phone_for(restaurant)


def on_mpesa_payment_failed(payload: dict) -> None:
    """
    An STK push was cancelled, timed out, or hit insufficient funds.

    Until 2026-07-08 the M-Pesa webhook emitted MPESA_PAYMENT_FAILED and nothing
    subscribed to it: the event went into the void, the order silently stayed
    unpaid, and nobody — owner or customer — was told. Staff would find out when
    the guest walked out on an unsettled tab.

    The owner is the right recipient (not the customer): the customer already saw
    the STK prompt fail on their handset, and messaging them again on a failed
    payment is the kind of unsolicited traffic the opt-out policy exists to
    prevent. Sends through `send_whatsapp_message`, the choke point that honours
    opt-out, and writes an audit row either way so the failure is recoverable
    even when no owner number is configured.
    """
    restaurant_id = payload.get("restaurant_id")
    order_id      = payload.get("order_id")
    reason        = (payload.get("reason") or "").strip() or "no reason given"

    db = SessionLocal()
    try:
        restaurant = db.query(models.Restaurant).filter(
            models.Restaurant.id == restaurant_id
        ).first()

        owner_phone = _owner_phone(restaurant)
        if owner_phone:
            from ai.whatsapp import send_whatsapp_message
            msg = (
                f"⚠️ *Payment Failed*\n\n"
                f"M-Pesa payment for order #{order_id} did not go through.\n"
                f"Reason: {reason}\n\n"
                f"_The order is still marked unpaid._"
            )
            send_whatsapp_message(owner_phone, msg, db=db, restaurant_id=restaurant_id,
                                  message_type="mpesa_payment_failed")
        else:
            logger.warning(
                f"[Orchestrator] M-Pesa payment failed for order {order_id} but no "
                f"owner phone is configured for restaurant {restaurant_id} — nobody notified"
            )

        write_audit_log(
            db, restaurant_id, "mpesa_payment_failed", "executive_orchestrator",
            entity_type = "order",
            entity_id   = order_id,
            reasoning   = f"M-Pesa STK push failed: {reason}. Order left unpaid.",
        )

    except Exception as exc:
        logger.error(f"[Orchestrator] on_mpesa_payment_failed failed: {exc}")
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

        # Bug found 2026-07-16 while extending this same alerting pattern
        # for directive 018: this read OWNER_PHONE_{id}/OWNER_PHONE env vars
        # only, never Restaurant.owner_phone — the exact class of bug
        # on_stock_critical's own comment describes fixing elsewhere in this
        # file ("Was env-var only... got no critical-stock alerts at all").
        # A restaurant onboarded via the DB column (the normal path today)
        # got zero supplier-late alerts. Switched to the shared helper.
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
        from ai.whatsapp import send_whatsapp_message
        owner_phone = _owner_phone(restaurant)
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


def on_purchase_order_created(payload: dict) -> None:
    """
    Directive 018: a purchase order was auto-drafted (par level crossed the
    reorder point). Tells the owner a draft is waiting — approval still
    happens explicitly via POST /purchase-orders/{id}/approve, this is only
    the notification that one exists, same "surface it, don't act silently"
    posture as everything else in this alerting pipeline.
    """
    restaurant_id = payload.get("restaurant_id")
    po_id         = payload.get("po_id")
    item_name     = payload.get("item_name", "Unknown item")
    quantity      = payload.get("quantity", 0)
    unit          = payload.get("unit", "")
    supplier_name = payload.get("supplier_name", "")

    db = SessionLocal()
    try:
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
        if not restaurant:
            return

        owner_phone = _owner_phone(restaurant)
        if owner_phone:
            from ai.whatsapp import send_whatsapp_message
            msg = (
                f"📝 *Purchase Order Drafted*\n\n"
                f"{quantity}{unit} {item_name} from {supplier_name} — stock hit its reorder point.\n"
                f"Reply or open the dashboard to approve before it's sent."
            )
            send_whatsapp_message(owner_phone, msg, db=db, restaurant_id=restaurant_id,
                                  message_type="purchase_order_drafted")

        write_audit_log(
            db, restaurant_id, "purchase_order_drafted", "executive_orchestrator",
            entity_type="purchase_order", entity_id=po_id,
            reasoning=f"{item_name}: reorder point crossed, drafted {quantity}{unit} from {supplier_name}.",
            data_sources=["ai.reorder"],
        )
    except Exception as exc:
        logger.error(f"[Orchestrator] on_purchase_order_created failed: {exc}")
    finally:
        db.close()


def on_purchase_order_delivered(payload: dict) -> None:
    """
    Directive 018: a delivery came in short of what was ordered — the
    supplier-leg equivalent of on_stock_transfer_discrepancy. Only fires on
    a real shortfall (see ai/reorder.receive_purchase_order), matching the
    "alert on the exception" philosophy throughout this workstream.
    """
    restaurant_id      = payload.get("restaurant_id")
    po_id              = payload.get("po_id")
    item_name          = payload.get("item_name", "Unknown item")
    quantity_ordered   = payload.get("quantity_ordered", 0)
    quantity_received  = payload.get("quantity_received", 0)
    shortfall          = payload.get("shortfall", 0)
    unit               = payload.get("unit", "")

    db = SessionLocal()
    try:
        restaurant = db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()
        if not restaurant:
            return

        owner_phone = _owner_phone(restaurant)
        if owner_phone:
            from ai.whatsapp import send_whatsapp_message
            msg = (
                f"📦 *Short Delivery*\n\n"
                f"PO #{po_id} for {item_name}: ordered {quantity_ordered}{unit}, "
                f"received {quantity_received}{unit} — {shortfall}{unit} short.\n"
                f"Recorded as-is; follow up with the supplier if this keeps happening."
            )
            send_whatsapp_message(owner_phone, msg, db=db, restaurant_id=restaurant_id,
                                  message_type="purchase_order_short_delivery")

        write_audit_log(
            db, restaurant_id, "purchase_order_short_delivery", "executive_orchestrator",
            entity_type="purchase_order", entity_id=po_id,
            reasoning=f"{item_name}: ordered {quantity_ordered}{unit}, received {quantity_received}{unit}.",
            data_sources=["stock_custody_router"],
        )
    except Exception as exc:
        logger.error(f"[Orchestrator] on_purchase_order_delivered failed: {exc}")
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
