"""
ai/notify.py + ai/orchestrator/push_notifier.py — the staff notification
channel built to work with zero external account (Twilio is unfunded).

Covers: wiring (register_push_handlers actually subscribes every routed
event), the in-app feed always gets written regardless of push config,
role-based fan-out only reaches the roles a given event targets (not
everyone), and push delivery itself (webhook payload shape, dead-subscription
pruning on 404/410) via a monkeypatched pywebpush.webpush — no real network
call, matching how test_event_orchestration.py stubs send_whatsapp_message.
"""

import auth
import models
from events.bus import EventType, clear_handlers, _handlers
from ai.orchestrator.push_notifier import register_push_handlers, _EVENT_TARGET_ROLES
from ai import notify as notify_mod


def _make_user(db_session, tenant, suffix, role=models.Role.STAFF, staff_role=None, is_active=True):
    user = models.User(
        tenant_id=tenant.id,
        email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=role,
        staff_role=staff_role,
        is_active=is_active,
        token_version=0,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _make_restaurant(db_session, suffix):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    db_session.refresh(restaurant)
    return tenant, restaurant


# ── Wiring ──────────────────────────────────────────────────────────────────

def test_register_push_handlers_subscribes_every_routed_event(db_session):
    clear_handlers()
    register_push_handlers()
    for event_type in _EVENT_TARGET_ROLES:
        assert _handlers.get(event_type.value), f"{event_type} has no push handler subscribed"


# ── In-app feed: always written, independent of push config ────────────────

def test_notify_user_writes_notification_row_even_without_vapid(db_session):
    tenant, restaurant = _make_restaurant(db_session, "n1")
    user = _make_user(db_session, tenant, "n1", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)

    # VAPID isn't configured in the test environment (no env vars set) —
    # notify_user must still persist the in-app row and must not raise.
    notif = notify_mod.notify_user(
        db_session, user.id, "Test title", "Test body", "test.event", url="/dashboard"
    )

    assert notif.id is not None
    row = db_session.query(models.Notification).filter(models.Notification.user_id == user.id).first()
    assert row is not None
    assert row.title == "Test title"
    assert row.is_read is False


def test_notify_users_fans_out_to_every_recipient(db_session):
    tenant, restaurant = _make_restaurant(db_session, "n2")
    u1 = _make_user(db_session, tenant, "n2a", staff_role=models.StaffRole.MANAGER)
    u2 = _make_user(db_session, tenant, "n2b", staff_role=models.StaffRole.CONTROLLER)

    notify_mod.notify_users(db_session, [u1.id, u2.id], "Title", "Body", "test.event")

    assert db_session.query(models.Notification).filter(models.Notification.user_id == u1.id).count() == 1
    assert db_session.query(models.Notification).filter(models.Notification.user_id == u2.id).count() == 1


# ── Push dispatch: monkeypatched webpush, no real network call ─────────────

def test_dispatch_push_sends_to_every_subscription_and_prunes_dead_ones(db_session, monkeypatch):
    tenant, restaurant = _make_restaurant(db_session, "n3")
    user = _make_user(db_session, tenant, "n3", staff_role=models.StaffRole.OWNER)

    alive = models.PushSubscription(
        user_id=user.id, endpoint="https://push.example/alive", p256dh="p1", auth="a1",
    )
    dead = models.PushSubscription(
        user_id=user.id, endpoint="https://push.example/dead", p256dh="p2", auth="a2",
    )
    db_session.add_all([alive, dead])
    db_session.commit()

    monkeypatch.setattr(notify_mod, "_VAPID_CONFIGURED", True)
    monkeypatch.setattr(notify_mod, "VAPID_PRIVATE_KEY", "fake-priv")
    monkeypatch.setattr(notify_mod, "VAPID_CLAIM_EMAIL", "owner@example.com")

    sent = []

    class FakeWebPushException(Exception):
        def __init__(self, response=None):
            super().__init__("dead subscription")
            self.response = response

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    def fake_webpush(subscription_info, data, vapid_private_key, vapid_claims):
        sent.append(subscription_info["endpoint"])
        if subscription_info["endpoint"].endswith("/dead"):
            raise FakeWebPushException(response=FakeResponse(410))

    import pywebpush
    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)
    monkeypatch.setattr(pywebpush, "WebPushException", FakeWebPushException)

    notify_mod._dispatch_push(db_session, user.id, "Title", "Body", "/dashboard")

    assert set(sent) == {"https://push.example/alive", "https://push.example/dead"}
    remaining = db_session.query(models.PushSubscription).filter(
        models.PushSubscription.user_id == user.id
    ).all()
    assert [s.endpoint for s in remaining] == ["https://push.example/alive"]


