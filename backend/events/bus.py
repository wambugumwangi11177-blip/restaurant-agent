"""
backend/events/bus.py
───────────────────────
PostgreSQL-backed in-process event bus.

Why PostgreSQL NOTIFY instead of Kafka:
  - Zero new infrastructure
  - Survives process restarts (no message loss within a transaction)
  - At <100 locations, latency is <10ms — Kafka adds nothing
  - When you need Kafka (100+ locations, cross-datacenter), replace
    the _emit/_subscribe implementations. All agent code stays the same.

Usage:

  # Publisher (in an agent or router):
  from events.bus import emit
  emit("order.created", {"order_id": 123, "restaurant_id": 1, "total": 2500})

  # Subscriber (registered at startup in main.py):
  from events.bus import subscribe, EventType
  subscribe(EventType.ORDER_CREATED, my_handler_function)

  # Handler signature:
  def my_handler(payload: dict) -> None:
      ...

Event types follow: domain.action (lowercase snake_case)
"""

import json
import threading
import logging
from collections import defaultdict
from typing import Callable
from enum import Enum

logger = logging.getLogger("events.bus")

# ── Event Type Registry ───────────────────────────────────────────────────────

class EventType(str, Enum):
    # Orders
    ORDER_CREATED      = "order.created"
    ORDER_COMPLETED    = "order.completed"
    ORDER_CANCELLED    = "order.cancelled"
    ORDER_PAID         = "order.paid"

    # Inventory
    STOCK_LOW          = "stock.low"
    STOCK_CRITICAL     = "stock.critical"
    STOCK_RECEIVED     = "stock.received"
    STOCK_DEPLETED     = "stock.depleted"

    # Pricing
    PRICE_CHANGED      = "price.changed"
    RECOMMENDATION_GENERATED = "recommendation.generated"
    RECOMMENDATION_APPROVED  = "recommendation.approved"
    RECOMMENDATION_REJECTED  = "recommendation.rejected"

    # Reservations
    RESERVATION_CREATED   = "reservation.created"
    RESERVATION_NO_SHOW   = "reservation.no_show"
    RESERVATION_CANCELLED = "reservation.cancelled"

    # Labor
    SHIFT_STARTED  = "shift.started"
    SHIFT_ENDED    = "shift.ended"

    # Supply chain
    PURCHASE_ORDER_CREATED   = "purchase_order.created"
    PURCHASE_ORDER_DELIVERED = "purchase_order.delivered"
    PURCHASE_ORDER_LATE      = "purchase_order.late"

    # Stock chain-of-custody (directive 016). Both are inherently
    # non-repeating (a transfer confirm happens once; the variance job runs
    # once daily) so neither needs the last_alerted_at-style cooldown the
    # 2-hourly stock check needs — see run_variance_check in main.py.
    STOCK_TRANSFER_DISCREPANCY = "stock_transfer.discrepancy"
    STOCK_VARIANCE_FLAGGED     = "stock.variance_flagged"
    # A physical count (directive 017) found a real gap against what the
    # system expected. Fires once per count submission that exceeds
    # tolerance — inherently non-repeating like STOCK_TRANSFER_DISCREPANCY.
    STOCK_COUNT_DISCREPANCY    = "stock_count.discrepancy"

    # Marketing: CAMPAIGN_LAUNCHED / WINBACK_TRIGGERED were removed 2026-07-08
    # along with ai/marketing/campaigns.py, their only emitter. Nothing ever
    # subscribed to them. Winback is served instead by
    # brain.get_winback_candidates(): the owner asks, the AI answers, the owner
    # decides who to message. Re-introducing an autonomous outbound-marketing
    # event means first re-deciding consent, opt-out, Twilio spend, kill switch.

    # Agent system
    AGENT_FAILED    = "agent.failed"
    MORNING_BRIEFING = "briefing.morning"

    # M-Pesa
    MPESA_PAYMENT_RECEIVED = "mpesa.payment_received"
    MPESA_PAYMENT_FAILED   = "mpesa.payment_failed"


# ── In-Process Bus ────────────────────────────────────────────────────────────

_handlers: dict[str, list[Callable]] = defaultdict(list)
_lock = threading.Lock()


def subscribe(event_type: EventType | str, handler: Callable) -> None:
    """Register a handler for an event type. Called at startup."""
    key = event_type.value if isinstance(event_type, EventType) else event_type
    with _lock:
        _handlers[key].append(handler)
    logger.debug(f"[EventBus] Subscribed {handler.__name__} to {key}")


def emit(event_type: EventType | str, payload: dict) -> None:
    """
    Emit an event. All registered handlers are called synchronously
    in the emitting thread. For slow handlers, use emit_async().

    We run handlers in a try/except so one bad handler doesn't break
    the emitting code path (e.g., a stock alert failure doesn't
    prevent an order from being saved).
    """
    key = event_type.value if isinstance(event_type, EventType) else event_type
    with _lock:
        handlers = list(_handlers.get(key, []))

    for handler in handlers:
        try:
            handler(payload)
        except Exception as exc:
            logger.error(f"[EventBus] Handler {handler.__name__} failed for {key}: {exc}")


def emit_async(event_type: EventType | str, payload: dict) -> None:
    """
    Emit in a background thread. Use for slow handlers (WhatsApp sends,
    email sends, external API calls) that shouldn't block the request.
    """
    t = threading.Thread(target=emit, args=(event_type, payload), daemon=True)
    t.start()


def clear_handlers() -> None:
    """Test utility — clears all registered handlers."""
    with _lock:
        _handlers.clear()


def list_subscriptions() -> dict:
    """Returns a summary of all registered handlers by event type."""
    with _lock:
        return {k: [h.__name__ for h in v] for k, v in _handlers.items()}
