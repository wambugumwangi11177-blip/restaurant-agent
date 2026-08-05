"""
backend/notifications.py
─────────────────────────
Owner-alert delivery. In-app first, WhatsApp/SMS as an optional forward.

The inversion this module exists to make: every owner alert used to be raised
like this —

    owner_phone = _owner_phone(restaurant)
    if owner_phone:
        send_whatsapp_message(owner_phone, msg, ...)

— so an alert reached the owner only if (a) a phone number was on file *and*
(b) a Twilio account was configured and working. With neither, which is the
normal state of a deployment before a WhatsApp sender is approved, the system
computed a critical stock warning, wrote an audit log, and then dropped it on
the floor with no trace in the product. The dashboard showed nothing, because
nothing in the dashboard had ever been told.

`deliver()` reverses that dependency: it writes a `Notification` row first,
unconditionally, and only then attempts the phone forward. In-app delivery has
no external dependency, so it cannot silently fail; WhatsApp becomes an
enhancement for owners who aren't at a screen.

Callers should use `deliver()` for anything an owner needs to see. Use
`record()` directly only when a phone forward would be wrong (e.g. an alert
that is purely a dashboard affordance).
"""

import functools
import logging

import models
from time_utils import utcnow

logger = logging.getLogger("notifications")

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"
SEVERITIES = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL)

# ── who may see what ─────────────────────────────────────────────────────────
# Alert bodies are not uniformly safe to show every logged-in user. The morning
# briefing carries yesterday's revenue, week-on-week movement, payment-method
# split and top sellers; the slow-day alert carries revenue too. The dashboard
# already hides Sales/AI/ROI from STAFF (`adminOnly` in the nav) and the backend
# RBAC-gates /ai/* and analytics to ADMIN — so a feed that served those bodies to
# STAFF would route financial data straight around that gate.
#
# The audience is decided by the emitting code, which is the only place that
# knows what it just put in the body, and stored on the row. An earlier version
# inferred it from `category` via an allow-list here; storing it is better
# because the judgement is made once where the context exists, it survives a
# category being reused for something more sensitive, and it is auditable after
# the fact.
AUDIENCE_ALL = "all"        # everyone rostered on this restaurant
AUDIENCE_ADMIN = "admin"    # owners/managers only
AUDIENCES = (AUDIENCE_ALL, AUDIENCE_ADMIN)


def _is_staff(role) -> bool:
    """
    True for the STAFF role. Accepts the enum, its value, or a raw string, since
    callers reach this from an ORM object, a JWT claim, or a test.

    Anything unrecognised is treated as staff (restricted) rather than admin —
    a typo'd or future role must not silently gain access to revenue.
    """
    if role is None:
        return False
    raw = str(getattr(role, "value", role)).strip().lower()
    return raw not in ("admin", "superadmin")

# Max characters kept in a stored body. WhatsApp templates are chatty and the
# feed only ever renders a few lines; the message log (AgentMessage) keeps the
# full text for anything that also went out over a wire.
BODY_LIMIT = 2000


