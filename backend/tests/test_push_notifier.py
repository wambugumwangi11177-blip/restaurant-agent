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
    """MANAGER is a valid target for STOCK_CRITICAL but has no nav access to
    /dashboard/inventory (frontend layout.tsx's access matrix) — the
    notification must not link them to a page they can't open."""
    from ai.orchestrator.push_notifier import _on_stock_critical

    tenant, restaurant = _make_restaurant(db_session, "n5")
    manager = _make_user(db_session, tenant, "n5mgr", staff_role=models.StaffRole.MANAGER)
    controller = _make_user(db_session, tenant, "n5ctrl", staff_role=models.StaffRole.CONTROLLER)

    _on_stock_critical({
        "restaurant_id": restaurant.id, "item_name": "Rice", "hours_remaining": 1,
    })

    mgr_notif = db_session.query(models.Notification).filter(models.Notification.user_id == manager.id).first()
    ctrl_notif = db_session.query(models.Notification).filter(models.Notification.user_id == controller.id).first()
    assert mgr_notif.url == "/dashboard"
    assert ctrl_notif.url == "/dashboard/inventory"


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
