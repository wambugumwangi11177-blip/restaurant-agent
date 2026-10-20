"""
S5.3 — alert levels (docs/v2/SPEC.md §4): now (a push, a daily limit, quiet hours; cash and fraud to the owner alone, and an
unacknowledged one never paged to a manager) · today (an evening digest) · this week (in the weekly report).

Written before the code. Every threshold is the owner's setting (urgent_alerts_per_day, quiet_hours_start/end), so a test per setting
shows that changing it changes what happens, and the digest is held to the same rule as every owner sentence: no number in it
that its rows do not carry.
"""
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

import models
from ai import alert_levels as al
from ai.escalation.engine import EVENT_SEVERITY, LEVEL_1_TIMEOUT_MINUTES, LEVEL_2_TIMEOUT_MINUTES, run_escalation_sweep
from events.bus import EventType
from owner.answers import ungrounded
from owner.settings import DEFAULTS, update_settings
from tests.fixtures import golden_restaurant as gr
from tests.test_escalation import _make_restaurant, _make_user
from time_utils import utcnow


def S(**changes):
    return replace(DEFAULTS, **changes)


def eat(hour: int, minute: int = 0, day: int = 14) -> datetime:
    """A Nairobi wall-clock time on 14 Oct 2026, as the naive UTC the database stores."""
    return datetime(2026, 10, day, hour, minute) - timedelta(hours=3)


def today_at(hour: int) -> datetime:
    """Nairobi `hour` o'clock today (the real day), as naive UTC."""
    return al.eat_day_start(utcnow()) + timedelta(hours=hour)          # the real clock: tests patch al.utcnow to this very value


@pytest.fixture
def pushes(monkeypatch):
    """Every Web Push that would have gone out: (user_id, title)."""
    sent = []
    monkeypatch.setattr("ai.notify._dispatch_push", lambda db, user_id, title, body, url: sent.append((user_id, title)))
    return sent


def _notif(db, user, event_type="stock.critical", *, at=None, held=None, severity=None, title="Alert", acknowledged=False):
    n = models.Notification(user_id=user.id, title=title, body="body", event_type=event_type, severity=severity,
                            created_at=at or utcnow(), push_held=held, acknowledged_at=utcnow() if acknowledged else None)
    db.add(n)
    db.commit()
    return n


# ── the three levels ─────────────────────────────────────────────────────────

def test_the_exceptions_an_owner_is_woken_for_are_now_and_everything_else_is_today():
    assert {al.level_for(e) for e in al.NOW_EVENTS} == {al.NOW}
    for quiet in ("order.ready", "purchase_order.created", "recommendation.generated", "reservation.created"):
        assert al.level_for(quiet) == al.TODAY


def test_every_event_with_an_escalation_severity_is_now():
    assert set(EVENT_SEVERITY) <= al.NOW_EVENTS


def test_the_now_events_are_real_events():
    """A typo here would silently turn an urgent alert into a quiet one."""
    real = {e.value for e in EventType}
    assert al.NOW_EVENTS <= real and al.OWNER_ONLY_EVENTS <= al.NOW_EVENTS


def test_the_week_level_is_two_sections_of_the_weekly_report():
    from owner.reports import PLAN
    keys = {f"{period}.{key}" for period, sections in PLAN.items() for key, _label in sections}
    assert set(al.WEEK_SECTIONS) <= keys


# ── quiet hours (Nairobi time, may wrap midnight) ────────────────────────────

@pytest.mark.parametrize("hour,quiet", [(21, False), (22, True), (23, True), (0, True), (3, True), (6, True), (7, False), (12, False)])
def test_default_quiet_hours_are_10pm_to_7am_in_nairobi(hour, quiet):
    assert al.in_quiet_hours(DEFAULTS, eat(hour)) is quiet


