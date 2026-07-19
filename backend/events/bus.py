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
    # A ticket the kitchen just marked READY — front-of-house (Waiter/
    # Supervisor) has to *run* it, and until now had to watch the KDS to know.
    # Same "shouldn't have to poll" justification as STOCK_TRANSFER_FULFILLED:
    # fires on the happy path, but push-only + role-scoped, so it doesn't
    # reintroduce the alert-fatigue the exception-only events guard against.
    # ORDER_CANCELLED (above) was defined long ago but never emitted or
    # subscribed — the 2026-07-18 event-map pass wires it: the kitchen needs to
    # stop cooking a ticket that was pulled. Both fire once, on the actual
    # status transition (not every PATCH), and exclude the actor.
    ORDER_READY        = "order.ready"

    # Inventory
    STOCK_LOW          = "stock.low"
    STOCK_CRITICAL     = "stock.critical"
    STOCK_RECEIVED     = "stock.received"
    STOCK_DEPLETED     = "stock.depleted"
    # A *manual* downward stock adjustment (waste/breakage/loss/correction) —
    # the shrinkage vector directive 016's stock-loss-prevention skill exists
    # for. Sales are auto-deducted (directive 017), so a hand-entered OUT is,
    # by elimination, either waste or loss: exactly what custody oversight
    # wants surfaced. Fires only on negative adjustments (routers/inventory.py),
    # never on a positive correction, and carries who did it.
    INVENTORY_ADJUSTMENT_FLAGGED = "inventory.adjustment_flagged"

    # Pricing. PRICE_CHANGED and RECOMMENDATION_GENERATED were defined early but
    # sat unemitted until the 2026-07-18 event-map pass wired them: a *manual*
    # menu price edit (routers/menu.py) is the hand-driven twin of
    # recommendation.approved, and a freshly-generated batch of AI
    # recommendations (ai/pricing) should tell its approver one is waiting.
    # RECOMMENDATION_REJECTED stays reserved (the rejecter is the only party who
    # needs to know; no one to fan out to — see directive 019 §6).
    PRICE_CHANGED      = "price.changed"
    RECOMMENDATION_GENERATED = "recommendation.generated"
    RECOMMENDATION_APPROVED  = "recommendation.approved"
    RECOMMENDATION_REJECTED  = "recommendation.rejected"

    # A weekly unattended strategist review (ai/orchestrator/strategist.py,
    # gated by the autonomous_strategist flag) just produced a headline —
    # nudge OWNER/MANAGER to read it, same posture as RECOMMENDATION_GENERATED.
    STRATEGY_REVIEW_GENERATED = "strategy.review_generated"

    # Reservations. CREATED/CANCELLED were defined early but sat unemitted and
    # unsubscribed until the 2026-07-18 event-map pass wired them: front-of-
    # house (Waiter/Supervisor) shouldn't have to keep re-opening the bookings
    # list to notice a new/pulled booking. Push-only + role-scoped, actor
    # excluded — same posture as ORDER_READY.
    RESERVATION_CREATED   = "reservation.created"
    RESERVATION_NO_SHOW   = "reservation.no_show"
    RESERVATION_CANCELLED = "reservation.cancelled"

    # Labor. SHIFT_STARTED/SHIFT_ENDED were defined early but sat unemitted —
    # LaborShift had no router at all until routers/attendance.py (2026-07-19
    # walkthrough-notes pass). Both fire on every clock-in/out (routine, not
    # exception — same posture as STOCK_TRANSFER_REQUESTED), scoped to
    # oversight tiers only, not the whole floor.
    SHIFT_STARTED  = "shift.started"
    SHIFT_ENDED    = "shift.ended"
    # A clock-in's GPS coordinates were farther than the proximity threshold
    # from the restaurant's own (routers/attendance.py) — never blocks the
    # clock-in itself, just flags it for oversight. Exception-class, not
    # routine, unlike SHIFT_STARTED above.
    SHIFT_CLOCK_IN_FLAGGED = "shift.clock_in_flagged"

    # Supply chain
    PURCHASE_ORDER_CREATED   = "purchase_order.created"
    PURCHASE_ORDER_DELIVERED = "purchase_order.delivered"
    PURCHASE_ORDER_LATE      = "purchase_order.late"
    # A PO was approved and SENT to the supplier (reorder.approve_and_send) —
    # the receiving side (Stockkeeper/Controller) now knows a delivery is
    # inbound to expect and reconcile against, rather than learning only when
    # the truck shows up. Fires once on the PENDING->SENT transition.
    PURCHASE_ORDER_APPROVED  = "purchase_order.approved"
    # A supplier's reliability score just crossed below the "watch" threshold
    # (executive.py penalises it on every late delivery). Fires once, on the
    # downward crossing — not every late delivery — so it reads as "this
    # supplier has become a problem", not per-incident noise.
    SUPPLIER_RELIABILITY_DROPPED = "supplier.reliability_dropped"

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

    # Kitchen "pull" requisition (directive 017), the routine (non-exception)
    # half of the request/fulfil/confirm chain: unlike the discrepancy/
    # variance events above, these fire on the normal happy path (every
    # request, every fulfilment) because the whole point is that a
    # Stockkeeper shouldn't have to poll the dashboard to learn the kitchen
    # is asking for something, and the kitchen shouldn't have to poll to
    # learn it's ready to collect. Fan-out is role-based (ai/notify.py), not
    # per-movement Twilio, so this doesn't reintroduce the alert-fatigue
    # problem the discrepancy/variance events were designed to avoid.
    STOCK_TRANSFER_REQUESTED  = "stock_transfer.requested"
    STOCK_TRANSFER_FULFILLED = "stock_transfer.fulfilled"

    # Account/risk signals (2026-07-17 notification audit). Both are
    # inherently non-repeating per occurrence (a lockout transition happens
    # once; a role change happens once) — no cooldown needed, same reasoning
    # as STOCK_TRANSFER_DISCREPANCY above.
    ACCOUNT_LOCKED       = "account.locked"
    STAFF_ROLE_CHANGED   = "staff.role_changed"
    STAFF_DEACTIVATED    = "staff.deactivated"
    # The symmetric partner of STAFF_DEACTIVATED (added 2026-07-18): re-enabling
    # a previously-revoked login restores access, which is just as much a
    # "who can get in" change as revoking it — arguably more of a risk (a
    # dormant account brought back). Rare, so low-noise; Owner-only, actor
    # excluded, same routing as its partner.
    STAFF_REACTIVATED    = "staff.reactivated"

    # A menu item just went unavailable mid-shift ("86'd") — POS-facing
    # staff need to stop selling it immediately. Deliberately one-directional
    # (fires True->False only, not the reverse) — matches this workstream's
    # "alert on the exception, not the routine" posture; re-enabling an item
    # is lower urgency than a live sale risk.
    MENU_ITEM_UNAVAILABLE = "menu_item.unavailable"

    # A remake or kitchen quality issue was logged against an order
    # (routers/orders.py, 2026-07-19 walkthrough-notes pass) — oversight
    # tiers should see the pattern building, not just the reporter who
    # already knows. Fires on every log (routine volume is low enough this
    # doesn't reintroduce alert fatigue), actor excluded.
    KITCHEN_INCIDENT_LOGGED = "kitchen.incident_logged"

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
