"""
Stock alerting: one owner message per item per cooldown window.

Two defects fixed 2026-07-08 in `brain.run_stock_check`:
  • It emitted STOCK_CRITICAL (whose handler WhatsApps the owner) AND separately
    sent `compose_stock_alert(urgent[0])` itself — two messages, same shortage.
  • It ran every 2h with no dedup, so a persistently low item re-alerted on every
    cycle (up to 7 identical messages a day, per item) until someone restocked.
    Pricing recommendations had had a 7-day cooldown all along.

Fixing the first without the second would have silently *removed* an alert path:
a depleted item with no recent usage scores WARNING (hours_remaining defaults to
999), never enters `urgent`, and so only ever reached the owner via that direct
send. `on_stock_depleted` now notifies too.
"""

from datetime import timedelta

import pytest

import models
from time_utils import utcnow
from events.bus import clear_handlers


def _tenant_id(db) -> int:
    tenant = models.Tenant(name="Stock Alerts Tenant")
    db.add(tenant)
    db.commit()
    return tenant.id


@pytest.fixture
def stocked(db_session):
    """A restaurant whose 'Chicken' is critically low and actively selling."""
    r = models.Restaurant(id=1, tenant_id=_tenant_id(db_session), name="Test Bistro", address="x",
                          owner_phone="+254712345678")
    item = models.InventoryItem(
        id=1, restaurant_id=1, item_name="Chicken", quantity=2.0, unit="kg",
        low_stock_threshold=10,
    )
    db_session.add_all([r, item])
    db_session.commit()

    # Recent usage so hours_remaining is small -> severity URGENT.
    for days_ago in range(1, 4):
        db_session.add(models.StockMovement(
            inventory_item_id=1, movement_type=models.StockMovementType.OUT,
            quantity=20.0, created_at=utcnow() - timedelta(days=days_ago),
        ))
    db_session.commit()
    return db_session


def _run_check(db_session, monkeypatch):
    """Run the scheduled stock check with a real handler chain and a spy send."""
    import database
    sent = []
    import ai.whatsapp as whatsapp_mod
    import ai.whatsapp.brain as brain_mod
    monkeypatch.setattr(whatsapp_mod, "send_whatsapp_message",
                        lambda to, msg, **kw: sent.append((to, msg)))
    monkeypatch.setattr(brain_mod, "send_whatsapp_message",
                        lambda to, msg, **kw: sent.append((to, msg)))

    clear_handlers()
    from ai.orchestrator.executive import register_all_handlers
    register_all_handlers()

    # emit_async dispatches on a background thread; run handlers inline so the
    # assertions don't race the scheduler.
    import events.bus as bus
    monkeypatch.setattr(bus, "emit_async", bus.emit)
    monkeypatch.setattr(brain_mod, "utcnow", utcnow)

    # Pin service hours ON so these tests are deterministic. run_stock_check gates
    # merely-urgent (still-in-stock) items behind within_service_hours(), which
    # reads the real wall clock — so before this pin the urgent-path tests below
    # silently failed whenever the suite ran outside 07:00–22:00 EAT. Quiet-hours
    # behaviour is orthogonal to what these tests assert (dedup / cooldown /
    # single-send); depleted-item tests fire regardless of hours anyway.
    monkeypatch.setattr(brain_mod, "within_service_hours", lambda *a, **k: True)

    brain_mod.run_stock_check(database.SessionLocal)
    return sent


def test_critical_item_alerts_owner_exactly_once(stocked, monkeypatch):
    sent = _run_check(stocked, monkeypatch)

    assert len(sent) == 1, f"expected exactly one owner message, got {len(sent)}: {sent}"
    to, msg = sent[0]
    assert to == "+254712345678"
    assert "Chicken" in msg
    # ...and it is the *orchestrated* alert (cross-agent context), not the plain
    # one the direct send used. on_stock_critical resolved the owner from
    # OWNER_PHONE env only, so a restaurant onboarded via the owner_phone column
    # (migration 006) silently got no orchestrated alert at all.
    assert "h of stock remaining" in msg


