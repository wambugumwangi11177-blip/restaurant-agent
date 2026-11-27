"""Shared 'today' strip math for Home, Money, and Ask."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from time_utils import utcnow

_EAT = timedelta(hours=3)
_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def eat_day_start(now=None):
    """Nairobi calendar midnight as naive UTC (matches overview EAT window)."""
    now = now or utcnow()
    local = now + _EAT
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - _EAT


def eat_now(now=None):
    return (now or utcnow()) + _EAT


def _paid_orders_q(db: Session, restaurant_id: int, start, end):
    return db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.created_at >= start,
        models.Order.created_at <= end,
        models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
    )


def today_sales_snapshot(db: Session, restaurant_id: int, now=None) -> dict:
    """Paid, non-cancelled orders created from Nairobi midnight through now."""
    now = now or utcnow()
    start = eat_day_start(now)
    base_q = _paid_orders_q(db, restaurant_id, start, now)
    revenue_cents = int(
        db.query(func.coalesce(func.sum(models.Order.total), 0))
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.created_at >= start,
            models.Order.created_at <= now,
            models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .scalar()
        or 0
    )
    tickets = base_q.count()
    cash_cents = int(
        db.query(func.coalesce(func.sum(models.Order.total), 0))
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.created_at >= start,
            models.Order.created_at <= now,
            models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.payment_method == models.PaymentMethod.CASH,
        )
        .scalar()
        or 0
    )
    mpesa_cents = revenue_cents - cash_cents
    note = None
    if revenue_cents > 0 and cash_cents == 0:
        note = "No cash tickets today — sales were M-Pesa/card only."
    elif revenue_cents > 0 and cash_cents < revenue_cents:
        note = "Cash drawer is cash sales only; M-Pesa does not sit in the drawer."
    return {
        "has_sales": revenue_cents > 0 or tickets > 0,
        "sales_kes": revenue_cents / 100.0,
        "tickets": int(tickets),
        "cash_expected_kes": cash_cents / 100.0,
        "mpesa_kes": mpesa_cents / 100.0,
        "cash_expected_note": note,
        "window_start": start,
        "window_end": now,
    }


def today_cash_breakdown(db: Session, restaurant_id: int, day_start) -> dict:
    """Back-compat wrapper: pass explicit start and use now as end."""
    now = utcnow()
    payload = today_sales_snapshot(db, restaurant_id, now=now)
    if day_start != payload["window_start"]:
        end = now
        base_q = _paid_orders_q(db, restaurant_id, day_start, end)
        revenue_cents = int(
            db.query(func.coalesce(func.sum(models.Order.total), 0))
            .filter(
                models.Order.restaurant_id == restaurant_id,
                models.Order.created_at >= day_start,
                models.Order.created_at <= end,
                models.Order.is_paid.is_(True),
                models.Order.status != models.OrderStatus.CANCELLED,
            )
            .scalar()
            or 0
        )
        tickets = base_q.count()
        cash_cents = int(
            db.query(func.coalesce(func.sum(models.Order.total), 0))
            .filter(
                models.Order.restaurant_id == restaurant_id,
                models.Order.created_at >= day_start,
                models.Order.created_at <= end,
                models.Order.is_paid.is_(True),
                models.Order.status != models.OrderStatus.CANCELLED,
                models.Order.payment_method == models.PaymentMethod.CASH,
            )
            .scalar()
            or 0
        )
        mpesa_cents = revenue_cents - cash_cents
        note = None
        if revenue_cents > 0 and cash_cents == 0:
            note = "No cash tickets today — sales were M-Pesa/card only."
        elif revenue_cents > 0 and cash_cents < revenue_cents:
            note = "Cash drawer is cash sales only; M-Pesa does not sit in the drawer."
        return {
            "has_sales": revenue_cents > 0 or tickets > 0,
            "sales_kes": revenue_cents / 100.0,
            "tickets": int(tickets),
            "cash_expected_kes": cash_cents / 100.0,
            "mpesa_kes": mpesa_cents / 100.0,
            "cash_expected_note": note,
        }
    return {k: v for k, v in payload.items() if k not in ("window_start", "window_end")}


def format_kes_owner(amount_kes: float) -> str:
    whole = int(round(amount_kes))
    return f"KES {whole:,}"


def today_sales_owner_sentence(db: Session, restaurant_id: int, now=None) -> dict:
    snap = today_sales_snapshot(db, restaurant_id, now=now)
    now = now or utcnow()
    now_eat = eat_now(now)
    tickets = snap["tickets"]
    sales = snap["sales_kes"]
    ticket_word = "ticket" if tickets == 1 else "tickets"
    wd = now_eat.weekday()
    weekday = _WEEKDAY_NAMES[wd]
    since = eat_day_start(now) - timedelta(days=35)
    rows = (
        db.query(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.created_at >= since,
            models.Order.created_at < eat_day_start(now),
            models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .all()
    )
    by_wd: dict[int, list[float]] = defaultdict(list)
    for o in rows:
        if not o.created_at:
            continue
        local = o.created_at + _EAT
        by_wd[local.weekday()].append(int(o.total or 0) / 100.0)
    hist = by_wd.get(wd, [])
    usual_full = sum(hist) / len(hist) if hist else None
    minute = now_eat.hour * 60 + now_eat.minute
    day_frac = max(minute / (24 * 60), 0.08)
    compare = None
    if usual_full and sales > 0:
        usual_by_now = usual_full * day_frac
        diff = round(sales - usual_by_now)
        if abs(diff) >= 500:
            if diff > 0:
                compare = f"about {format_kes_owner(abs(diff))} more than a usual {weekday} by this time"
            else:
                compare = f"about {format_kes_owner(abs(diff))} less than a usual {weekday} by this time"
        else:
            compare = f"about in line with a usual {weekday} by this time"
    if sales > 0:
        finding = f"You've sold {format_kes_owner(sales)} today from {tickets} {ticket_word}"
        if compare:
            finding += f", {compare}."
        else:
            finding += "."
    else:
        finding = "No paid tickets yet today."
    why = (
        "Paid, non-cancelled orders on the till since Nairobi midnight, up to now. "
        "This is sales on tickets, not cash in the drawer."
    )
    return {
        **snap,
        "finding": finding,
        "why": why,
        "weekday_name": weekday,
        "usual_weekday_full_day_kes": usual_full,
    }