# ── Role-based fan-out: only targeted roles get notified ───────────────────

def test_on_stock_critical_notifies_only_targeted_roles(db_session):
    from ai.orchestrator.push_notifier import _on_stock_critical

    tenant, restaurant = _make_restaurant(db_session, "n4")
    owner = _make_user(db_session, tenant, "n4owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    stockkeeper = _make_user(db_session, tenant, "n4sk", staff_role=models.StaffRole.STOCKKEEPER)
    waiter = _make_user(db_session, tenant, "n4w", staff_role=models.StaffRole.WAITER)  # NOT targeted

    _on_stock_critical({
        "restaurant_id": restaurant.id, "item_name": "Tomatoes",
        "hours_remaining": 2, "inventory_item_id": 1,
    })

    assert db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 1
    assert db_session.query(models.Notification).filter(models.Notification.user_id == stockkeeper.id).count() == 1
    assert db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).count() == 0


def test_on_stock_critical_gives_manager_a_safe_fallback_url(db_session):
    """MANAGER is a valid target for STOCK_CRITICAL. Every staff_role tier now
    has its own /staff/<tier>/* route tree (dashboard/layout.tsx redirects any
    staff_role account off /dashboard/* entirely), so the notification must
    link each recipient to *their own* tier's inventory page, not a single
    hardcoded /dashboard/inventory link that would bounce them straight back
    out (2026-07-17 fix, see directive 016's as-built notes)."""
    from ai.orchestrator.push_notifier import _on_stock_critical

    tenant, restaurant = _make_restaurant(db_session, "n5")
    manager = _make_user(db_session, tenant, "n5mgr", staff_role=models.StaffRole.MANAGER)
    controller = _make_user(db_session, tenant, "n5ctrl", staff_role=models.StaffRole.CONTROLLER)

    _on_stock_critical({
        "restaurant_id": restaurant.id, "item_name": "Rice", "hours_remaining": 1,
    })

    mgr_notif = db_session.query(models.Notification).filter(models.Notification.user_id == manager.id).first()
    ctrl_notif = db_session.query(models.Notification).filter(models.Notification.user_id == controller.id).first()
    assert mgr_notif.url == "/staff/manager/inventory"
    assert ctrl_notif.url == "/staff/controller"


def test_on_agent_failed_resolves_restaurant_properly(db_session):
    """Unlike executive.py's WhatsApp handler (which reads OWNER_PHONE env
    var directly and skips the Restaurant lookup), the push handler must
    resolve Restaurant and only notify when it exists."""
    from ai.orchestrator.push_notifier import _on_agent_failed

    tenant, restaurant = _make_restaurant(db_session, "n6")
    owner = _make_user(db_session, tenant, "n6owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)

    _on_agent_failed({"agent_name": "reorder_agent", "error": "boom", "restaurant_id": restaurant.id})
    assert db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 1

    # Unknown restaurant_id: must no-op, not raise.
    _on_agent_failed({"agent_name": "reorder_agent", "error": "boom", "restaurant_id": 999999})
    assert db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 1


# ── Kitchen "pull" requisition (directive 017) — the routine, non-exception
# half of request/fulfil now fires a notification, closing the gap where a
# storekeeper/kitchen had to poll the dashboard to learn a request existed.

def test_on_stock_transfer_requested_notifies_stockkeeper_and_gives_kitchen_link(db_session):
    from ai.orchestrator.push_notifier import _on_stock_transfer_requested

    tenant, restaurant = _make_restaurant(db_session, "n7")
    stockkeeper = _make_user(db_session, tenant, "n7sk", staff_role=models.StaffRole.STOCKKEEPER)
    supervisor = _make_user(db_session, tenant, "n7sup", staff_role=models.StaffRole.SUPERVISOR)
    kitchen = _make_user(db_session, tenant, "n7k", staff_role=models.StaffRole.KITCHEN)  # NOT targeted

    _on_stock_transfer_requested({
        "restaurant_id": restaurant.id, "transfer_id": 1, "item_name": "Chicken",
        "unit": "kg", "from_location": "store", "to_location": "kitchen",
    })

    sk_notif = db_session.query(models.Notification).filter(models.Notification.user_id == stockkeeper.id).first()
    assert sk_notif is not None
    assert sk_notif.url == "/staff/stockkeeper"
    sup_notif = db_session.query(models.Notification).filter(models.Notification.user_id == supervisor.id).first()
    assert sup_notif is not None  # Supervisor "sees the log" (directive 017)
    assert db_session.query(models.Notification).filter(models.Notification.user_id == kitchen.id).count() == 0


def test_on_stock_transfer_fulfilled_notifies_kitchen(db_session):
    from ai.orchestrator.push_notifier import _on_stock_transfer_fulfilled

    tenant, restaurant = _make_restaurant(db_session, "n8")
    kitchen = _make_user(db_session, tenant, "n8k", staff_role=models.StaffRole.KITCHEN)

    _on_stock_transfer_fulfilled({
        "restaurant_id": restaurant.id, "transfer_id": 1, "item_name": "Chicken",
        "quantity": 5, "unit": "kg", "from_location": "store", "to_location": "kitchen",
    })

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == kitchen.id).first()
    assert notif is not None
    assert notif.url == "/staff/kitchen/stock"


