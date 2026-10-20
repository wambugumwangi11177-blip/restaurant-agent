"""
backend/owner/money/pnl.py — the Profit & Loss (docs/v2/SPEC.md S3.2; owner words, §3.4: "Left after ingredients",
"What you kept", "Out of every KES 100").

    sales                         what customers paid: paid, non-cancelled orders in the period (Nairobi days)
  − ingredients                   recipe cost × dishes sold (purchases when almost no dish has a recipe cost — flagged)
  = left after ingredients        (gross profit)
  − wages                         the Staff cost lines you entered; the shifts' cost when you entered none — flagged
  − other costs                   everything else you entered, by section; delivery app commissions are estimated from
                                  your commission rates unless you entered the real ones
  = what you kept                 (operating profit; "net before tax" equals it — nothing below it is recorded yet)

All money is integer cents; every percentage is of sales and is rounded half-up to one decimal. The engine only reads.

Deviation from the spec's wording, on purpose: delivery commissions are a cost line (under fees), not a deduction from
revenue, so "sales" is one number the owner recognises and "left after ingredients" is the gross profit the vocabulary
promises. The bottom line is identical; `sales_after_commission` is given for anyone who wants the net view.

Honest about what it cannot know: a cost the owner has not entered is not a cost of KES 0. `missing_categories` names the
fixed cost lines that were entered in the previous three months but not in this period, and the whole P&L says whether any
cost was entered at all (`costs_entered`), so the screen can say "add your costs" instead of showing a flattering profit.

Cash basis: an expense belongs to the day it was paid (`paid_on`). A bill paid once a month therefore appears in the week it was
paid; use a month or a year when you want a P&L an accountant would recognise.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from owner.money import categories as cats
from owner.settings import Settings, resolve
from time_utils import EAT_OFFSET, utcnow

KINDS = ("day", "week", "month", "year")
DRINK_CATEGORIES = frozenset({"drinks", "drink", "beverages", "beverage"})
PLATFORM_CHANNELS = (models.DeliveryChannel.UBER_EATS, models.DeliveryChannel.GLOVO, models.DeliveryChannel.BOLT_FOOD)
PURCHASE_STATUSES = ("DELIVERED", "LATE", "PARTIAL")
# below this share of sales covered by a dish with a recipe cost, ingredients come from purchases instead
MIN_COSTED_SHARE = 0.5
MISSING_LOOKBACK_DAYS = 90


def period_range(kind: str, anchor: date) -> tuple[date, date]:
    """The calendar period containing `anchor`: the day, the Monday-to-Sunday week, the month, the year."""
    if kind == "day":
        return anchor, anchor
    if kind == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if kind == "month":
        return anchor.replace(day=1), anchor.replace(day=calendar.monthrange(anchor.year, anchor.month)[1])
    if kind == "year":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    raise ValueError(f"period must be one of {KINDS}")


def nairobi_utc_range(start: date, end: date) -> tuple[datetime, datetime]:
    """[start 00:00, end+1 00:00) Nairobi as naive-UTC datetimes, the way every DateTime column is stored."""
    lo = datetime(start.year, start.month, start.day) - EAT_OFFSET
    return lo, datetime(end.year, end.month, end.day) + timedelta(days=1) - EAT_OFFSET


def pct(part: int, whole: int) -> float | None:
    """`part` as a percentage of `whole`, rounded half-up to one decimal (not Python's float rounding); None if there is no whole."""
    if not whole:
        return None
    return float((Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _commission(total_cents: int, rate: float) -> int:
    """A platform's cut of `total_cents`, to the cent, half-up (rates are fractions like 0.25)."""
    return int((Decimal(total_cents) * Decimal(str(rate))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compute_pnl(db: Session, restaurant_id: int, start: date, end: date, settings: Settings | None = None, *,
                today: date | None = None) -> dict[str, Any]:
    """The Profit & Loss for the Nairobi days start..end inclusive. Integer cents throughout."""
    if end < start:
        raise ValueError("the period ends before it starts")
    settings = resolve(db, restaurant_id, settings)
    lo, hi = nairobi_utc_range(start, end)

    # ── sales ────────────────────────────────────────────────────────────────
    paid = (models.Order.restaurant_id == restaurant_id, models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= lo, models.Order.created_at < hi)
    by_channel = {ch: (int(total or 0), int(n)) for ch, total, n in
                  db.query(models.Order.delivery_channel, func.sum(models.Order.total), func.count(models.Order.id)).filter(*paid).group_by(models.Order.delivery_channel)}
    sales = sum(t for t, _n in by_channel.values())
    orders = sum(n for _t, n in by_channel.values())

    # ── dishes: food/drinks split, ingredient cost, dishes with no cost ──────
    lines = db.query(models.MenuItem.id, models.MenuItem.name, models.MenuItem.category, models.MenuItem.cost_price,
                     func.sum(models.OrderItem.quantity), func.sum(models.OrderItem.unit_price * models.OrderItem.quantity)
                     ).join(models.OrderItem, models.OrderItem.menu_item_id == models.MenuItem.id
                            ).join(models.Order, models.Order.id == models.OrderItem.order_id
                                   ).filter(*paid).group_by(models.MenuItem.id, models.MenuItem.name, models.MenuItem.category, models.MenuItem.cost_price).all()
    food = drinks = recipe_cost = costed_sales = 0
    missing_costs: list[dict] = []
    for _id, name, category, cost_price, qty, line_sales in lines:
        qty, line_sales = int(qty or 0), int(line_sales or 0)
        if (category or "").strip().lower() in DRINK_CATEGORIES:
            drinks += line_sales
        else:
            food += line_sales
        if cost_price and cost_price > 0:
            recipe_cost += qty * int(cost_price)
            costed_sales += line_sales
        else:
            missing_costs.append({"dish": name, "units": qty, "sales_cents": line_sales})
    other_income = sales - food - drinks
    missing_costs.sort(key=lambda m: m["sales_cents"], reverse=True)

    purchases = int(db.query(func.coalesce(func.sum(models.PurchaseOrder.total_cost), 0)).filter(
        models.PurchaseOrder.restaurant_id == restaurant_id, models.PurchaseOrder.status.in_(PURCHASE_STATUSES),
        models.PurchaseOrder.delivered_at >= lo, models.PurchaseOrder.delivered_at < hi).scalar() or 0)
    if sales and costed_sales < MIN_COSTED_SHARE * sales and purchases:
        ingredients, ingredients_basis = purchases, "purchases"
    else:
        ingredients, ingredients_basis = recipe_cost, "recipe"

    # ── what the owner entered ───────────────────────────────────────────────
    cats.ensure_categories(db, restaurant_id)
    entered = db.query(models.ExpenseCategory, func.sum(models.Expense.amount_cents), func.count(models.Expense.id), func.max(models.Expense.paid_on)
                       ).join(models.Expense, models.Expense.category_id == models.ExpenseCategory.id
                              ).filter(models.Expense.restaurant_id == restaurant_id, models.Expense.voided_at.is_(None),
                                       models.Expense.paid_on >= start, models.Expense.paid_on <= end
                                       ).group_by(models.ExpenseCategory.id).all()
    by_category = {c.key: (c, int(total), int(n), last) for c, total, n, last in entered}
    entered_up_to = max((last for *_r, last in by_category.values()), default=None)
    costs_entered = bool(by_category)

    # wages: the Staff lines you entered, else the shifts' cost
    staff_entered = sum(t for c, t, _n, _l in by_category.values() if c.pnl_line == "staff")
    shifts_cost = int(db.query(func.coalesce(func.sum(models.LaborShift.labor_cost), 0)).filter(
        models.LaborShift.restaurant_id == restaurant_id, models.LaborShift.shift_date >= start, models.LaborShift.shift_date <= end).scalar() or 0)
    if any(c.pnl_line == "staff" for c, *_ in by_category.values()):
        labour, labour_basis = staff_entered, "entered"
        labour_fixed = sum(t for c, t, _n, _l in by_category.values() if c.pnl_line == "staff" and c.is_fixed)
    elif shifts_cost:
        labour, labour_basis = shifts_cost, "shifts"
        labour_fixed = shifts_cost                   # the people on the rota are there whatever the sales
    else:
        labour, labour_basis, labour_fixed = 0, "none", 0

    # delivery commissions: the real ones if entered, else the owner's rates on the platform orders
    estimated_commission = sum(_commission(total, settings.commission_rate(ch.value)) for ch, (total, _n) in by_channel.items() if ch in PLATFORM_CHANNELS)
    commission_entered = by_category.get("delivery_commissions")
    if commission_entered is not None:
        commission, commission_basis = commission_entered[1], "entered"
    elif estimated_commission:
        commission, commission_basis = estimated_commission, "estimated"
    else:
        commission, commission_basis = 0, "none"

    # other costs by section and line
    sections: dict[str, dict] = {}
    for c, total, n, _last in by_category.values():
        if c.pnl_line == "staff" or c.key == "delivery_commissions":
            continue
        sections.setdefault(c.pnl_line, {"lines": [], "total_cents": 0})
        sections[c.pnl_line]["lines"].append({"key": c.key, "name": c.name, "amount_cents": total, "entries": n, "is_fixed": c.is_fixed})
        sections[c.pnl_line]["total_cents"] += total
    if commission:
        sections.setdefault("fees", {"lines": [], "total_cents": 0})
        sections["fees"]["lines"].append({"key": "delivery_commissions", "name": "Delivery app commissions", "amount_cents": commission,
                                          "entries": commission_entered[2] if commission_entered else 0, "is_fixed": False, "basis": commission_basis})
        sections["fees"]["total_cents"] += commission
    ordered_sections = []
    for key in cats.PNL_LINES:
        if key in sections:
            sec = sections[key]
            sec["lines"].sort(key=lambda l: l["amount_cents"], reverse=True)
            ordered_sections.append({"key": key, "name": cats.PNL_LINE_NAMES[key], **sec})
    other_costs = sum(s["total_cents"] for s in ordered_sections)
    fixed_costs = labour_fixed + sum(l["amount_cents"] for sec in ordered_sections for l in sec["lines"] if l["is_fixed"])

    gross = sales - ingredients
    kept = gross - labour - other_costs

    # ── fixed lines entered before but not this period ───────────────────────
    prior_lo = start - timedelta(days=MISSING_LOOKBACK_DAYS)
    used_before = {cid for (cid,) in db.query(models.Expense.category_id).filter(
        models.Expense.restaurant_id == restaurant_id, models.Expense.voided_at.is_(None),
        models.Expense.paid_on >= prior_lo, models.Expense.paid_on < start).distinct()}
    here = {c.id for c, *_ in by_category.values()}
    missing_categories = []
    for c in db.query(models.ExpenseCategory).filter(models.ExpenseCategory.restaurant_id == restaurant_id, models.ExpenseCategory.is_active.is_(True),
                                                      models.ExpenseCategory.is_fixed.is_(True)).order_by(models.ExpenseCategory.sort_order):
        if c.id in used_before and c.id not in here:
            missing_categories.append({"key": c.key, "name": c.name, "why": "entered before, nothing this period"})

    today = today or (utcnow() + EAT_OFFSET).date()
    return {
        "period": {"start": start, "end": end, "days": (end - start).days + 1, "partial": end > today,
                   "days_elapsed": max(0, (min(end, today) - start).days + 1)},
        "orders": orders,
        "sales_cents": sales, "food_sales_cents": food, "drinks_sales_cents": drinks, "other_income_cents": other_income,
        "ingredients_cents": ingredients, "ingredients_basis": ingredients_basis, "missing_costs": missing_costs,
        "gross_profit_cents": gross,
        "labour_cents": labour, "labour_basis": labour_basis, "shifts_cost_cents": shifts_cost,
        "other_costs_cents": other_costs, "sections": ordered_sections,
        "labour_fixed_cents": labour_fixed, "fixed_costs_cents": fixed_costs,         # the costs that do not move with sales: break-even's numerator
        "delivery_commission_cents": commission, "delivery_commission_basis": commission_basis,
        "sales_after_commission_cents": sales - commission,
        "operating_profit_cents": kept, "net_before_tax_cents": kept,
        "food_cost_pct": pct(ingredients, sales), "labour_pct": pct(labour, sales), "other_costs_pct": pct(other_costs, sales),
        "prime_cost_pct": pct(ingredients + labour, sales), "gross_margin_pct": pct(gross, sales), "kept_pct": pct(kept, sales),
        "costs_entered": costs_entered, "entered_up_to": entered_up_to, "missing_categories": missing_categories,
    }