def test_quiet_hours_boundaries_are_to_the_minute():
    assert al.in_quiet_hours(DEFAULTS, eat(21, 59)) is False and al.in_quiet_hours(DEFAULTS, eat(22, 0)) is True
    assert al.in_quiet_hours(DEFAULTS, eat(6, 59)) is True and al.in_quiet_hours(DEFAULTS, eat(7, 0)) is False


def test_quiet_hours_use_nairobi_time_not_utc():
    """21:30 UTC is 00:30 in Nairobi: quiet. 05:00 UTC is 08:00: not."""
    assert al.in_quiet_hours(DEFAULTS, datetime(2026, 10, 14, 21, 30)) is True
    assert al.in_quiet_hours(DEFAULTS, datetime(2026, 10, 14, 5, 0)) is False


def test_quiet_hours_that_do_not_wrap_midnight():
    nap = S(quiet_hours_start=14, quiet_hours_end=16)
    assert [al.in_quiet_hours(nap, eat(h)) for h in (13, 14, 15, 16)] == [False, True, True, False]


def test_the_same_hour_twice_means_never_quiet():
    never = S(quiet_hours_start=9, quiet_hours_end=9)
    assert not any(al.in_quiet_hours(never, eat(h)) for h in range(24))


def test_the_day_starts_at_midnight_in_nairobi():
    assert al.eat_day_start(eat(0, 5)) == eat(0) and al.eat_day_start(eat(23, 59)) == eat(0)
    assert al.eat_day_start(eat(0, 5) - timedelta(minutes=10)) == eat(0) - timedelta(days=1)


# ── now: the push decision ───────────────────────────────────────────────────

def test_an_urgent_alert_in_the_day_is_pushed_to_the_owner(db_session):
    g = gr.build_skeleton(db_session)
    d = al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", eat(12))
    assert (d.level, d.push, d.held) == ("now", True, None)


def test_an_urgent_alert_in_quiet_hours_is_held(db_session):
    g = gr.build_skeleton(db_session)
    d = al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", eat(23))
    assert (d.push, d.held) == (False, "quiet_hours")


def test_the_daily_limit_holds_the_alert_after_the_nth_push(db_session):
    g = gr.build_skeleton(db_session)
    update_settings(db_session, g.rid, g.owner.id, {"urgent_alerts_per_day": 2})
    now = today_at(12)
    for _ in range(2):
        assert al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", now).push is True
        _notif(db_session, g.owner, at=now)
    d = al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", now)
    assert (d.push, d.held) == (False, "daily_cap")


def test_changing_the_daily_limit_changes_the_answer(db_session):
    g = gr.build_skeleton(db_session)
    now = today_at(12)
    for _ in range(3):
        _notif(db_session, g.owner, at=now)
    assert al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", now).push is True          # default 5
    update_settings(db_session, g.rid, g.owner.id, {"urgent_alerts_per_day": 3})
    assert al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", now).held == "daily_cap"


def test_changing_the_quiet_hours_changes_the_answer(db_session):
    g = gr.build_skeleton(db_session)
    assert al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", eat(23)).held == "quiet_hours"
    update_settings(db_session, g.rid, g.owner.id, {"quiet_hours_start": 23, "quiet_hours_end": 5})
    assert al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", eat(23, 30)).held == "quiet_hours"
    assert al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", eat(22, 30)).push is True


def test_held_alerts_and_owner_reminders_do_not_use_up_the_limit(db_session):
    g = gr.build_skeleton(db_session)
    update_settings(db_session, g.rid, g.owner.id, {"urgent_alerts_per_day": 1})
    now = today_at(12)
    _notif(db_session, g.owner, at=now, held="quiet_hours")
    _notif(db_session, g.owner, "owner_escalation", at=now)
    assert al.pushes_today(db_session, g.owner.id, now) == 0
    assert al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", now).push is True