def test_on_purchase_order_created_reaches_supervisor(db_session):
    """Supervisor is an approver (routers/purchase_orders.py's _CAN_APPROVE)
    but previously had no notification path at all for a drafted PO —
    executive.py's WhatsApp handler only ever reaches the Owner's phone."""
    from ai.orchestrator.push_notifier import _on_purchase_order_created

    tenant, restaurant = _make_restaurant(db_session, "n9")
    supervisor = _make_user(db_session, tenant, "n9sup", staff_role=models.StaffRole.SUPERVISOR)

    _on_purchase_order_created({
        "restaurant_id": restaurant.id, "po_id": 1, "item_name": "Rice",
        "quantity": 20, "unit": "kg", "supplier_name": "Acme Foods",
    })

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == supervisor.id).first()
    assert notif is not None
    assert notif.url == "/staff/supervisor/purchasing"


# ── 2026-07-17 notification-coverage audit ─────────────────────────────────

def test_on_order_paid_only_notifies_for_mpesa_webhook_path(db_session):
    """The POS 'mark as paid' emit has no mpesa_reference — must be a no-op
    here (it's the staff member's own synchronous action, not a signal)."""
    from ai.orchestrator.push_notifier import _on_order_paid

    tenant, restaurant = _make_restaurant(db_session, "n10")
    waiter = _make_user(db_session, tenant, "n10w", staff_role=models.StaffRole.WAITER)

    _on_order_paid({
        "restaurant_id": restaurant.id, "order_id": 1, "amount_cents": 5000,
        "payment_method": "cash",  # POS path: no mpesa_reference
    })
    assert db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).count() == 0

    _on_order_paid({
        "restaurant_id": restaurant.id, "order_id": 2, "amount_cents": 5000,
        "mpesa_reference": "ABC123",
    })
    notif = db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).first()
    assert notif is not None
    assert notif.url == "/staff/waiter/orders"


def test_on_purchase_order_delivered_reaches_stockkeeper(db_session):
    from ai.orchestrator.push_notifier import _on_purchase_order_delivered

    tenant, restaurant = _make_restaurant(db_session, "n11")
    stockkeeper = _make_user(db_session, tenant, "n11sk", staff_role=models.StaffRole.STOCKKEEPER)

    _on_purchase_order_delivered({
        "restaurant_id": restaurant.id, "po_id": 1, "item_name": "Rice",
        "quantity_ordered": 20, "quantity_received": 15, "unit": "kg",
    })
    notif = db_session.query(models.Notification).filter(models.Notification.user_id == stockkeeper.id).first()
    assert notif is not None
    assert notif.url == "/staff/stockkeeper/purchasing"


def test_on_recommendation_approved_notifies_waiter_with_menu_link(db_session):
    from ai.orchestrator.push_notifier import _on_recommendation_approved

    tenant, restaurant = _make_restaurant(db_session, "n12")
    waiter = _make_user(db_session, tenant, "n12w", staff_role=models.StaffRole.WAITER)

    _on_recommendation_approved({
        "restaurant_id": restaurant.id, "item_name": "Chicken Burger",
        "old_price": 50000, "new_price": 55000,
    })
    notif = db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).first()
    assert notif is not None
    assert notif.url == "/staff/waiter/menu"