def test_no_double_send_when_legacy_owner_phone_env_is_also_set(stocked, monkeypatch):
    """
    The double send. `run_stock_check` emitted STOCK_CRITICAL *and* sent
    `compose_stock_alert(urgent[0])` itself. It only bit when OWNER_PHONE was set
    — otherwise the event handler couldn't resolve a recipient and stayed mute,
    hiding the duplication behind a second bug.
    """
    monkeypatch.setenv("OWNER_PHONE", "+254712345678")
    sent = _run_check(stocked, monkeypatch)
    assert len(sent) == 1, f"same shortage reported {len(sent)} times: {sent}"


def test_second_check_inside_cooldown_sends_nothing(stocked, monkeypatch):
    """The 2-hourly job must not re-alert the same still-low item."""
    first = _run_check(stocked, monkeypatch)
    assert len(first) == 1

    second = _run_check(stocked, monkeypatch)
    assert second == [], f"item re-alerted inside the cooldown window: {second}"


def test_check_after_cooldown_expires_alerts_again(stocked, monkeypatch):
    _run_check(stocked, monkeypatch)

    # Age the stamp past the cooldown window.
    import ai.whatsapp.brain as brain_mod
    item = stocked.query(models.InventoryItem).filter(models.InventoryItem.id == 1).first()
    item.last_alerted_at = utcnow() - timedelta(hours=brain_mod.STOCK_ALERT_COOLDOWN_HOURS + 1)
    stocked.commit()

    again = _run_check(stocked, monkeypatch)
    assert len(again) == 1, "a still-low item must re-alert once the cooldown expires"


def test_cooldown_is_stamped_on_the_item(stocked, monkeypatch):
    def _item():
        return stocked.query(models.InventoryItem).filter(models.InventoryItem.id == 1).first()

    assert _item().last_alerted_at is None
    _run_check(stocked, monkeypatch)
    stocked.expire_all()
    assert _item().last_alerted_at is not None


def test_depleted_item_with_no_usage_still_reaches_the_owner(db_session, monkeypatch):
    """
    Zero quantity + zero recent usage => hours_remaining 999 => severity WARNING,
    so it never entered `urgent` and never emitted STOCK_CRITICAL. Before
    on_stock_depleted learned to send, this item was reported to nobody.
    """
    db_session.add_all([
        models.Restaurant(id=1, tenant_id=_tenant_id(db_session), name="Test Bistro", address="x",
                          owner_phone="+254712345678"),
        models.InventoryItem(id=1, restaurant_id=1, item_name="Saffron",
                             quantity=0.0, unit="g", low_stock_threshold=5),
    ])
    db_session.commit()

    sent = _run_check(db_session, monkeypatch)

    assert len(sent) == 1, f"a depleted item must alert the owner, got {sent}"
    assert "Saffron" in sent[0][1]
    assert "Out of Stock" in sent[0][1]


def test_depleted_item_is_not_reported_twice(db_session, monkeypatch):
    """A depleted item is depleted, not *also* merely critical — one event each."""
    db_session.add_all([
        models.Restaurant(id=1, tenant_id=_tenant_id(db_session), name="Test Bistro", address="x",
                          owner_phone="+254712345678"),
        models.InventoryItem(id=1, restaurant_id=1, item_name="Chicken",
                             quantity=0.0, unit="kg", low_stock_threshold=10),
    ])
    db_session.commit()
    for days_ago in range(1, 4):   # heavy usage -> hours_remaining 0 -> URGENT
        db_session.add(models.StockMovement(
            inventory_item_id=1, movement_type=models.StockMovementType.OUT,
            quantity=20.0, created_at=utcnow() - timedelta(days=days_ago),
        ))
    db_session.commit()

    sent = _run_check(db_session, monkeypatch)
    assert len(sent) == 1, f"depleted+urgent item alerted twice: {sent}"
