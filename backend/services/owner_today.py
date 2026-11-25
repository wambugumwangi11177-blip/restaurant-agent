"""Shared 'today' strip math for Home and Money."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

import models


def today_cash_breakdown(db: Session, restaurant_id: int, day_start) -> dict:
    base_q = db.query(models.Order).filter(
        models.Order.restaurant_id == restaurant_id,
        models.Order.created_at >= day_start,
        models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
    )
    revenue_cents = int(
        db.query(func.coalesce(func.sum(models.Order.total), 0))
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.created_at >= day_start,
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