def test_on_account_locked_reaches_owner_only(db_session):
    from ai.orchestrator.push_notifier import _on_account_locked

    tenant, restaurant = _make_restaurant(db_session, "n13")
    owner = _make_user(db_session, tenant, "n13o", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    manager = _make_user(db_session, tenant, "n13m", staff_role=models.StaffRole.MANAGER)  # NOT targeted

    _on_account_locked({"restaurant_id": restaurant.id, "email": "waiter@e.com", "lockout_minutes": 15})

    owner_notif = db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).first()
    assert owner_notif is not None
    assert owner_notif.url == "/dashboard/staff"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == manager.id).count() == 0


def test_on_staff_role_changed_excludes_the_actor(db_session):
    """An Owner granting a role themselves shouldn't be told about their own
    action — exclude_user_id must actually filter them out of the fan-out."""
    from ai.orchestrator.push_notifier import _on_staff_role_changed

    tenant, restaurant = _make_restaurant(db_session, "n14")
    owner = _make_user(db_session, tenant, "n14o", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)

    _on_staff_role_changed({
        "restaurant_id": restaurant.id, "staff_name": "Jane", "before_role": "waiter",
        "after_role": "supervisor", "changed_by": owner.email, "changed_by_user_id": owner.id,
    })
    assert db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 0

    # A different actor (e.g. a Manager granting the role) must NOT be excluded.
    _on_staff_role_changed({
        "restaurant_id": restaurant.id, "staff_name": "Jane", "before_role": "waiter",
        "after_role": "supervisor", "changed_by": "manager@e.com", "changed_by_user_id": 999999,
    })
    owner_notif = db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).first()
    assert owner_notif is not None
    assert owner_notif.url == "/dashboard/staff"


def test_on_staff_deactivated_excludes_the_actor(db_session):
    from ai.orchestrator.push_notifier import _on_staff_deactivated

    tenant, restaurant = _make_restaurant(db_session, "n15")
    owner = _make_user(db_session, tenant, "n15o", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)

    _on_staff_deactivated({
        "restaurant_id": restaurant.id, "staff_name": "Jane",
        "deactivated_by": owner.email, "deactivated_by_user_id": owner.id,
    })
    assert db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 0

    _on_staff_deactivated({
        "restaurant_id": restaurant.id, "staff_name": "Jane",
        "deactivated_by": "manager@e.com", "deactivated_by_user_id": 999999,
    })
    notif = db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).first()
    assert notif is not None
    assert notif.url == "/dashboard/staff"


def test_on_staff_reactivated_reaches_owner_and_excludes_actor(db_session):
    from ai.orchestrator.push_notifier import _on_staff_reactivated

    tenant, restaurant = _make_restaurant(db_session, "n28")
    owner = _make_user(db_session, tenant, "n28o", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)

    # Owner reactivating themselves-as-actor is excluded.
    _on_staff_reactivated({
        "restaurant_id": restaurant.id, "staff_name": "Jane",
        "reactivated_by": owner.email, "reactivated_by_user_id": owner.id,
    })
    assert db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 0

    # A different actor (e.g. a Manager) does not exclude the Owner.
    _on_staff_reactivated({
        "restaurant_id": restaurant.id, "staff_name": "Jane",
        "reactivated_by": "manager@e.com", "reactivated_by_user_id": 999999,
    })
    notif = db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).first()
    assert notif is not None
    assert notif.url == "/dashboard/staff"


def test_on_menu_item_unavailable_reaches_waiter(db_session):
    from ai.orchestrator.push_notifier import _on_menu_item_unavailable

    tenant, restaurant = _make_restaurant(db_session, "n16")
    waiter = _make_user(db_session, tenant, "n16w", staff_role=models.StaffRole.WAITER)
    stockkeeper = _make_user(db_session, tenant, "n16sk", staff_role=models.StaffRole.STOCKKEEPER)  # NOT targeted

    _on_menu_item_unavailable({"restaurant_id": restaurant.id, "item_name": "Chicken Burger"})

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).first()
    assert notif is not None
    assert notif.url == "/staff/waiter/menu"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == stockkeeper.id).count() == 0


# ── 2026-07-18 event-map pass: order/reservation lifecycle + PO approved ────
# These four operational events deliberately do NOT target the Owner (their
# feed is for the exception class, not the live floor). Every one excludes its
# actor.