def record(
    db,
    restaurant_id: int,
    title: str,
    body: str = "",
    category: str = "general",
    severity: str = SEVERITY_INFO,
    link: str = "",
    audience: str = AUDIENCE_ADMIN,
) -> "models.Notification | None":
    """
    Write one in-app notification. Returns the row, or None if the write failed.

    `audience` defaults to admin-only. Callers widen it deliberately — a new
    alert whose author forgot to think about who should see it stays restricted.

    Never raises. This is called from event handlers and scheduler jobs whose
    real job is something else (recording a stockout, running a briefing); an
    exception escaping here would abort that work to fail at *telling someone
    about* it — strictly worse than a missing bell entry. Failures are logged.
    """
    if severity not in SEVERITIES:
        severity = SEVERITY_INFO
    if audience not in AUDIENCES:
        audience = AUDIENCE_ADMIN     # fail closed on a typo
    try:
        note = models.Notification(
            restaurant_id=restaurant_id,
            title=title[:255],
            body=(body or "")[:BODY_LIMIT],
            category=category,
            severity=severity,
            link=link,
            audience=audience,
            created_at=utcnow(),
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return note
    except Exception as exc:
        logger.warning("[notifications] failed to record '%s': %s", title, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


def deliver(
    db,
    restaurant,
    title: str,
    body: str,
    category: str = "general",
    severity: str = SEVERITY_INFO,
    link: str = "",
    audience: str = AUDIENCE_ADMIN,
    whatsapp_body: str | None = None,
    message_type: str | None = None,
) -> None:
    """
    Deliver an owner alert: always in-app, then best-effort to WhatsApp/SMS.

    `whatsapp_body` lets the caller send richer/emoji-formatted text over the
    wire than the feed stores — pass None to reuse `body`. `message_type` is the
    label written to the AgentMessage log; defaults to `category` so the two
    stay aligned without every call site repeating itself.

    The phone forward is imported lazily and wrapped: `ai.whatsapp.brain` pulls
    in a large dependency graph, and its failure must never cost the in-app
    delivery that has already been committed above.

    A `restaurant` of None is tolerated, not raised on. Handlers resolve it with
    `.first()` on an id taken from an event payload, so it is None whenever that
    row is missing — and the previous code path (`_owner_phone(restaurant)`)
    returned "" for None and simply skipped the send. Raising here instead would
    abort the caller mid-handler and, in `on_mpesa_payment_failed`, skip the
    audit write that follows — losing the record of a failed payment.
    """
    if restaurant is None:
        logger.warning("[notifications] no restaurant resolved; dropping alert '%s'", title)
        return

    record(db, restaurant.id, title, body, category=category, severity=severity,
           link=link, audience=audience)

    try:
        from ai.whatsapp.brain import send_to_owner

        send_to_owner(db, restaurant, whatsapp_body or body,
                      message_type=message_type or category)
    except Exception as exc:
        # Expected and tolerated whenever no transport is configured — the owner
        # still has the alert in the dashboard.
        logger.info("[notifications] phone forward skipped for '%s': %s", title, exc)


# ── read side ────────────────────────────────────────────────────────────────

def _visible(query, role):
    """Restrict a notification query to what `role` is allowed to see."""
    if _is_staff(role):
        return query.filter(models.Notification.audience == AUDIENCE_ALL)
    return query


def list_for(db, restaurant_id: int, limit: int = 50, unread_only: bool = False,
             role=None) -> list:
    """
    Newest-first feed for one restaurant, filtered to what `role` may see.

    `role=None` means unrestricted and is the right default for internal callers
    (tests, scheduler jobs). Every HTTP path passes the caller's real role.
    """
    query = db.query(models.Notification).filter(
        models.Notification.restaurant_id == restaurant_id
    )
    query = _visible(query, role)
    if unread_only:
        query = query.filter(models.Notification.read_at.is_(None))
    return query.order_by(models.Notification.created_at.desc()).limit(limit).all()


def unread_count(db, restaurant_id: int, role=None) -> int:
    """Unread badge count — counts only what `role` may actually open."""
    query = db.query(models.Notification).filter(
        models.Notification.restaurant_id == restaurant_id,
        models.Notification.read_at.is_(None),
    )
    return _visible(query, role).count()


def mark_read(db, restaurant_id: int, notification_id: int, role=None) -> bool:
    """
    Mark one notification read. Returns False if it doesn't exist, belongs to
    another restaurant, *or* is outside what `role` may see — all three are
    indistinguishable to the caller, so this can neither cross the tenant
    boundary nor be used to probe for the existence of a restricted alert.
    """
    query = db.query(models.Notification).filter(
        models.Notification.id == notification_id,
        models.Notification.restaurant_id == restaurant_id,
    )
    note = _visible(query, role).first()
    if not note:
        return False
    if note.read_at is None:
        note.read_at = utcnow()
        db.commit()
    return True


def mark_all_read(db, restaurant_id: int, role=None) -> int:
    """
    Mark read every unread notification this role can see; returns how many.

    Scoped by role so a STAFF "mark all read" cannot silently acknowledge — and
    thereby hide from the owner — alerts that STAFF was never shown.
    """
    visible_ids = [
        n.id for n in _visible(
            db.query(models.Notification).filter(
                models.Notification.restaurant_id == restaurant_id,
                models.Notification.read_at.is_(None),
            ),
            role,
        ).all()
    ]
    if not visible_ids:
        return 0
    updated = (
        db.query(models.Notification)
        .filter(models.Notification.id.in_(visible_ids))
        .update({models.Notification.read_at: utcnow()}, synchronize_session=False)
    )
    db.commit()
    return updated


# ─────────────────────────────────────────────────────────────────────────────
# ACTIVITY FEED — the ordinary running of the restaurant
# ─────────────────────────────────────────────────────────────────────────────
# Everything above is an *alert*: something is wrong and someone must act. The
# helpers below record the routine operational events (an order placed, a table
# booked, stock received) so the feed is a complete picture of what the software
# did, not only of what went wrong.
#
# Three deliberate properties:
#
#   • record(), never deliver(). These must not page anyone's phone — a WhatsApp
#     message per order would be unusable and expensive. In-app only.
#   • SEVERITY_INFO throughout, so routine traffic stays visually distinct from
#     the warnings and criticals it would otherwise bury.
#   • Best-effort and non-blocking. record() already swallows its own failures,
#     so a notification problem can never fail the order it describes.
#
# Volume warning: a busy site does hundreds of orders a day and each one lands
# here. That is the intended behaviour ("everything happening should be
# notified"), but it means the bell is an activity log, not a to-do list. If it
# becomes noisy, the fix is per-category muting — the `category` column exists
# for exactly that — not removing the events.

def _never_fails(fn):
    """
    Make an activity helper incapable of breaking the thing it describes.

    `record()` already swallows *database* failures, but these helpers also
    format titles from ORM attributes — a None unit, a missing relationship, an
    unexpected enum — and that formatting runs inside the request that just took
    an order. Without this, a bug in a notification string returns 500 to the POS
    and the sale is lost. The order is the product; the bell entry describing it
    is not, so every failure here is logged and swallowed.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logger.warning("[notifications] activity helper %s failed: %s", fn.__name__, exc)
            return None
    return wrapper


def _money(cents: int | None) -> str:
    """KES from integer cents, matching how the UI renders money."""
    return f"KES {(cents or 0) // 100:,}"


@_never_fails
def order_created(db, restaurant_id: int, order, item_count: int, source: str = "POS") -> None:
    record(
        db, restaurant_id,
        title=f"New order #{order.id} — {_money(order.total)}",
        body=f"{item_count} item(s) · {source}",
        category="order_created", severity=SEVERITY_INFO,
        link="/dashboard/orders", audience=AUDIENCE_ALL,
    )


@_never_fails
def order_status_changed(db, restaurant_id: int, order, new_status: str) -> None:
    # Cancellations are the one status change worth more than a glance, so they
    # carry warning severity while the rest of the lifecycle stays informational.
    cancelled = new_status.lower() == "cancelled"
    record(
        db, restaurant_id,
        title=f"Order #{order.id} {new_status.lower()}",
        body=_money(order.total),
        category="order_cancelled" if cancelled else "order_status",
        severity=SEVERITY_WARNING if cancelled else SEVERITY_INFO,
        link="/dashboard/orders", audience=AUDIENCE_ALL,
    )


@_never_fails
def order_paid(db, restaurant_id: int, order, method: str) -> None:
    record(
        db, restaurant_id,
        title=f"Payment received — order #{order.id}",
        body=f"{_money(order.total)} via {method}",
        category="order_paid", severity=SEVERITY_INFO,
        link="/dashboard/orders", audience=AUDIENCE_ALL,
    )


@_never_fails
def reservation_created(db, restaurant_id: int, reservation) -> None:
    when = reservation.reservation_date.isoformat() if reservation.reservation_date else "?"
    time_str = reservation.reservation_time.strftime("%H:%M") if reservation.reservation_time else ""
    record(
        db, restaurant_id,
        title=f"Booking: {reservation.customer_name} · {reservation.party_size} pax",
        body=f"{when} {time_str}".strip(),
        category="reservation_created", severity=SEVERITY_INFO,
        link="/dashboard/reservations", audience=AUDIENCE_ALL,
    )


@_never_fails
def reservation_status_changed(db, restaurant_id: int, reservation, new_status: str) -> None:
    disruptive = new_status.lower() in ("cancelled", "no_show")
    record(
        db, restaurant_id,
        title=f"Booking {new_status.lower()}: {reservation.customer_name}",
        body=f"{reservation.party_size} pax",
        category="reservation_status",
        severity=SEVERITY_WARNING if disruptive else SEVERITY_INFO,
        link="/dashboard/reservations", audience=AUDIENCE_ALL,
    )


@_never_fails
def stock_received(db, restaurant_id: int, item, quantity: float) -> None:
    record(
        db, restaurant_id,
        title=f"Stock received: {item.item_name}",
        body=f"+{quantity:g} {item.unit or ''} · now {item.quantity:g}".strip(),
        category="stock_received", severity=SEVERITY_INFO,
        link="/dashboard/inventory", audience=AUDIENCE_ALL,
    )


@_never_fails
def stock_adjusted(db, restaurant_id: int, item, delta: float, reason: str) -> None:
    # Waste and breakage are a cost line, so an adjustment is worth a warning
    # even though it is a routine action — it is the one activity event an owner
    # is likely to want to review.
    record(
        db, restaurant_id,
        title=f"Stock adjusted: {item.item_name} ({delta:+g})",
        body=f"Reason: {reason or 'not given'} · now {item.quantity:g} {item.unit or ''}".strip(),
        category="stock_adjusted", severity=SEVERITY_WARNING,
        link="/dashboard/inventory", audience=AUDIENCE_ALL,
    )


@_never_fails
def menu_changed(db, restaurant_id: int, item_name: str, what: str) -> None:
    # Admin-only: menu edits are pricing decisions, and price is gated to ADMIN
    # everywhere else in the app.
    record(
        db, restaurant_id,
        title=f"Menu {what}: {item_name}",
        body="",
        category="menu_changed", severity=SEVERITY_INFO,
        link="/dashboard/menu", audience=AUDIENCE_ADMIN,
    )
