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

from database import SessionLocal
import models
from events.bus import subscribe, EventType
from ai.notify import notify_users
from routers.deps import get_staff_users_for_restaurant

logger = logging.getLogger("ai.orchestrator.push_notifier")

StaffRole = models.StaffRole

# Who gets notified for each event. Tunable — this is the single source of
# truth for routing, kept as one visible table rather than scattered
# per-handler literals. Does not need to match the dashboard nav's per-role
# `access` matrix exactly (see _split_by_nav_access below for the one place
# that distinction matters: the notification's deep link).
_EVENT_TARGET_ROLES: dict[EventType, list[StaffRole]] = {
    EventType.STOCK_CRITICAL:             [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER, StaffRole.STOCKKEEPER],
    EventType.STOCK_DEPLETED:             [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER, StaffRole.STOCKKEEPER],
    EventType.STOCK_TRANSFER_DISCREPANCY: [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    EventType.STOCK_VARIANCE_FLAGGED:     [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    EventType.STOCK_COUNT_DISCREPANCY:    [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    EventType.PURCHASE_ORDER_LATE:        [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.CONTROLLER],
    EventType.RESERVATION_NO_SHOW:        [StaffRole.OWNER, StaffRole.MANAGER, StaffRole.SUPERVISOR, StaffRole.WAITER],
    EventType.MPESA_PAYMENT_FAILED:       [StaffRole.OWNER, StaffRole.MANAGER],
    EventType.AGENT_FAILED:               [StaffRole.OWNER],
}

# Roles that DO have dashboard nav access to a given deep-link route today
# (frontend/src/app/dashboard/layout.tsx's navItems.access — OWNER is
# excluded from every set here because Owner accounts are role="admin" and
# bypass the nav matrix entirely, so a deep link always works for them).
# Any target role NOT in the matching set below falls back to "/dashboard"
# instead of a link that would 403/blank for them (e.g. MANAGER currently
# has no Stock nav access at all, even though Manager is a valid alert
# target — a pre-existing nav-matrix gap, not something this module should
# silently paper over by changing the matrix).
_INVENTORY_NAV_ROLES = {StaffRole.CONTROLLER, StaffRole.STOCKKEEPER}
_PURCHASING_NAV_ROLES = {StaffRole.MANAGER, StaffRole.CONTROLLER, StaffRole.STOCKKEEPER}
_RESERVATIONS_NAV_ROLES = {StaffRole.SUPERVISOR, StaffRole.WAITER}


def register_push_handlers() -> None:
    """Register all push/in-app handlers on the event bus. Called once from
    main.py on startup, right after executive.py's register_all_handlers()."""
    subscribe(EventType.STOCK_CRITICAL, _on_stock_critical)
    subscribe(EventType.STOCK_DEPLETED, _on_stock_depleted)
    subscribe(EventType.STOCK_TRANSFER_DISCREPANCY, _on_stock_transfer_discrepancy)
    subscribe(EventType.STOCK_VARIANCE_FLAGGED, _on_stock_variance_flagged)
    subscribe(EventType.STOCK_COUNT_DISCREPANCY, _on_stock_count_discrepancy)
    subscribe(EventType.PURCHASE_ORDER_LATE, _on_purchase_order_late)
    subscribe(EventType.RESERVATION_NO_SHOW, _on_reservation_no_show)
    subscribe(EventType.MPESA_PAYMENT_FAILED, _on_mpesa_payment_failed)
    subscribe(EventType.AGENT_FAILED, _on_agent_failed)

    logger.info("[PushNotifier] All handlers registered")


# ── Shared helper ────────────────────────────────────────────────────────

def _fan_out(db, restaurant, event_type: EventType, title: str, body: str,
             nav_ok_roles: set | None, deep_link: str) -> None:
    """Notify every role targeted by event_type. Roles in nav_ok_roles (or,
    if nav_ok_roles is None, every targeted role) get deep_link; everyone
    else gets the safe "/dashboard" fallback. OWNER always gets deep_link
    (role="admin" bypasses the nav matrix, so it always resolves for them)."""
    roles = _EVENT_TARGET_ROLES.get(event_type, [])
    if not roles:
        return

    if nav_ok_roles is None:
        ok_roles = set(roles)
    else:
        ok_roles = ({StaffRole.OWNER} | nav_ok_roles) & set(roles)
    fallback_roles = [r for r in roles if r not in ok_roles]

    if ok_roles:
        users = get_staff_users_for_restaurant(db, restaurant, list(ok_roles))
        notify_users(db, [u.id for u in users], title, body, event_type.value, deep_link)
    if fallback_roles:
        users = get_staff_users_for_restaurant(db, restaurant, fallback_roles)
        notify_users(db, [u.id for u in users], title, body, event_type.value, "/dashboard")


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
        _fan_out(db, restaurant, EventType.STOCK_CRITICAL, title, body,
                 _INVENTORY_NAV_ROLES, "/dashboard/inventory")
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
        _fan_out(db, restaurant, EventType.STOCK_DEPLETED, title, body,
                 _INVENTORY_NAV_ROLES, "/dashboard/inventory")
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
        _fan_out(db, restaurant, EventType.STOCK_TRANSFER_DISCREPANCY, title, body,
                 _INVENTORY_NAV_ROLES, "/dashboard/inventory")
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
        _fan_out(db, restaurant, EventType.STOCK_VARIANCE_FLAGGED, title, body,
                 _INVENTORY_NAV_ROLES, "/dashboard/inventory")
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
        _fan_out(db, restaurant, EventType.STOCK_COUNT_DISCREPANCY, title, body,
                 _INVENTORY_NAV_ROLES, "/dashboard/inventory")
    except Exception as exc:
        logger.error(f"[PushNotifier] stock_count_discrepancy failed: {exc}")
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
        _fan_out(db, restaurant, EventType.PURCHASE_ORDER_LATE, title, body,
                 _PURCHASING_NAV_ROLES, "/dashboard/purchasing")
    except Exception as exc:
        logger.error(f"[PushNotifier] purchase_order_late failed: {exc}")
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
        _fan_out(db, restaurant, EventType.RESERVATION_NO_SHOW, title, body,
                 _RESERVATIONS_NAV_ROLES, "/dashboard/reservations")
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
        # Neither OWNER-nav-bypass-aside role here (MANAGER) has Orders nav
        # access today — no page both roles can reliably open, so everyone
        # lands on /dashboard rather than a route that 403s for Manager.
        _fan_out(db, restaurant, EventType.MPESA_PAYMENT_FAILED, title, body, set(), "/dashboard")
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
        _fan_out(db, restaurant, EventType.AGENT_FAILED, title, body, None, "/dashboard/ai-ops")
    except Exception as exc:
        logger.error(f"[PushNotifier] agent_failed failed: {exc}")
    finally:
        db.close()