def test_on_order_ready_reaches_front_of_house_not_owner_or_kitchen(db_session):
    from ai.orchestrator.push_notifier import _on_order_ready

    tenant, restaurant = _make_restaurant(db_session, "n17")
    waiter = _make_user(db_session, tenant, "n17w", staff_role=models.StaffRole.WAITER)
    owner = _make_user(db_session, tenant, "n17o", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)  # NOT targeted
    kitchen = _make_user(db_session, tenant, "n17k", staff_role=models.StaffRole.KITCHEN)  # NOT targeted

    _on_order_ready({"restaurant_id": restaurant.id, "order_id": 7, "table_number": 4})

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).first()
    assert notif is not None
    assert notif.url == "/staff/waiter/orders"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 0
    assert db_session.query(models.Notification).filter(models.Notification.user_id == kitchen.id).count() == 0


def test_on_order_ready_excludes_the_actor(db_session):
    from ai.orchestrator.push_notifier import _on_order_ready

    tenant, restaurant = _make_restaurant(db_session, "n18")
    # A Supervisor who advanced the ticket themselves shouldn't be pinged.
    supervisor = _make_user(db_session, tenant, "n18s", staff_role=models.StaffRole.SUPERVISOR)

    _on_order_ready({"restaurant_id": restaurant.id, "order_id": 1, "actor_user_id": supervisor.id})
    assert db_session.query(models.Notification).filter(models.Notification.user_id == supervisor.id).count() == 0


def test_on_order_cancelled_reaches_kitchen_not_waiter(db_session):
    from ai.orchestrator.push_notifier import _on_order_cancelled

    tenant, restaurant = _make_restaurant(db_session, "n19")
    kitchen = _make_user(db_session, tenant, "n19k", staff_role=models.StaffRole.KITCHEN)
    waiter = _make_user(db_session, tenant, "n19w", staff_role=models.StaffRole.WAITER)  # NOT targeted

    _on_order_cancelled({"restaurant_id": restaurant.id, "order_id": 9, "table_number": 2})

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == kitchen.id).first()
    assert notif is not None
    # Kitchen order events land on the KDS (tier home), where the ticket is
    # actually advanced/stopped — not the read-only /orders list.
    assert notif.url == "/staff/kitchen"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).count() == 0


def test_on_reservation_created_reaches_waiter_not_owner(db_session):
    from ai.orchestrator.push_notifier import _on_reservation_created

    tenant, restaurant = _make_restaurant(db_session, "n20")
    waiter = _make_user(db_session, tenant, "n20w", staff_role=models.StaffRole.WAITER)
    owner = _make_user(db_session, tenant, "n20o", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)  # NOT targeted

    _on_reservation_created({
        "restaurant_id": restaurant.id, "reservation_id": 3, "customer_name": "Jane",
        "party_size": 4, "reservation_date": "2026-07-19", "reservation_time": "19:30",
    })

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).first()
    assert notif is not None
    assert notif.url == "/staff/waiter/reservations"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 0


def test_on_reservation_cancelled_excludes_the_actor(db_session):
    from ai.orchestrator.push_notifier import _on_reservation_cancelled

    tenant, restaurant = _make_restaurant(db_session, "n21")
    waiter = _make_user(db_session, tenant, "n21w", staff_role=models.StaffRole.WAITER)
    supervisor = _make_user(db_session, tenant, "n21s", staff_role=models.StaffRole.SUPERVISOR)

    _on_reservation_cancelled({
        "restaurant_id": restaurant.id, "reservation_id": 3, "customer_name": "Jane",
        "party_size": 2, "actor_user_id": supervisor.id,
    })

    assert db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).count() == 1
    assert db_session.query(models.Notification).filter(models.Notification.user_id == supervisor.id).count() == 0


def test_on_purchase_order_approved_reaches_stockkeeper(db_session):
    from ai.orchestrator.push_notifier import _on_purchase_order_approved

    tenant, restaurant = _make_restaurant(db_session, "n22")
    stockkeeper = _make_user(db_session, tenant, "n22sk", staff_role=models.StaffRole.STOCKKEEPER)
    waiter = _make_user(db_session, tenant, "n22w", staff_role=models.StaffRole.WAITER)  # NOT targeted

    _on_purchase_order_approved({
        "restaurant_id": restaurant.id, "po_id": 5, "item_name": "Rice",
        "quantity": 20, "unit": "kg", "supplier_name": "Acme Foods",
    })

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == stockkeeper.id).first()
    assert notif is not None
    assert notif.url == "/staff/stockkeeper/purchasing"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).count() == 0