def test_the_limit_starts_again_at_midnight_in_nairobi(db_session):
    g = gr.build_skeleton(db_session)
    update_settings(db_session, g.rid, g.owner.id, {"urgent_alerts_per_day": 1})
    _notif(db_session, g.owner, at=eat(23, 50))                             # pushed last evening (quiet hours do not matter here: the row is data)
    assert al.pushes_today(db_session, g.owner.id, eat(0, 10, day=15)) == 0
    assert al.pushes_today(db_session, g.owner.id, eat(23, 55)) == 1


def test_the_limit_is_counted_per_person(db_session):
    g = gr.build_skeleton(db_session)
    second = _make_user(db_session, g.tenant, "second-owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    update_settings(db_session, g.rid, g.owner.id, {"urgent_alerts_per_day": 1})
    now = today_at(12)
    _notif(db_session, g.owner, at=now)
    assert al.push_decision(db_session, g.restaurant, g.owner, "stock.critical", now).held == "daily_cap"
    assert al.push_decision(db_session, g.restaurant, second, "stock.critical", now).push is True


def test_a_today_alert_is_never_pushed_to_the_owner(db_session):
    g = gr.build_skeleton(db_session)
    d = al.push_decision(db_session, g.restaurant, g.owner, "purchase_order.created", eat(12))
    assert (d.level, d.push, d.held) == ("today", False, "today")


def test_the_floor_is_not_under_the_owner_policy(db_session):
    """A manager is told at 23:00, whatever the owner's quiet hours, and a routine event is still pushed to the tier that acts on it."""
    g = gr.build_skeleton(db_session)
    assert al.push_decision(db_session, g.restaurant, g.manager, "stock.critical", eat(23)).push is True
    assert al.push_decision(db_session, g.restaurant, g.manager, "order.ready", eat(23)).push is True


def test_an_admin_login_is_the_owner(db_session):
    g = gr.build_skeleton(db_session)
    admin = _make_user(db_session, g.tenant, "plain-admin", role=models.Role.ADMIN, staff_role=None)
    assert al.is_owner(admin) and al.is_owner(g.owner) and not al.is_owner(g.manager)


# ── the fan-out applies the policy ───────────────────────────────────────────

def _critical_stock():
    from ai.orchestrator.push_notifier import _on_stock_critical
    return _on_stock_critical


def test_an_urgent_alert_in_the_day_pushes_the_owner_and_the_floor(db_session, pushes, monkeypatch):
    g = gr.build_skeleton(db_session)
    monkeypatch.setattr(al, "utcnow", lambda: today_at(12))
    _critical_stock()({"restaurant_id": g.rid, "item_name": "Rice", "hours_remaining": 2})
    assert {u for u, _t in pushes} == {g.owner.id, g.manager.id, g.storekeeper.id}
    owner_row = db_session.query(models.Notification).filter_by(user_id=g.owner.id).one()
    assert owner_row.push_held is None and owner_row.severity == "critical"


def test_at_night_the_owner_is_written_to_but_not_pushed_and_the_floor_still_is(db_session, pushes, monkeypatch):
    g = gr.build_skeleton(db_session)
    monkeypatch.setattr(al, "utcnow", lambda: today_at(23))
    _critical_stock()({"restaurant_id": g.rid, "item_name": "Rice", "hours_remaining": 2})
    assert sorted(u for u, _t in pushes) == sorted([g.manager.id, g.storekeeper.id])
    owner_row = db_session.query(models.Notification).filter_by(user_id=g.owner.id).one()
    assert owner_row.push_held == "quiet_hours" and owner_row.title == "Stock critical: Rice"      # in the feed, with the reason


def test_the_daily_limit_holds_the_owners_push_through_the_real_fan_out(db_session, pushes, monkeypatch):
    g = gr.build_skeleton(db_session)
    update_settings(db_session, g.rid, g.owner.id, {"urgent_alerts_per_day": 1})
    monkeypatch.setattr(al, "utcnow", lambda: today_at(12))
    for item in ("Rice", "Beef"):
        _critical_stock()({"restaurant_id": g.rid, "item_name": item, "hours_remaining": 2})
    rows = db_session.query(models.Notification).filter_by(user_id=g.owner.id).order_by(models.Notification.id).all()
    assert [r.push_held for r in rows] == [None, "daily_cap"]
    assert [u for u, _t in pushes].count(g.owner.id) == 1


def test_a_today_event_reaches_the_owner_feed_without_a_push(db_session, pushes):
    from ai.orchestrator.push_notifier import _on_supplier_reliability_dropped
    g = gr.build_skeleton(db_session)
    _on_supplier_reliability_dropped({"restaurant_id": g.rid, "supplier_name": "Golden Meats", "reliability_score": 60, "previous_score": 80})
    row = db_session.query(models.Notification).filter_by(user_id=g.owner.id).one()
    assert row.push_held == "today" and (g.owner.id, row.title) not in pushes


# ── cash and fraud: the owner alone ──────────────────────────────────────────

def test_cash_and_fraud_are_routed_to_the_owner_alone():
    from ai.orchestrator.push_notifier import _EVENT_TARGET_ROLES
    for event in (EventType.CASH_RECONCILIATION_FLAGGED, EventType.SUSPICIOUS_TRANSACTION_FLAGGED):
        assert _EVENT_TARGET_ROLES[event] == [models.StaffRole.OWNER]


def test_a_cash_flag_reaches_nobody_but_the_owner(db_session, pushes, monkeypatch):
    from ai.orchestrator.push_notifier import _on_cash_reconciliation_flagged
    g = gr.build_skeleton(db_session)
    controller = _make_user(db_session, g.tenant, "ctrl", staff_role=models.StaffRole.CONTROLLER)
    monkeypatch.setattr(al, "utcnow", lambda: today_at(12))
    _on_cash_reconciliation_flagged({"restaurant_id": g.rid, "expected_amount_cents": 3_500_000, "counted_amount_cents": 3_450_000, "variance_cents": -50_000})
    who = {n.user_id for n in db_session.query(models.Notification).all()}
    assert who == {g.owner.id}
    assert controller.id not in who and g.manager.id not in who


def test_a_fraud_flag_reaches_nobody_but_the_owner(db_session, pushes, monkeypatch):
    from ai.orchestrator.push_notifier import _on_suspicious_transaction_flagged
    g = gr.build_skeleton(db_session)
    monkeypatch.setattr(al, "utcnow", lambda: today_at(12))
    _on_suspicious_transaction_flagged({"restaurant_id": g.rid, "void_spike_count": 2})
    assert {n.user_id for n in db_session.query(models.Notification).all()} == {g.owner.id}


# ── escalation skips managers for the owner-only events ──────────────────────

def _unanswered(db, owner, event_type, severity, minutes_ago, now, level=0):
    n = models.Notification(user_id=owner.id, title="Flag", body="Something needs you", event_type=event_type, severity=severity,
                            created_at=now - timedelta(minutes=minutes_ago), escalation_level=level)
    db.add(n)
    db.commit()
    return n


def _team(db, suffix):
    tenant, restaurant = _make_restaurant(db, suffix)
    owner = _make_user(db, tenant, f"{suffix}owner", role=models.Role.ADMIN, staff_role=models.StaffRole.OWNER)
    manager = _make_user(db, tenant, f"{suffix}mgr", staff_role=models.StaffRole.MANAGER)
    return restaurant, owner, manager


@pytest.mark.parametrize("event_type,severity", [("cash.reconciliation_flagged", "high"), ("fraud.suspicious_transaction_flagged", "critical")])
def test_an_unacknowledged_cash_or_fraud_flag_is_never_paged_to_a_manager(db_session, event_type, severity):
    _r, owner, manager = _team(db_session, "s53a" + severity)
    now = eat(12)
    n = _unanswered(db_session, owner, event_type, severity, LEVEL_1_TIMEOUT_MINUTES[severity] + 1, now)
    result = run_escalation_sweep(db_session, now=now)
    assert result["escalated_to_managers"] == 0
    db_session.refresh(n)
    assert n.escalation_level == 1                                            # the clock moves on; nobody was paged
    assert db_session.query(models.Notification).filter_by(user_id=manager.id).count() == 0


def test_an_unacknowledged_stock_alert_still_pages_the_managers(db_session):
    _r, owner, manager = _team(db_session, "s53b")
    now = eat(12)
    _unanswered(db_session, owner, "stock.critical", "critical", LEVEL_1_TIMEOUT_MINUTES["critical"] + 1, now)
    assert run_escalation_sweep(db_session, now=now)["escalated_to_managers"] == 1
    assert db_session.query(models.Notification).filter_by(user_id=manager.id).count() == 1


def test_an_unanswered_fraud_flag_ends_with_a_reminder_to_the_owner_alone(db_session):
    _r, owner, manager = _team(db_session, "s53c")
    now = eat(12)
    n = _unanswered(db_session, owner, "fraud.suspicious_transaction_flagged", "critical", LEVEL_2_TIMEOUT_MINUTES["critical"] + 1, now, level=1)
    result = run_escalation_sweep(db_session, now=now)
    assert result["escalated_to_call"] == 1
    db_session.refresh(n)
    assert n.escalation_level == 2
    reminders = db_session.query(models.Notification).filter_by(event_type="owner_escalation").all()
    assert [r.user_id for r in reminders] == [owner.id] and reminders[0].push_held is None


def test_the_owner_reminder_waits_for_the_quiet_hours_to_end(db_session):
    _r, owner, _m = _team(db_session, "s53d")
    created = eat(21, 30)
    n = _unanswered(db_session, owner, "stock.critical", "critical", 0, created, level=1)
    n.created_at = created
    db_session.commit()
    night = eat(23, 0)                                                         # 90 minutes old, past the 45-minute mark, but it is night
    result = run_escalation_sweep(db_session, now=night)
    assert result["escalated_to_call"] == 0 and result.get("held_for_quiet_hours") == 1
    db_session.refresh(n)
    assert n.escalation_level == 1 and db_session.query(models.Notification).filter_by(event_type="owner_escalation").count() == 0
    morning = eat(7, 5, day=15)
    assert run_escalation_sweep(db_session, now=morning)["escalated_to_call"] == 1
    db_session.refresh(n)
    assert n.escalation_level == 2


def test_the_escalation_sweep_reads_the_saved_quiet_hours(db_session):
    r, owner, _m = _team(db_session, "s53e")
    update_settings(db_session, r.id, owner.id, {"quiet_hours_start": 9, "quiet_hours_end": 9})              # never quiet
    created = eat(21, 30)
    n = _unanswered(db_session, owner, "stock.critical", "critical", 0, created, level=1)
    n.created_at = created
    db_session.commit()
    assert run_escalation_sweep(db_session, now=eat(23, 0))["escalated_to_call"] == 1


# ── today: the evening digest ────────────────────────────────────────────────

def _busy_day(db, g, orders=3):
    dish = g.items["Pilau"]
    for i in range(orders):                                                    # just after midnight in Nairobi: never in the future
        gr.add_order(db, g, [(dish, 2, dish.price)], al.eat_day_start(utcnow()) + timedelta(minutes=i + 1))
    db.commit()


def _today_now() -> datetime:
    return today_at(20)


def test_the_digest_states_the_days_sales_from_home_and_every_figure_is_backed(db_session):
    from owner.home import compose_home
    from owner.states import OwnerContext
    g = gr.build_skeleton(db_session)
    _busy_day(db_session, g)
    digest = al.build_digest(db_session, g.owner, _today_now())
    pulse = compose_home(OwnerContext(db_session, g.owner, g.restaurant), "today")["pulse"]
    assert digest is not None and pulse["orders_today"] == 3
    sales = next(r for r in digest["rows"] if r["key"] == f"sales_{g.rid}")
    assert sales["value"] == pulse["sales_today"] and f"{pulse['orders_today']} orders" in digest["body"]
    assert ungrounded(digest) == []


def test_the_digest_lists_what_did_not_buzz_the_phone_and_what_still_waits(db_session):
    g = gr.build_skeleton(db_session)
    now = _today_now()
    _notif(db_session, g.owner, "stock.critical", at=al.eat_day_start(utcnow()) + timedelta(hours=2), held="quiet_hours", title="Stock critical: Rice", severity="critical")
    _notif(db_session, g.owner, "purchase_order.created", at=al.eat_day_start(utcnow()) + timedelta(hours=10), held="today", title="Purchase order ready")
    _notif(db_session, g.owner, "stock.critical", at=now - timedelta(hours=3), severity="critical", title="Beef is running out")
    digest = al.build_digest(db_session, g.owner, now)
    assert "2 alerts did not buzz your phone today: Stock critical: Rice; Purchase order ready." in digest["body"]
    assert "2 urgent alerts still wait for you to acknowledge." in digest["body"]          # the held critical one and the pushed one, neither acknowledged
    assert ungrounded(digest) == []


def test_an_acknowledged_alert_is_not_waiting(db_session):
    g = gr.build_skeleton(db_session)
    now = _today_now()
    _notif(db_session, g.owner, "stock.critical", at=now - timedelta(hours=3), severity="critical", acknowledged=True)
    assert al.build_digest(db_session, g.owner, now) is None


def test_a_quiet_day_has_no_digest(db_session):
    g = gr.build_skeleton(db_session)
    assert al.build_digest(db_session, g.owner, _today_now()) is None
    assert al.send_evening_digests(db_session, _today_now()) == {"sent": 0, "skipped": 1, "failed": 0}
    assert db_session.query(models.Notification).count() == 0


def test_the_digest_goes_to_the_owner_only_once_a_day(db_session, pushes):
    g = gr.build_skeleton(db_session)
    _busy_day(db_session, g)
    now = _today_now()
    assert al.send_evening_digests(db_session, now)["sent"] == 1
    assert al.send_evening_digests(db_session, now + timedelta(minutes=5)) == {"sent": 0, "skipped": 1, "failed": 0}
    rows = db_session.query(models.Notification).filter_by(event_type="owner.digest").all()
    assert [r.user_id for r in rows] == [g.owner.id] and rows[0].push_held is None and (g.owner.id, rows[0].title) in pushes
    assert rows[0].url == "/home" and rows[0].severity is None and rows[0].title.startswith("Your day")


def test_the_digest_is_kept_off_the_phone_in_quiet_hours(db_session, pushes):
    g = gr.build_skeleton(db_session)
    _busy_day(db_session, g)
    update_settings(db_session, g.rid, g.owner.id, {"quiet_hours_start": 19, "quiet_hours_end": 7})
    assert al.send_evening_digests(db_session, _today_now())["sent"] == 1
    row = db_session.query(models.Notification).filter_by(event_type="owner.digest").one()
    assert row.push_held == "quiet_hours" and pushes == []


def test_the_digest_does_not_use_up_the_urgent_limit(db_session):
    g = gr.build_skeleton(db_session)
    _busy_day(db_session, g)
    al.send_evening_digests(db_session, _today_now())
    assert al.pushes_today(db_session, g.owner.id, _today_now()) == 0


def test_one_owners_digest_never_carries_another_restaurants_day(db_session):
    a = gr.build_skeleton(db_session, suffix="digA")
    b = gr.build_skeleton(db_session, suffix="digB")
    _busy_day(db_session, b, orders=4)
    _notif(db_session, b.owner, "stock.critical", at=_today_now() - timedelta(hours=1), severity="critical", title="B's rice is out")
    assert al.build_digest(db_session, a.owner, _today_now()) is None                      # A sold nothing and was told nothing
    digest = al.build_digest(db_session, b.owner, _today_now())
    assert "4 orders" in digest["body"] and "1 urgent alert still waits" in digest["body"]
    assert {r["key"] for r in digest["rows"] if r["key"].startswith(("sales_", "orders_"))} == {f"sales_{b.rid}", f"orders_{b.rid}"}


def test_the_job_sends_one_digest_per_owner_login(db_session):
    a = gr.build_skeleton(db_session, suffix="jobA")
    b = gr.build_skeleton(db_session, suffix="jobB")
    _busy_day(db_session, a)
    _busy_day(db_session, b)
    assert al.send_evening_digests(db_session, _today_now()) == {"sent": 2, "skipped": 0, "failed": 0}
    assert {n.user_id for n in db_session.query(models.Notification).filter_by(event_type="owner.digest")} == {a.owner.id, b.owner.id}


def test_one_owners_failure_does_not_stop_the_others(db_session, monkeypatch):
    a = gr.build_skeleton(db_session, suffix="failA")
    b = gr.build_skeleton(db_session, suffix="failB")
    _busy_day(db_session, a)
    _busy_day(db_session, b)
    real = al.build_digest

    def flaky(db, user, now=None):
        if user.id == a.owner.id:
            raise RuntimeError("boom")
        return real(db, user, now)

    monkeypatch.setattr(al, "build_digest", flaky)
    assert al.send_evening_digests(db_session, _today_now()) == {"sent": 1, "skipped": 0, "failed": 1}


def test_the_digest_job_is_scheduled_after_the_dinner_rush(monkeypatch):
    import main
    jobs = {}

    class FakeScheduler:
        def __init__(self, *a, **k): ...
        def add_job(self, fn, trigger, **kw): jobs[kw["id"]] = (fn, trigger)
        def start(self): ...

    monkeypatch.setattr("apscheduler.schedulers.background.BackgroundScheduler", FakeScheduler)
    main._start_scheduler()
    fn, trigger = jobs["evening_digest"]
    assert fn is main._send_all_evening_digests
    fields = {f.name: str(f) for f in trigger.fields}
    assert fields["hour"] == str(al.DIGEST_HOUR_EAT - 3) and fields["minute"] == "0"          # the scheduler runs in UTC


def test_the_digest_job_hands_the_database_to_the_sender_and_never_raises(db_session, monkeypatch):
    import main
    calls = []
    monkeypatch.setattr(al, "send_evening_digests", lambda db, now=None: calls.append(db) or {"sent": 0, "skipped": 0, "failed": 0})
    main._send_all_evening_digests()
    assert len(calls) == 1

    def explode(db, now=None):
        raise RuntimeError("database gone")

    monkeypatch.setattr(al, "send_evening_digests", explode)
    main._send_all_evening_digests()                                                      # a failed job is logged, not raised into the scheduler


# ── the model and the registry ───────────────────────────────────────────────

def test_a_notification_remembers_why_it_was_not_pushed(db_session):
    g = gr.build_skeleton(db_session)
    n = _notif(db_session, g.owner, held="daily_cap")
    db_session.refresh(n)
    assert n.push_held == "daily_cap"
    assert _notif(db_session, g.owner).push_held is None


def test_the_notification_column_has_a_migration():
    from pathlib import Path
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    migration = next(versions.glob("054_*.py")).read_text()
    assert "push_held" in migration and 'down_revision = "053_money_settings"' in migration


def test_the_alert_settings_are_listed_by_the_engine_that_uses_them():
    from owner.registry import ENGINES
    listed = {s for e in ENGINES for s in e.settings}
    assert {"urgent_alerts_per_day", "quiet_hours_start", "quiet_hours_end"} <= listed
