"""
backend/ai/alert_levels.py — what reaches the owner's phone, and when (docs/v2/SPEC.md §4, sprint S5.3).

Three levels, so an owner is neither buried nor blind:

  now    A push, at once. Only the exceptions an owner would want to be woken for (NOW_EVENTS: stock about to run out, a gap in the
         stock, a cash drawer outside tolerance, a suspicious transaction, a locked account). At most `urgent_alerts_per_day` of
         them a day and none inside the quiet hours; both are the owner's settings (owner/settings.py).
  today  Not pushed. It is in the in-app feed, and the evening digest says what the day held and what is still waiting.
  week   Not a notification: it is in the weekly report ("things to check", "cash count check"; WEEK_SECTIONS).

A held alert is never lost. The notification is always written (the in-app feed does not depend on push) and records why no push
went out (`Notification.push_held`: "quiet_hours" · "daily_cap" · "today"); the evening digest lists them. Only the owner is under
this policy: the floor tiers keep getting what their role must act on, at any hour.

Cash and fraud go to the owner alone, because their own people may be the subject, and an unacknowledged one is never paged to a
manager (ai/escalation/engine.py reads OWNER_ONLY_EVENTS). Everything here is deterministic: the digest's words are made by code
from the same blocks Home shows, so a figure in it is a figure on Home.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from owner.settings import Settings, get_settings
from time_utils import EAT_OFFSET, utcnow

logger = logging.getLogger("ai.alert_levels")

NOW, TODAY, WEEK = "now", "today", "week"

# EventType values an owner is woken for: the escalation table's severities (stock about to run out, a gap in the stock, a cash
# drawer outside tolerance, a suspicious transaction) and a locked account. Everything else that reaches the owner is "today".
NOW_EVENTS = frozenset({
    "stock.critical", "stock.variance_flagged",
    "cash.reconciliation_flagged", "fraud.suspicious_transaction_flagged",
    "account.locked",
})
# Reaches the owner alone and is never paged to a manager: the people involved may be the subject.
OWNER_ONLY_EVENTS = frozenset({"cash.reconciliation_flagged", "fraud.suspicious_transaction_flagged"})
# The owner reminder the escalation engine writes when a critical alert is still unacknowledged (not a new alert: not counted).
REMINDER_EVENT = "owner_escalation"
DIGEST_EVENT = "owner.digest"
DIGEST_HOUR_EAT = 20                                   # after the dinner rush, before the default quiet hours (22:00)
WEEK_SECTIONS = ("weekly.things_to_check", "weekly.cash_check")

HELD_QUIET_HOURS, HELD_DAILY_CAP, HELD_TODAY = "quiet_hours", "daily_cap", "today"


def level_for(event_type: str) -> str:
    return NOW if event_type in NOW_EVENTS else TODAY


def is_owner(user: models.User) -> bool:
    """The same people `get_staff_users_for_restaurant(..., [OWNER])` returns."""
    return user.staff_role == models.StaffRole.OWNER or user.role in (models.Role.ADMIN, models.Role.SUPERADMIN)


# ── the owner's clock ────────────────────────────────────────────────────────

def in_quiet_hours(settings: Settings, now: datetime | None = None) -> bool:
    """Is it quiet in Nairobi? `now` is naive UTC. The hours may wrap midnight (22 → 7); the same hour twice means never quiet."""
    start, end = settings.quiet_hours_start, settings.quiet_hours_end
    if start == end:
        return False
    hour = ((now or utcnow()) + EAT_OFFSET).hour
    return start <= hour < end if start < end else (hour >= start or hour < end)


def eat_day_start(now: datetime | None = None) -> datetime:
    """Midnight in Nairobi today, as naive UTC (what a DateTime column compares against)."""
    local = (now or utcnow()) + EAT_OFFSET
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - EAT_OFFSET


# ── now: the push decision ───────────────────────────────────────────────────

@dataclass(frozen=True)
class PushDecision:
    level: str
    push: bool
    held: str | None = None          # why no push went out


def pushes_today(db: Session, user_id: int, now: datetime | None = None) -> int:
    """Urgent pushes this person has had since midnight in Nairobi. Held alerts and owner reminders do not count."""
    return db.query(func.count(models.Notification.id)).filter(
        models.Notification.user_id == user_id,
        models.Notification.event_type.in_(NOW_EVENTS),
        models.Notification.created_at >= eat_day_start(now),
        models.Notification.push_held.is_(None),
    ).scalar() or 0


def push_decision(db: Session, restaurant: models.Restaurant, user: models.User, event_type: str,
                  now: datetime | None = None, settings: Settings | None = None) -> PushDecision:
    """Does this event become a push for this person right now?"""
    level = level_for(event_type)
    if not is_owner(user):
        return PushDecision(level, True)
    if level != NOW:
        return PushDecision(level, False, HELD_TODAY)
    now = now or utcnow()
    settings = settings or get_settings(db, restaurant.id)
    if in_quiet_hours(settings, now):
        return PushDecision(level, False, HELD_QUIET_HOURS)
    if pushes_today(db, user.id, now) >= settings.urgent_alerts_per_day:
        return PushDecision(level, False, HELD_DAILY_CAP)
    return PushDecision(level, True)


# ── today: the evening digest ────────────────────────────────────────────────

def _owner_ids(db: Session) -> list[tuple[models.User, models.Restaurant]]:
    from routers.deps import get_staff_users_for_restaurant
    seen: set[int] = set()
    out = []
    for restaurant in db.query(models.Restaurant).order_by(models.Restaurant.id).all():
        for user in get_staff_users_for_restaurant(db, restaurant, [models.StaffRole.OWNER]):
            if user.id not in seen:
                seen.add(user.id)
                out.append((user, restaurant))
    return out


def build_digest(db: Session, user: models.User, now: datetime | None = None) -> dict | None:
    """What the owner's day held, in words made by code from Home's own blocks. None when there is nothing to say.

    {"title", "body", "headline", "rows"}: `rows` carry every figure the body states, so the grounding check in
    owner/answers.py (`ungrounded`) can prove no number was invented.
    """
    from owner.answers import day_text, kes_text, pct_text, row
    from owner.home import compose_home
    from owner.states import OwnerContext
    from time_utils import eat_date

    now = now or utcnow()
    day_start = eat_day_start(now)
    lines: list[str] = []
    rows: list[dict] = []
    for restaurant in db.query(models.Restaurant).filter(models.Restaurant.tenant_id == user.tenant_id).order_by(models.Restaurant.id).all():
        ctx = OwnerContext(db, user, restaurant)
        home = compose_home(ctx, "today")
        pulse, money = home.get("pulse") or {}, home.get("costing_you_money") or {}
        name = restaurant.name
        orders = pulse.get("orders_today") or 0
        if orders:
            sales = pulse.get("sales_today") or 0
            line = f"{name}: {kes_text(sales)} from {orders} order{'s' if orders != 1 else ''}"
            rows += [row(f"sales_{restaurant.id}", f"{name} sales today", sales, "kes"), row(f"orders_{restaurant.id}", f"{name} orders today", orders, "count")]
            vs = pulse.get("vs_same_weekday_pct")
            if vs is not None and pulse.get("vs_same_weekday_state") == "live":
                line += f", {pct_text(abs(vs))} {'more' if vs >= 0 else 'less'} than the same day last week"
                rows.append(row(f"vs_{restaurant.id}", f"{name} against the same day last week", abs(vs), "pct"))
            lines.append(line + ".")
        top = next(iter(money.get("cards") or []), None)
        if top and top.get("kes_month"):
            lines.append(f"Biggest thing costing you money: {top['sentence'].rstrip('.')}, about {kes_text(top['kes_month'])} a month.")
            rows.append(row(f"idea_{restaurant.id}", top["sentence"], top["kes_month"], "kes"))
    held = db.query(models.Notification).filter(
        models.Notification.user_id == user.id, models.Notification.created_at >= day_start,
        models.Notification.push_held.isnot(None), models.Notification.event_type != DIGEST_EVENT,
    ).order_by(models.Notification.created_at).all()
    titles = list(dict.fromkeys(n.title for n in held))
    if held:
        lines.append(f"{len(held)} alert{'s' if len(held) != 1 else ''} did not buzz your phone today: {'; '.join(titles)}.")
        rows.append(row("held", "Alerts that did not buzz your phone", len(held), "count"))
        rows += [row(f"held_{i}", t, None, "text") for i, t in enumerate(titles)]
    waiting = db.query(func.count(models.Notification.id)).filter(
        models.Notification.user_id == user.id, models.Notification.severity.isnot(None),
        models.Notification.acknowledged_at.is_(None), models.Notification.created_at >= now - timedelta(hours=24),
    ).scalar() or 0
    if waiting:
        lines.append(f"{waiting} urgent alert{'s' if waiting != 1 else ''} still wait{'s' if waiting == 1 else ''} for you to acknowledge.")
        rows.append(row("waiting", "Urgent alerts waiting for you", waiting, "count"))
    if not lines:
        return None
    body = " ".join(lines)
    return {"title": f"Your day · {day_text(eat_date(now))}", "body": body, "headline": body, "rows": rows}


def send_evening_digests(db: Session, now: datetime | None = None) -> dict:
    """The scheduled job (main.py): one digest per owner login, once a day. A failure for one owner never stops the rest."""
    from ai.notify import notify_user
    now = now or utcnow()
    sent = skipped = failed = 0
    for user, restaurant in _owner_ids(db):
        try:
            if db.query(models.Notification.id).filter(
                    models.Notification.user_id == user.id, models.Notification.event_type == DIGEST_EVENT,
                    models.Notification.created_at >= eat_day_start(now)).first():
                skipped += 1
                continue
            digest = build_digest(db, user, now)
            if digest is None:
                skipped += 1
                continue
            quiet = in_quiet_hours(get_settings(db, restaurant.id), now)
            notify_user(db, user.id, digest["title"], digest["body"], DIGEST_EVENT, "/home",
                        push=not quiet, push_held=HELD_QUIET_HOURS if quiet else None)
            sent += 1
        except Exception as exc:                     # noqa: BLE001 — one owner's failure must not stop the others
            db.rollback()
            failed += 1
            logger.error(f"[AlertLevels] evening digest failed for user {user.id}: {exc}")
    return {"sent": sent, "skipped": skipped, "failed": failed}