def test_on_inventory_adjustment_flagged_reaches_oversight_and_excludes_actor(db_session):
    """A manual write-off goes to custody oversight (Owner/Mgr/Controller) but
    not the actor who entered it, nor the floor tiers."""
    from ai.orchestrator.push_notifier import _on_inventory_adjustment_flagged

    tenant, restaurant = _make_restaurant(db_session, "n23")
    controller = _make_user(db_session, tenant, "n23c", staff_role=models.StaffRole.CONTROLLER)
    manager = _make_user(db_session, tenant, "n23m", staff_role=models.StaffRole.MANAGER)  # the actor
    waiter = _make_user(db_session, tenant, "n23w", staff_role=models.StaffRole.WAITER)  # NOT targeted

    _on_inventory_adjustment_flagged({
        "restaurant_id": restaurant.id, "inventory_item_id": 1, "item_name": "Beef",
        "quantity": 3, "unit": "kg", "reason": "spoilage", "value_cents": 150000,
        "performed_by": manager.email, "actor_user_id": manager.id,
    })

    ctrl = db_session.query(models.Notification).filter(models.Notification.user_id == controller.id).first()
    assert ctrl is not None
    assert ctrl.url == "/staff/controller"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == manager.id).count() == 0
    assert db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).count() == 0


def test_on_order_created_reaches_kitchen(db_session):
    from ai.orchestrator.push_notifier import _on_order_created

    tenant, restaurant = _make_restaurant(db_session, "n24")
    kitchen = _make_user(db_session, tenant, "n24k", staff_role=models.StaffRole.KITCHEN)
    owner = _make_user(db_session, tenant, "n24o", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)  # NOT targeted

    _on_order_created({
        "restaurant_id": restaurant.id, "order_id": 12, "customer_name": "Sam", "total_cents": 80000,
    })

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == kitchen.id).first()
    assert notif is not None
    # New online order → kitchen lands on the KDS to start preparing it.
    assert notif.url == "/staff/kitchen"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == owner.id).count() == 0


def test_on_supplier_reliability_dropped_reaches_controller(db_session):
    from ai.orchestrator.push_notifier import _on_supplier_reliability_dropped

    tenant, restaurant = _make_restaurant(db_session, "n25")
    controller = _make_user(db_session, tenant, "n25c", staff_role=models.StaffRole.CONTROLLER)
    waiter = _make_user(db_session, tenant, "n25w", staff_role=models.StaffRole.WAITER)  # NOT targeted

    _on_supplier_reliability_dropped({
        "restaurant_id": restaurant.id, "supplier_id": 1,
        "supplier_name": "Acme Foods", "reliability_score": 65,
    })

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == controller.id).first()
    assert notif is not None
    assert notif.url == "/staff/controller/purchasing"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).count() == 0


def test_on_price_changed_reaches_waiter_and_excludes_actor(db_session):
    """A hand-edited price is the manual twin of recommendation.approved —
    same POS-facing recipients, minus whoever made the edit."""
    from ai.orchestrator.push_notifier import _on_price_changed

    tenant, restaurant = _make_restaurant(db_session, "n26")
    waiter = _make_user(db_session, tenant, "n26w", staff_role=models.StaffRole.WAITER)
    manager = _make_user(db_session, tenant, "n26m", staff_role=models.StaffRole.MANAGER)  # the actor

    _on_price_changed({
        "restaurant_id": restaurant.id, "menu_item_id": 1, "item_name": "Ugali",
        "old_price": 20000, "new_price": 25000, "actor_user_id": manager.id,
    })

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).first()
    assert notif is not None
    assert notif.url == "/staff/waiter/menu"
    assert db_session.query(models.Notification).filter(models.Notification.user_id == manager.id).count() == 0


def test_on_recommendation_generated_reaches_manager_as_summary(db_session):
    from ai.orchestrator.push_notifier import _on_recommendation_generated

    tenant, restaurant = _make_restaurant(db_session, "n27")
    manager = _make_user(db_session, tenant, "n27m", staff_role=models.StaffRole.MANAGER)
    waiter = _make_user(db_session, tenant, "n27w", staff_role=models.StaffRole.WAITER)  # NOT targeted

    _on_recommendation_generated({"restaurant_id": restaurant.id, "count": 3})

    notif = db_session.query(models.Notification).filter(models.Notification.user_id == manager.id).first()
    assert notif is not None
    assert "3" in notif.title
    assert db_session.query(models.Notification).filter(models.Notification.user_id == waiter.id).count() == 0

    # A zero-count run must be a no-op (guarded at the emit site and the handler).
    _on_recommendation_generated({"restaurant_id": restaurant.id, "count": 0})
    assert db_session.query(models.Notification).filter(models.Notification.user_id == manager.id).count() == 1
