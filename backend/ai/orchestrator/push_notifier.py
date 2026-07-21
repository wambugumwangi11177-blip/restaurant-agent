"""
backend/ai/orchestrator/push_notifier.py
───────────────────────────────────────────
Second, independent subscriber on the event bus (events/bus.py), alongside
executive.py's WhatsApp handlers — not replacing them. Fans events out to
the in-app notification feed + Web Push (ai/notify.py) instead of a phone
number, and unlike executive.py's WhatsApp handlers (which only ever reach
the restaurant owner), this targets every active staff member whose
staff_role is relevant to the event.

Deliberately a separate module rather than edits inside executive.py's
existing handlers: zero risk to the WhatsApp pipeline (a bug here can't
break it, and vice versa — each subscriber on a given EventType is wrapped
in its own try/except by events/bus.py's emit()), and if Twilio gets funded
again later both channels simply run side by side.

Registered once at startup via register_push_handlers(), called from
main.py right after executive.py's register_all_handlers().
"""

import logging
from collections import defaultdict

from database import SessionLocal
import models
from events.bus import subscribe, EventType
from ai.notify import notify_users
from routers.deps import get_staff_users_for_restaurant

logger = logging.getLogger("ai.orchestrator.push_notifier")

StaffRole = models.StaffRole

# Who gets notified for each event. Tunable — this is the single source of
# truth for routing, kept as one visible table rather than scattered
# per-handler literals.
_EVENT_TARGET_ROLES: dict[EventType, list[StaffRole]] = {
    EventType.STOCK_CRITICAL:             [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER, StaffRole.STOCKKEEPER],
    EventType.STOCK_DEPLETED:             [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER, StaffRole.STOCKKEEPER],
    EventType.STOCK_TRANSFER_DISCREPANCY: [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    EventType.STOCK_VARIANCE_FLAGGED:     [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    EventType.STOCK_COUNT_DISCREPANCY:    [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    # Kitchen "pull" requisition (directive 017): the storekeeper has to act
    # on a request, so they're the primary target; Manager/Supervisor are
    # visibility ("sees the log", directive 017's described real-world
    # practice) even on restaurants where they have no inventory nav page —
    # _resolve_link below routes them to their own tier home instead of a
    # route that would 403/bounce for them.
    EventType.STOCK_TRANSFER_REQUESTED:   [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.STOCKKEEPER],
    # Fulfilled = ready to collect — the requesting side (Kitchen) needs to
    # know to go get it and confirm receipt.
    EventType.STOCK_TRANSFER_FULFILLED:   [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.KITCHEN],
    EventType.PURCHASE_ORDER_LATE:        [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    # A draft PO needs an approver to know it exists — executive.py's WhatsApp
    # handler only ever reaches the Owner's phone, but Supervisor is an
    # approver too (routers/purchase_orders.py's _CAN_APPROVE) and had no
    # notification path at all before this. Controller included for
    # visibility (read access per the permission matrix), not action.
    EventType.PURCHASE_ORDER_CREATED:     [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.CONTROLLER],
    EventType.RESERVATION_NO_SHOW:        [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER],
    EventType.MPESA_PAYMENT_FAILED:       [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER],
    EventType.AGENT_FAILED:               [StaffRole.OWNER],
    # M-Pesa settles asynchronously (the customer approves on their own phone,
    # sometimes minutes after the order was rung up) — the front-of-house
    # tiers waiting on that confirmation had no signal it landed short of
    # polling the orders list. Only the webhook path emits this with
    # mpesa_reference set; the POS "mark as paid" path (routers/orders.py)
    # is the staff member's own synchronous action and is filtered out in
    # the handler below, not here, to keep this table describing *who*, not
    # *which emit site*.
    EventType.ORDER_PAID:                 [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER],
    # Short/partial delivery (directive 018) — executive.py's WhatsApp
    # handler only reaches the Owner; Controller/Stockkeeper/Manager (who
    # actually reconcile and re-order) had no notification path at all.
    EventType.PURCHASE_ORDER_DELIVERED:   [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER, StaffRole.STOCKKEEPER],
    # approve_pricing_rec() updates the live menu price immediately — POS
    # staff quoting from memory need to know it changed, not just Owner
    # (executive.py's on_recommendation_approved only records memory/audit,
    # notifies nobody).
    EventType.RECOMMENDATION_APPROVED:    [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER],
    # Risk/security signals (2026-07-17 audit) — Owner only, deliberately not
    # fanned out wider: a possible brute-force attempt or a privilege change
    # is exactly the kind of thing that should reach one accountable person,
    # not become background noise across every tier.
    EventType.ACCOUNT_LOCKED:             [StaffRole.OWNER],
    EventType.STAFF_ROLE_CHANGED:         [StaffRole.OWNER],
    EventType.STAFF_DEACTIVATED:          [StaffRole.OWNER],
    EventType.STAFF_REACTIVATED:          [StaffRole.OWNER],
    # A menu item just went unavailable mid-shift — every POS-facing tier
    # needs to stop selling it, not just Owner. Kitchen added 2026-07-19 (was
    # missing): the owner's walkthrough notes are explicit that an auto-86
    # on stock depletion must tell "the kitchen and the POS and the
    # waiters", not just front-of-house.
    EventType.MENU_ITEM_UNAVAILABLE:      [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER, StaffRole.KITCHEN],
    # 2026-07-18 event-map pass. These four are high-frequency *operational*
    # events (every ready ticket, every booking), so unlike almost every event
    # above they deliberately EXCLUDE the Owner: the owner's feed is for the
    # exception class (stockouts, variance, security, failed payments), not a
    # live running commentary of the floor — that's exactly the alert-fatigue
    # this workstream guards against. They reach only the tiers that must act.
    # Actor is excluded per-event in the handlers (whoever advanced the ticket
    # or took the booking already knows).
    #
    # Kitchen marked it READY -> front-of-house runs the food.
    EventType.ORDER_READY:                [StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER],
    # A live ticket was pulled -> the kitchen must stop cooking it.
    EventType.ORDER_CANCELLED:            [StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.KITCHEN],
    # New booking landed / a booking freed its slot -> front-of-house.
    EventType.RESERVATION_CREATED:        [StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER],
    EventType.RESERVATION_CANCELLED:      [StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER],
    # PO approved & sent -> the receiving side expects an inbound delivery.
    # Owner already saw the draft alert (PURCHASE_ORDER_CREATED), so this is
    # scoped to who reconciles goods in, not re-notifying the approver.
    EventType.PURCHASE_ORDER_APPROVED:    [StaffRole.MANAGER, StaffRole.CONTROLLER, StaffRole.STOCKKEEPER],
    # A manual downward stock adjustment (waste/loss) — a custody/shrinkage
    # signal, so it goes to the oversight tiers (not the whole floor), same
    # recipient set as the variance/count-discrepancy events. Actor excluded
    # in the handler (they made the entry; the point is *others* see it).
    EventType.INVENTORY_ADJUSTMENT_FLAGGED: [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    # An online order landed with no staff involved -> the kitchen needs to
    # cook it (map §3/§4 "new order"). Scoped to the public path only.
    EventType.ORDER_CREATED:              [StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.KITCHEN],
    # A supplier crossed into "watch" territory -> procurement oversight.
    EventType.SUPPLIER_RELIABILITY_DROPPED: [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    # A menu price was changed by hand -> same POS-facing set as the AI-driven
    # recommendation.approved, so staff quoting from memory stay correct.
    EventType.PRICE_CHANGED:              [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER],
    # A batch of AI pricing recommendations is waiting -> the approvers.
    EventType.RECOMMENDATION_GENERATED:   [StaffRole.OWNER, StaffRole.MANAGER],
    # The weekly unattended strategist review produced a headline -> same
    # audience as RECOMMENDATION_GENERATED (they decide whether to act on it).
    EventType.STRATEGY_REVIEW_GENERATED:  [StaffRole.OWNER, StaffRole.MANAGER],
    # 2026-07-19 walkthrough-notes pass — remake/quality issue logged ->
    # oversight tiers, not the whole floor (same posture as
    # INVENTORY_ADJUSTMENT_FLAGGED). Actor (the reporter) excluded in the
    # handler.
    EventType.KITCHEN_INCIDENT_LOGGED:    [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR],
    # Clock-in/out — routine, high-frequency, so scoped to the tiers that
    # actually manage labor (not the whole floor, and not Owner directly —
    # matches ORDER_READY/RESERVATION_CREATED's "operational, not
    # exception" posture above).
    EventType.SHIFT_STARTED:              [StaffRole.MANAGER, StaffRole.SUPERVISOR],
    EventType.SHIFT_ENDED:                [StaffRole.MANAGER, StaffRole.SUPERVISOR],
    # A clock-in was farther than the proximity threshold from the
    # restaurant — an exception, unlike the two above, so it does reach
    # Owner (same posture as ACCOUNT_LOCKED: a possible attendance-fraud
    # signal is exactly the kind of thing one accountable person should see).
    EventType.SHIFT_CLOCK_IN_FLAGGED:     [StaffRole.OWNER, StaffRole.MANAGER],
    # Sprint 3 — suspicious-transaction pattern flagged (void spike, refund
    # burst, payment mismatch, off-hours activity). Owner + Controller only,
    # deliberately excluding Manager/Supervisor: the flagged actor could BE a
    # manager-tier staff member, so this stays with the same oversight-only
    # posture as ACCOUNT_LOCKED/STAFF_ROLE_CHANGED above, not a wide fan-out.
    EventType.SUSPICIOUS_TRANSACTION_FLAGGED: [StaffRole.OWNER, StaffRole.CONTROLLER],
    # Sprint 4 — drawer count landed outside tolerance. Same oversight-only
    # posture as SUSPICIOUS_TRANSACTION_FLAGGED (the counting staff member
    # could be the one the variance implicates).
    EventType.CASH_RECONCILIATION_FLAGGED: [StaffRole.OWNER, StaffRole.CONTROLLER],
}

# Where each domain actually lives per tier, post-2026-07-17 (every staff
# tier moved off /dashboard/* onto its own /staff/<tier>/* route tree —
# dashboard/layout.tsx now immediately redirects any staff_role account back
# to its tier home). A role missing from a domain's map here has no page for
# that domain at all, so it falls back to _TIER_HOME instead of a link that
# would bounce/404 for them. Keep in sync with frontend/src/app/staff/*/layout.tsx
# and frontend/src/lib/permissions.ts — this is the backend mirror of that
# nav structure, same "don't let it silently drift" reasoning as that file's
# own docstring.
_TIER_URLS: dict[str, dict[StaffRole, str]] = {
    "inventory": {
        StaffRole.OWNER: "/dashboard/inventory",
        StaffRole.MANAGER: "/staff/manager/inventory",
        StaffRole.CONTROLLER: "/staff/controller",
        StaffRole.STOCKKEEPER: "/staff/stockkeeper",
        StaffRole.KITCHEN: "/staff/kitchen/stock",
    },
    "purchasing": {
        StaffRole.OWNER: "/dashboard/purchasing",
        StaffRole.MANAGER: "/staff/manager/purchasing",
        StaffRole.CONTROLLER: "/staff/controller/purchasing",
        StaffRole.STOCKKEEPER: "/staff/stockkeeper/purchasing",
        StaffRole.SUPERVISOR: "/staff/supervisor/purchasing",
    },
    "reservations": {
        StaffRole.OWNER: "/dashboard/reservations",
        StaffRole.MANAGER: "/staff/manager/reservations",
        StaffRole.SUPERVISOR: "/staff/supervisor/reservations",
        StaffRole.WAITER: "/staff/waiter/reservations",
    },
    "ai-ops": {
        StaffRole.OWNER: "/dashboard/ai-ops",
        StaffRole.MANAGER: "/staff/manager/ai-ops",
        StaffRole.CONTROLLER: "/staff/controller/ai-ops",
    },
    # The actual StrategyAgent (headline/steps/risks) UI, distinct from
    # "ai-ops" above (cost/token/reliability metrics only). Owner-only today
    # — no /staff/manager/ai page exists yet, so a Manager notified of a
    # strategy review falls back to _TIER_HOME (their dashboard home) rather
    # than a page that can't show them anything, per _resolve_link's fallback.
    "ai": {
        StaffRole.OWNER: "/dashboard/ai",
    },
    "orders": {
        StaffRole.OWNER: "/dashboard/orders",
        StaffRole.MANAGER: "/staff/manager/orders",
        StaffRole.SUPERVISOR: "/staff/supervisor/orders",
        StaffRole.WAITER: "/staff/waiter/orders",
        # Kitchen order events (order.created / order.cancelled) are *actionable*
        # — "start preparing it" / "stop cooking it" both happen by advancing the
        # ticket on the KDS, which is the kitchen tier home (/staff/kitchen →
        # KDSBoard). /staff/kitchen/orders renders the read-only OrderList (no
        # status-advance button), so routing the notification there dropped the
        # tap one page short of the action. Point it at the KDS instead.
        StaffRole.KITCHEN: "/staff/kitchen",
        StaffRole.CONTROLLER: "/staff/controller/orders",
    },
    "menu": {
        StaffRole.OWNER: "/dashboard/menu",
        StaffRole.MANAGER: "/staff/manager/menu",
        StaffRole.SUPERVISOR: "/staff/supervisor/menu",
        StaffRole.WAITER: "/staff/waiter/menu",
        StaffRole.KITCHEN: "/staff/kitchen/menu",
    },
    "staff": {
        StaffRole.OWNER: "/dashboard/staff",
        StaffRole.MANAGER: "/staff/manager/staff",
    },
}

# Matches frontend/src/lib/permissions.ts's TIER_HOME + dashboard/layout.tsx's
# Owner landing — the safe fallback when a role has no page for a domain.
_TIER_HOME: dict[StaffRole, str] = {
    StaffRole.OWNER: "/dashboard",
    StaffRole.MANAGER: "/staff/manager",
    StaffRole.SUPERVISOR: "/staff/supervisor",
    StaffRole.CONTROLLER: "/staff/controller",
    StaffRole.STOCKKEEPER: "/staff/stockkeeper",
    StaffRole.KITCHEN: "/staff/kitchen",
    StaffRole.WAITER: "/staff/waiter",
}


def register_push_handlers() -> None:
    """Register all push/in-app handlers on the event bus. Called once from
    main.py on startup, right after executive.py's register_all_handlers()."""
    subscribe(EventType.STOCK_CRITICAL, _on_stock_critical)
    subscribe(EventType.STOCK_DEPLETED, _on_stock_depleted)
    subscribe(EventType.STOCK_TRANSFER_DISCREPANCY, _on_stock_transfer_discrepancy)
    subscribe(EventType.STOCK_VARIANCE_FLAGGED, _on_stock_variance_flagged)
    subscribe(EventType.STOCK_COUNT_DISCREPANCY, _on_stock_count_discrepancy)
    subscribe(EventType.STOCK_TRANSFER_REQUESTED, _on_stock_transfer_requested)
    subscribe(EventType.STOCK_TRANSFER_FULFILLED, _on_stock_transfer_fulfilled)
    subscribe(EventType.PURCHASE_ORDER_LATE, _on_purchase_order_late)
    subscribe(EventType.PURCHASE_ORDER_CREATED, _on_purchase_order_created)
    subscribe(EventType.RESERVATION_NO_SHOW, _on_reservation_no_show)
    subscribe(EventType.MPESA_PAYMENT_FAILED, _on_mpesa_payment_failed)
    subscribe(EventType.AGENT_FAILED, _on_agent_failed)
    subscribe(EventType.ORDER_PAID, _on_order_paid)
    subscribe(EventType.PURCHASE_ORDER_DELIVERED, _on_purchase_order_delivered)
    subscribe(EventType.RECOMMENDATION_APPROVED, _on_recommendation_approved)
    subscribe(EventType.ACCOUNT_LOCKED, _on_account_locked)
    subscribe(EventType.STAFF_ROLE_CHANGED, _on_staff_role_changed)
    subscribe(EventType.STAFF_DEACTIVATED, _on_staff_deactivated)
    subscribe(EventType.MENU_ITEM_UNAVAILABLE, _on_menu_item_unavailable)
    subscribe(EventType.ORDER_READY, _on_order_ready)
    subscribe(EventType.ORDER_CANCELLED, _on_order_cancelled)
    subscribe(EventType.RESERVATION_CREATED, _on_reservation_created)
    subscribe(EventType.RESERVATION_CANCELLED, _on_reservation_cancelled)
    subscribe(EventType.PURCHASE_ORDER_APPROVED, _on_purchase_order_approved)
    subscribe(EventType.INVENTORY_ADJUSTMENT_FLAGGED, _on_inventory_adjustment_flagged)
    subscribe(EventType.ORDER_CREATED, _on_order_created)
    subscribe(EventType.SUPPLIER_RELIABILITY_DROPPED, _on_supplier_reliability_dropped)
    subscribe(EventType.PRICE_CHANGED, _on_price_changed)
    subscribe(EventType.RECOMMENDATION_GENERATED, _on_recommendation_generated)
    subscribe(EventType.STAFF_REACTIVATED, _on_staff_reactivated)
    subscribe(EventType.STRATEGY_REVIEW_GENERATED, _on_strategy_review_generated)
    subscribe(EventType.KITCHEN_INCIDENT_LOGGED, _on_kitchen_incident_logged)
    subscribe(EventType.SHIFT_STARTED, _on_shift_started)
    subscribe(EventType.SHIFT_ENDED, _on_shift_ended)
    subscribe(EventType.SHIFT_CLOCK_IN_FLAGGED, _on_shift_clock_in_flagged)
    subscribe(EventType.SUSPICIOUS_TRANSACTION_FLAGGED, _on_suspicious_transaction_flagged)
    subscribe(EventType.CASH_RECONCILIATION_FLAGGED, _on_cash_reconciliation_flagged)

    logger.info("[PushNotifier] All handlers registered")


# ── Shared helpers ───────────────────────────────────────────────────────

def _resolve_link(role: StaffRole, domain: str | None) -> str:
    if domain:
        url = _TIER_URLS.get(domain, {}).get(role)
        if url:
            return url
    return _TIER_HOME.get(role, "/dashboard")


def _fan_out(db, restaurant, event_type: EventType, title: str, body: str, domain: str | None,
             exclude_user_id: int | None = None) -> None:
    """Notify every role targeted by event_type, each with a link resolved to
    a page that role actually has (see _resolve_link) rather than one
    hardcoded link every role gets regardless of whether they can open it.
    exclude_user_id skips the actor of a self-triggered event (e.g. a Manager
    who just changed someone's role doesn't need to be told about it).

    Notifications are tagged with a severity (ai/escalation/engine.py's
    EVENT_SEVERITY map) when the event type is one that should page a human
    if left unacknowledged — every other event stays severity=None, an
    ordinary in-app notification with no escalation clock (unchanged from
    before Sprint 2)."""
    roles = _EVENT_TARGET_ROLES.get(event_type, [])
    if not roles:
        return

    from ai.escalation.engine import severity_for
    severity = severity_for(event_type.value)

    users = get_staff_users_for_restaurant(db, restaurant, roles)
    by_role: dict[StaffRole, list[int]] = defaultdict(list)
    for u in users:
        if exclude_user_id is not None and u.id == exclude_user_id:
            continue
        by_role[u.staff_role].append(u.id)

    for role, user_ids in by_role.items():
        notify_users(db, user_ids, title, body, event_type.value, _resolve_link(role, domain),
                     severity=severity)


def _get_restaurant(db, restaurant_id):
    if not restaurant_id:
        return None
    return db.query(models.Restaurant).filter(models.Restaurant.id == restaurant_id).first()


# ── Handlers ──────────────────────────────────────────────────────────────

def _on_stock_critical(payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "An item")
    hours_left = payload.get("hours_remaining", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Stock critical: {item_name}"
        body = f"{item_name} has about {hours_left}h of stock left."
        _fan_out(db, restaurant, EventType.STOCK_CRITICAL, title, body, "inventory")
    except Exception as exc:
        logger.error(f"[PushNotifier] stock_critical failed: {exc}")
    finally:
        db.close()


def _on_stock_depleted(payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name")
    if not (restaurant_id and item_name):
        return

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Out of stock: {item_name}"
        body = f"{item_name} has hit zero — orders using it may need to be 86'd."
        _fan_out(db, restaurant, EventType.STOCK_DEPLETED, title, body, "inventory")
    except Exception as exc:
        logger.error(f"[PushNotifier] stock_depleted failed: {exc}")
    finally:
        db.close()


def _on_stock_transfer_discrepancy(payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "Unknown item")
    declared = payload.get("declared_quantity", 0)
    confirmed = payload.get("confirmed_quantity", 0)
    unit = payload.get("unit", "")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = "Stock transfer mismatch"
        body = f"{item_name}: declared {declared}{unit}, confirmed {confirmed}{unit}."
        _fan_out(db, restaurant, EventType.STOCK_TRANSFER_DISCREPANCY, title, body, "inventory")
    except Exception as exc:
        logger.error(f"[PushNotifier] stock_transfer_discrepancy failed: {exc}")
    finally:
        db.close()


def _on_stock_variance_flagged(payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    items = payload.get("items", [])
    if not items:
        return

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Stock variance flagged ({len(items)} item{'s' if len(items) != 1 else ''})"
        top = items[0]
        body = f"{top.get('item_name', 'An item')} is off by {top.get('variance_pct', 0)}%" + (
            f" (+{len(items) - 1} more)" if len(items) > 1 else "."
        )
        _fan_out(db, restaurant, EventType.STOCK_VARIANCE_FLAGGED, title, body, "inventory")
    except Exception as exc:
        logger.error(f"[PushNotifier] stock_variance_flagged failed: {exc}")
    finally:
        db.close()


def _on_stock_count_discrepancy(payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "Unknown item")
    expected = payload.get("expected_quantity", 0)
    counted = payload.get("counted_quantity", 0)
    unit = payload.get("unit", "")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = "Stock count discrepancy"
        body = f"{item_name}: expected {expected}{unit}, counted {counted}{unit}."
        _fan_out(db, restaurant, EventType.STOCK_COUNT_DISCREPANCY, title, body, "inventory")
    except Exception as exc:
        logger.error(f"[PushNotifier] stock_count_discrepancy failed: {exc}")
    finally:
        db.close()


def _on_stock_transfer_requested(payload: dict) -> None:
    """Kitchen asked for an ingredient (directive 017's "pull"). Unlike the
    discrepancy/variance handlers above, this fires on every request, not
    just an exception — see EventType.STOCK_TRANSFER_REQUESTED's docstring."""
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "An item")
    to_location = payload.get("to_location", "kitchen")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Stock requested: {item_name}"
        body = f"{to_location.capitalize()} needs {item_name} — fulfil from the store when ready."
        _fan_out(db, restaurant, EventType.STOCK_TRANSFER_REQUESTED, title, body, "inventory")
    except Exception as exc:
        logger.error(f"[PushNotifier] stock_transfer_requested failed: {exc}")
    finally:
        db.close()


def _on_stock_transfer_fulfilled(payload: dict) -> None:
    """Storekeeper committed a quantity against a kitchen request — ready to
    collect and confirm. Same "fires on the happy path" reasoning as above."""
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "An item")
    quantity = payload.get("quantity", 0)
    unit = payload.get("unit", "")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Ready to collect: {item_name}"
        body = f"{quantity}{unit} of {item_name} is on its way — confirm receipt once it arrives."
        _fan_out(db, restaurant, EventType.STOCK_TRANSFER_FULFILLED, title, body, "inventory")
    except Exception as exc:
        logger.error(f"[PushNotifier] stock_transfer_fulfilled failed: {exc}")
    finally:
        db.close()


def _on_purchase_order_late(payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    supplier_name = payload.get("supplier_name", "A supplier")
    item_name = payload.get("item_name", "")
    days_late = payload.get("days_late", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = "Purchase order late"
        body = f"{supplier_name}'s delivery of {item_name} is {days_late}d overdue." if item_name \
            else f"{supplier_name}'s delivery is {days_late}d overdue."
        _fan_out(db, restaurant, EventType.PURCHASE_ORDER_LATE, title, body, "purchasing")
    except Exception as exc:
        logger.error(f"[PushNotifier] purchase_order_late failed: {exc}")
    finally:
        db.close()


def _on_purchase_order_created(payload: dict) -> None:
    """A PO was auto-drafted (directive 018) and needs a human approval —
    executive.py's WhatsApp handler for this only ever reaches the Owner's
    phone; Supervisor is an approver too (routers/purchase_orders.py's
    _CAN_APPROVE) and had no notification path for this event at all."""
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "An item")
    quantity = payload.get("quantity", 0)
    unit = payload.get("unit", "")
    supplier_name = payload.get("supplier_name", "")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Purchase order ready to approve: {item_name}"
        body = f"{quantity}{unit} of {item_name} from {supplier_name}." if supplier_name \
            else f"{quantity}{unit} of {item_name}."
        _fan_out(db, restaurant, EventType.PURCHASE_ORDER_CREATED, title, body, "purchasing")
    except Exception as exc:
        logger.error(f"[PushNotifier] purchase_order_created failed: {exc}")
    finally:
        db.close()


def _on_reservation_no_show(payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    customer_name = payload.get("customer_name", "A guest")
    party_size = payload.get("party_size", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = "Reservation no-show"
        body = f"{customer_name} (party of {party_size}) didn't show up."
        _fan_out(db, restaurant, EventType.RESERVATION_NO_SHOW, title, body, "reservations")
    except Exception as exc:
        logger.error(f"[PushNotifier] reservation_no_show failed: {exc}")
    finally:
        db.close()


def _on_mpesa_payment_failed(payload: dict) -> None:
    restaurant_id = payload.get("restaurant_id")
    order_id = payload.get("order_id")
    reason = (payload.get("reason") or "").strip() or "no reason given"

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = "M-Pesa payment failed"
        body = f"Order #{order_id}: payment failed ({reason})." if order_id else f"A payment failed ({reason})."
        _fan_out(db, restaurant, EventType.MPESA_PAYMENT_FAILED, title, body, "orders")
    except Exception as exc:
        logger.error(f"[PushNotifier] mpesa_payment_failed failed: {exc}")
    finally:
        db.close()


def _on_agent_failed(payload: dict) -> None:
    agent_name = payload.get("agent_name", "An agent")
    restaurant_id = payload.get("restaurant_id")

    db = SessionLocal()
    try:
        # Unlike executive.py's WhatsApp handler (which reads OWNER_PHONE
        # directly and skips the Restaurant lookup entirely), this resolves
        # Restaurant properly rather than reproducing that gap.
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = "AI agent failed"
        body = f"{agent_name} failed to run — check AI Ops for details."
        _fan_out(db, restaurant, EventType.AGENT_FAILED, title, body, "ai-ops")
    except Exception as exc:
        logger.error(f"[PushNotifier] agent_failed failed: {exc}")
    finally:
        db.close()


def _on_order_paid(payload: dict) -> None:
    """Only notify for the M-Pesa webhook path (async settlement, nobody
    necessarily watching) — the POS "mark as paid" path is the staff
    member's own synchronous action and carries no mpesa_reference, so it's
    filtered out here rather than never emitting from that path at all
    (routers/orders.py's emit is reused as-is for executive.py's receipt
    handler, which needs it regardless)."""
    restaurant_id = payload.get("restaurant_id")
    mpesa_reference = payload.get("mpesa_reference")
    if not mpesa_reference:
        return

    order_id = payload.get("order_id")
    amount_cents = payload.get("amount_cents", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Payment received — Order #{order_id}"
        body = f"M-Pesa payment of KES {amount_cents // 100:,} confirmed."
        _fan_out(db, restaurant, EventType.ORDER_PAID, title, body, "orders")
    except Exception as exc:
        logger.error(f"[PushNotifier] order_paid failed: {exc}")
    finally:
        db.close()


def _on_purchase_order_delivered(payload: dict) -> None:
    """Short/partial delivery only (ai/reorder.py emits this exclusively on a
    real shortfall — matches the "alert on the exception" philosophy)."""
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "Unknown item")
    quantity_ordered = payload.get("quantity_ordered", 0)
    quantity_received = payload.get("quantity_received", 0)
    unit = payload.get("unit", "")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Short delivery: {item_name}"
        body = f"Ordered {quantity_ordered}{unit}, received {quantity_received}{unit}."
        _fan_out(db, restaurant, EventType.PURCHASE_ORDER_DELIVERED, title, body, "purchasing")
    except Exception as exc:
        logger.error(f"[PushNotifier] purchase_order_delivered failed: {exc}")
    finally:
        db.close()


def _on_recommendation_approved(payload: dict) -> None:
    """A pricing recommendation was approved — approve_pricing_rec() updates
    the live menu price immediately, so POS-facing staff need to know the
    price they're quoting from memory just changed."""
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "A menu item")
    old_price = payload.get("old_price", 0)
    new_price = payload.get("new_price", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Price updated: {item_name}"
        body = f"KES {old_price // 100:,} -> KES {new_price // 100:,}."
        _fan_out(db, restaurant, EventType.RECOMMENDATION_APPROVED, title, body, "menu")
    except Exception as exc:
        logger.error(f"[PushNotifier] recommendation_approved failed: {exc}")
    finally:
        db.close()


def _on_account_locked(payload: dict) -> None:
    """A staff login just crossed the failed-attempt threshold and got
    locked out — a possible brute-force attempt, owner-only per
    _EVENT_TARGET_ROLES (see that table's comment for why this doesn't fan
    out wider)."""
    restaurant_id = payload.get("restaurant_id")
    email = payload.get("email", "An account")
    lockout_minutes = payload.get("lockout_minutes", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = "Account locked out"
        body = f"{email} was locked for {lockout_minutes} minutes after repeated failed logins."
        _fan_out(db, restaurant, EventType.ACCOUNT_LOCKED, title, body, "staff")
    except Exception as exc:
        logger.error(f"[PushNotifier] account_locked failed: {exc}")
    finally:
        db.close()


def _on_staff_role_changed(payload: dict) -> None:
    """A staff member's role was changed — real-time visibility alongside the
    AgentAuditLog entry routers/staff.py already writes. Excludes the actor
    (changed_by_user_id): they already know, they just did it."""
    restaurant_id = payload.get("restaurant_id")
    staff_name = payload.get("staff_name", "A staff member")
    before_role = payload.get("before_role") or "unassigned"
    after_role = payload.get("after_role", "unknown")
    changed_by = payload.get("changed_by", "someone")
    changed_by_user_id = payload.get("changed_by_user_id")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Role changed: {staff_name}"
        body = f"{before_role} -> {after_role}, by {changed_by}."
        _fan_out(db, restaurant, EventType.STAFF_ROLE_CHANGED, title, body, "staff",
                 exclude_user_id=changed_by_user_id)
    except Exception as exc:
        logger.error(f"[PushNotifier] staff_role_changed failed: {exc}")
    finally:
        db.close()


def _on_staff_deactivated(payload: dict) -> None:
    """A staff login was just revoked — directive 016's own risk table names
    ex-staff retaining access as a real risk; this confirms back to Owner
    that a deactivation actually happened, in real time. Excludes the actor."""
    restaurant_id = payload.get("restaurant_id")
    staff_name = payload.get("staff_name", "A staff member")
    deactivated_by = payload.get("deactivated_by", "someone")
    deactivated_by_user_id = payload.get("deactivated_by_user_id")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Staff deactivated: {staff_name}"
        body = f"Login revoked by {deactivated_by}."
        _fan_out(db, restaurant, EventType.STAFF_DEACTIVATED, title, body, "staff",
                 exclude_user_id=deactivated_by_user_id)
    except Exception as exc:
        logger.error(f"[PushNotifier] staff_deactivated failed: {exc}")
    finally:
        db.close()


def _on_staff_reactivated(payload: dict) -> None:
    """A revoked staff login was restored — symmetric with _on_staff_deactivated.
    Owner-only, excludes the actor who did it."""
    restaurant_id = payload.get("restaurant_id")
    staff_name = payload.get("staff_name", "A staff member")
    reactivated_by = payload.get("reactivated_by", "someone")
    reactivated_by_user_id = payload.get("reactivated_by_user_id")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Staff reactivated: {staff_name}"
        body = f"Login restored by {reactivated_by}."
        _fan_out(db, restaurant, EventType.STAFF_REACTIVATED, title, body, "staff",
                 exclude_user_id=reactivated_by_user_id)
    except Exception as exc:
        logger.error(f"[PushNotifier] staff_reactivated failed: {exc}")
    finally:
        db.close()


def _on_menu_item_unavailable(payload: dict) -> None:
    """A menu item just went unavailable mid-shift ("86'd") — POS-facing
    staff need to stop selling it immediately (routers/menu.py only emits
    this on the True->False transition, never the reverse)."""
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "A menu item")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"86'd: {item_name}"
        body = f"{item_name} is no longer available — stop selling it."
        _fan_out(db, restaurant, EventType.MENU_ITEM_UNAVAILABLE, title, body, "menu")
    except Exception as exc:
        logger.error(f"[PushNotifier] menu_item_unavailable failed: {exc}")
    finally:
        db.close()


def _on_order_ready(payload: dict) -> None:
    """Kitchen marked a ticket READY — front-of-house needs to run it. Fires on
    the READY transition only (routers/orders.py), actor excluded."""
    restaurant_id = payload.get("restaurant_id")
    order_id = payload.get("order_id")
    table_number = payload.get("table_number")
    customer_name = payload.get("customer_name") or ""

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        where = f"Table {table_number}" if table_number else (customer_name or "Takeaway")
        title = f"Order ready — {where}"
        body = f"Order #{order_id} is ready to run." if order_id else "An order is ready to run."
        _fan_out(db, restaurant, EventType.ORDER_READY, title, body, "orders",
                 exclude_user_id=payload.get("actor_user_id"))
    except Exception as exc:
        logger.error(f"[PushNotifier] order_ready failed: {exc}")
    finally:
        db.close()


def _on_order_cancelled(payload: dict) -> None:
    """A live ticket was pulled — the kitchen must stop cooking it. Fires on the
    CANCELLED transition only, actor excluded."""
    restaurant_id = payload.get("restaurant_id")
    order_id = payload.get("order_id")
    table_number = payload.get("table_number")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        where = f" (Table {table_number})" if table_number else ""
        title = f"Order cancelled: #{order_id}" if order_id else "Order cancelled"
        body = f"Order #{order_id}{where} was cancelled — stop preparing it." if order_id \
            else "An order was cancelled — stop preparing it."
        _fan_out(db, restaurant, EventType.ORDER_CANCELLED, title, body, "orders",
                 exclude_user_id=payload.get("actor_user_id"))
    except Exception as exc:
        logger.error(f"[PushNotifier] order_cancelled failed: {exc}")
    finally:
        db.close()


def _on_reservation_created(payload: dict) -> None:
    """A new booking landed — front-of-house shouldn't have to poll to see it.
    Actor (the staff member who took it) excluded."""
    restaurant_id = payload.get("restaurant_id")
    customer_name = payload.get("customer_name") or "A guest"
    party_size = payload.get("party_size", 0)
    res_date = payload.get("reservation_date") or ""
    res_time = payload.get("reservation_time") or ""

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        when = f" for {res_date} {res_time}".rstrip() if (res_date or res_time) else ""
        title = f"New booking: {customer_name}"
        body = f"Party of {party_size}{when}." if party_size else f"New reservation{when}."
        _fan_out(db, restaurant, EventType.RESERVATION_CREATED, title, body, "reservations",
                 exclude_user_id=payload.get("actor_user_id"))
    except Exception as exc:
        logger.error(f"[PushNotifier] reservation_created failed: {exc}")
    finally:
        db.close()


def _on_reservation_cancelled(payload: dict) -> None:
    """A booking freed its table/slot — front-of-house should know. Actor
    excluded."""
    restaurant_id = payload.get("restaurant_id")
    customer_name = payload.get("customer_name") or "A guest"
    party_size = payload.get("party_size", 0)
    res_date = payload.get("reservation_date") or ""
    res_time = payload.get("reservation_time") or ""

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        when = f" for {res_date} {res_time}".rstrip() if (res_date or res_time) else ""
        title = f"Booking cancelled: {customer_name}"
        body = f"Party of {party_size}{when} — the table is free again." if party_size \
            else f"A reservation{when} was cancelled — the table is free again."
        _fan_out(db, restaurant, EventType.RESERVATION_CANCELLED, title, body, "reservations",
                 exclude_user_id=payload.get("actor_user_id"))
    except Exception as exc:
        logger.error(f"[PushNotifier] reservation_cancelled failed: {exc}")
    finally:
        db.close()


def _on_purchase_order_approved(payload: dict) -> None:
    """A PO was approved and sent to the supplier — the receiving side now
    knows a delivery is inbound to expect and reconcile against."""
    restaurant_id = payload.get("restaurant_id")
    po_id = payload.get("po_id")
    item_name = payload.get("item_name", "An item")
    quantity = payload.get("quantity", 0)
    unit = payload.get("unit", "")
    supplier_name = payload.get("supplier_name", "")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Delivery inbound: {item_name}"
        body = f"{quantity}{unit} of {item_name} from {supplier_name} is on its way — reconcile on receipt." if supplier_name \
            else f"{quantity}{unit} of {item_name} is on its way — reconcile on receipt."
        _fan_out(db, restaurant, EventType.PURCHASE_ORDER_APPROVED, title, body, "purchasing")
    except Exception as exc:
        logger.error(f"[PushNotifier] purchase_order_approved failed: {exc}")
    finally:
        db.close()


def _on_inventory_adjustment_flagged(payload: dict) -> None:
    """A manual downward stock adjustment (waste/loss) — the shrinkage signal.
    Goes to custody oversight (Owner/Mgr/Controller); the actor who made the
    entry is excluded (the point is that *others* see it)."""
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "An item")
    quantity = payload.get("quantity", 0)
    unit = payload.get("unit", "")
    reason = (payload.get("reason") or "").strip() or "Manual adjustment"
    value_cents = payload.get("value_cents", 0)
    performed_by = payload.get("performed_by", "someone")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        value_note = f" (~KES {value_cents // 100:,})" if value_cents else ""
        title = f"Stock written off: {item_name}"
        body = f"-{quantity}{unit} of {item_name}{value_note} by {performed_by} — reason: {reason}."
        _fan_out(db, restaurant, EventType.INVENTORY_ADJUSTMENT_FLAGGED, title, body, "inventory",
                 exclude_user_id=payload.get("actor_user_id"))
    except Exception as exc:
        logger.error(f"[PushNotifier] inventory_adjustment_flagged failed: {exc}")
    finally:
        db.close()


def _on_order_created(payload: dict) -> None:
    """An online order landed with no staff involved — the kitchen needs to
    cook it. Only the public/online path emits this (routers/orders.py)."""
    restaurant_id = payload.get("restaurant_id")
    order_id = payload.get("order_id")
    customer_name = payload.get("customer_name") or ""
    total_cents = payload.get("total_cents", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        who = f" from {customer_name}" if customer_name else ""
        total_note = f" — KES {total_cents // 100:,}" if total_cents else ""
        title = f"New online order: #{order_id}" if order_id else "New online order"
        body = f"An online order{who} just came in{total_note}. Start preparing it."
        _fan_out(db, restaurant, EventType.ORDER_CREATED, title, body, "orders")
    except Exception as exc:
        logger.error(f"[PushNotifier] order_created failed: {exc}")
    finally:
        db.close()


def _on_supplier_reliability_dropped(payload: dict) -> None:
    """A supplier's reliability score crossed into "watch" territory — reaches
    the procurement oversight tiers so it can be acted on before it bites."""
    restaurant_id = payload.get("restaurant_id")
    supplier_name = payload.get("supplier_name", "A supplier")
    score = payload.get("reliability_score", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Supplier reliability dropping: {supplier_name}"
        body = f"{supplier_name}'s reliability is down to {score}% after repeated late deliveries — consider an alternative."
        _fan_out(db, restaurant, EventType.SUPPLIER_RELIABILITY_DROPPED, title, body, "purchasing")
    except Exception as exc:
        logger.error(f"[PushNotifier] supplier_reliability_dropped failed: {exc}")
    finally:
        db.close()


def _on_price_changed(payload: dict) -> None:
    """A menu price was edited by hand — POS staff quoting from memory need to
    know, the same reason recommendation.approved notifies them. Actor
    (whoever made the edit) excluded."""
    restaurant_id = payload.get("restaurant_id")
    item_name = payload.get("item_name", "A menu item")
    old_price = payload.get("old_price", 0)
    new_price = payload.get("new_price", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Price updated: {item_name}"
        body = f"KES {old_price // 100:,} -> KES {new_price // 100:,} (set by hand)."
        _fan_out(db, restaurant, EventType.PRICE_CHANGED, title, body, "menu",
                 exclude_user_id=payload.get("actor_user_id"))
    except Exception as exc:
        logger.error(f"[PushNotifier] price_changed failed: {exc}")
    finally:
        db.close()


def _on_strategy_review_generated(payload: dict) -> None:
    """A weekly unattended strategist review (main.py's strategist_review job)
    just produced a headline — nudge the owner/manager to read it. One
    summary per run (see the emit site)."""
    restaurant_id = payload.get("restaurant_id")
    headline = (payload.get("headline") or "").strip()
    if not headline:
        return

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = "Weekly strategy review ready"
        body = headline
        # Was "ai-ops" (tech-debt-register.md D15) — that domain is the cost/
        # token/reliability metrics page (GET /ai/usage), which never rendered
        # a headline/steps/risks at all. "ai" is the actual StrategyAgent page.
        _fan_out(db, restaurant, EventType.STRATEGY_REVIEW_GENERATED, title, body, "ai")
    except Exception as exc:
        logger.error(f"[PushNotifier] strategy_review_generated failed: {exc}")
    finally:
        db.close()


def _on_recommendation_generated(payload: dict) -> None:
    """A batch of AI pricing recommendations was just generated — nudge the
    approver to review them. One summary per run (see the emit site)."""
    restaurant_id = payload.get("restaurant_id")
    count = payload.get("count", 0)
    if not count:
        return

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"{count} pricing recommendation{'s' if count != 1 else ''} ready"
        body = f"The pricing agent has {count} new recommendation{'s' if count != 1 else ''} awaiting your review."
        _fan_out(db, restaurant, EventType.RECOMMENDATION_GENERATED, title, body, "menu")
    except Exception as exc:
        logger.error(f"[PushNotifier] recommendation_generated failed: {exc}")
    finally:
        db.close()


def _on_kitchen_incident_logged(payload: dict) -> None:
    """A remake or quality issue was logged — oversight tiers should see the
    pattern building. Actor (the reporter) excluded."""
    restaurant_id = payload.get("restaurant_id")
    incident_type = (payload.get("incident_type") or "other").replace("_", " ")
    reason = (payload.get("reason") or "").strip()
    order_id = payload.get("order_id")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        where = f" (Order #{order_id})" if order_id else ""
        title = f"Kitchen {incident_type}{where}"
        body = reason if reason else f"A {incident_type} was logged in the kitchen."
        _fan_out(db, restaurant, EventType.KITCHEN_INCIDENT_LOGGED, title, body, "orders",
                 exclude_user_id=payload.get("actor_user_id"))
    except Exception as exc:
        logger.error(f"[PushNotifier] kitchen_incident_logged failed: {exc}")
    finally:
        db.close()


def _on_shift_started(payload: dict) -> None:
    """A staff member clocked in — routine, scoped to labor-managing tiers."""
    restaurant_id = payload.get("restaurant_id")
    staff_name = payload.get("staff_name", "A staff member")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Clocked in: {staff_name}"
        body = f"{staff_name} just clocked in."
        _fan_out(db, restaurant, EventType.SHIFT_STARTED, title, body, "staff")
    except Exception as exc:
        logger.error(f"[PushNotifier] shift_started failed: {exc}")
    finally:
        db.close()


def _on_shift_ended(payload: dict) -> None:
    """A staff member clocked out — routine, scoped to labor-managing tiers."""
    restaurant_id = payload.get("restaurant_id")
    staff_name = payload.get("staff_name", "A staff member")
    hours = payload.get("actual_hours")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Clocked out: {staff_name}"
        body = f"{staff_name} worked {hours:.1f}h." if hours is not None else f"{staff_name} just clocked out."
        _fan_out(db, restaurant, EventType.SHIFT_ENDED, title, body, "staff")
    except Exception as exc:
        logger.error(f"[PushNotifier] shift_ended failed: {exc}")
    finally:
        db.close()


def _on_shift_clock_in_flagged(payload: dict) -> None:
    """A clock-in's GPS was farther than the proximity threshold from the
    restaurant — a possible attendance-fraud signal, reaches Owner."""
    restaurant_id = payload.get("restaurant_id")
    staff_name = payload.get("staff_name", "A staff member")
    distance_m = payload.get("distance_meters")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = f"Clock-in location flagged: {staff_name}"
        body = (f"{staff_name} clocked in ~{distance_m:.0f}m from the restaurant." if distance_m is not None
                else f"{staff_name} clocked in from an unexpected location.")
        _fan_out(db, restaurant, EventType.SHIFT_CLOCK_IN_FLAGGED, title, body, "staff")
    except Exception as exc:
        logger.error(f"[PushNotifier] shift_clock_in_flagged failed: {exc}")
    finally:
        db.close()


def _on_suspicious_transaction_flagged(payload: dict) -> None:
    """Sprint 3: at least one fraud pattern flagged for this restaurant in the
    trailing 24h scan. Owner/Controller only (see _EVENT_TARGET_ROLES's
    comment) — the flagged actor could be a Manager-tier staff member."""
    restaurant_id = payload.get("restaurant_id")

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        parts = []
        if payload.get("void_spike_count"):
            parts.append(f"{payload['void_spike_count']} staff cancel/refund spike(s)")
        if payload.get("refund_velocity_count"):
            parts.append(f"{payload['refund_velocity_count']} rapid refund burst(s)")
        if payload.get("payment_mismatch_count"):
            parts.append(f"{payload['payment_mismatch_count']} unmatched M-Pesa payment(s)")
        if payload.get("off_hours_count"):
            parts.append(f"{payload['off_hours_count']} off-hours order change(s)")
        title = "Suspicious transaction activity flagged"
        body = "Flagged in the last 24h: " + ", ".join(parts) + ". Review the Fraud report for evidence."
        _fan_out(db, restaurant, EventType.SUSPICIOUS_TRANSACTION_FLAGGED, title, body, None)
    except Exception as exc:
        logger.error(f"[PushNotifier] suspicious_transaction_flagged failed: {exc}")
    finally:
        db.close()


def _on_cash_reconciliation_flagged(payload: dict) -> None:
    """Sprint 4: a drawer count landed outside tolerance."""
    restaurant_id = payload.get("restaurant_id")
    expected = payload.get("expected_amount_cents", 0)
    counted = payload.get("counted_amount_cents", 0)
    variance = payload.get("variance_cents", 0)

    db = SessionLocal()
    try:
        restaurant = _get_restaurant(db, restaurant_id)
        if not restaurant:
            return
        title = "Cash drawer variance flagged"
        direction = "short" if variance < 0 else "over"
        body = (
            f"Drawer count is {direction} by KES {abs(variance) / 100:.2f} "
            f"(expected KES {expected / 100:.2f}, counted KES {counted / 100:.2f})."
        )
        _fan_out(db, restaurant, EventType.CASH_RECONCILIATION_FLAGGED, title, body, None)
    except Exception as exc:
        logger.error(f"[PushNotifier] cash_reconciliation_flagged failed: {exc}")
    finally:
        db.close()
