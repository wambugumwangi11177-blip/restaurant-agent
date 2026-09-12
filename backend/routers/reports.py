"""GET /api/v1/reports/{period} — deterministic drafted Restaurant OS reports.

period: daily | weekly | monthly | yearly. 422 for anything else.
"Drafted" = markdown template + real numbers interpolated. No LLM.
Shares _summarize() with the overview router (DRY).
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from routers.overview import _summarize
from auth import require_staff_role
from time_utils import utcnow

router = APIRouter(prefix="/reports", tags=["reports"])

_PERIOD_SPANS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "monthly": timedelta(days=30),
    "yearly": timedelta(days=365),
}
_EAT_OFFSET = timedelta(hours=3)


def _range(period: str):
    now_eat = utcnow() + _EAT_OFFSET
    if period == "daily":
        start_eat = now_eat.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_eat = now_eat - _PERIOD_SPANS[period]
    return start_eat - _EAT_OFFSET, now_eat - _EAT_OFFSET


def _top_items(db: Session, rid: int, start, end, limit=5) -> list:
    rows = db.query(
        models.MenuItem.name,
        func.sum(models.OrderItem.quantity).label("qty"),
        func.sum(models.OrderItem.unit_price * models.OrderItem.quantity).label("sales"),
    ).join(models.Order, models.OrderItem.order_id == models.Order.id).filter(
        models.Order.restaurant_id == rid,
        models.Order.created_at >= start, models.Order.created_at < end,
    ).group_by(models.MenuItem.name).order_by(func.sum(models.OrderItem.quantity).desc()).limit(limit).all()
    return [{"name": name, "qty": int(qty), "sales_kes": float(sales) / 100.0}
            for name, qty, sales in rows]


def _draft(period: str, range_label: str, core: dict, top: list) -> str:
    """Well-drafted report = good template + true numbers (deterministic)."""
    lines = [
        f"# {period.capitalize()} report — {range_label}",
        "",
        "## Overview",
        f"- Revenue: **KSh {core['revenue']:,.0f}**",
        f"- Orders: **{core['orders']}**",
        f"- Average order: **KSh {core['revenue'] / core['orders']:,.0f}**" if core["orders"] else "- No orders in this period.",
        "",
        "## Top selling items",
    ]
    if top:
        for t in top:
            lines.append(f"- {t['name']} — {t['qty']} sold (KSh {t['sales_kes']:,.0f})")
    else:
        lines.append("- No item-level sales recorded in this period.")
    lines += [
        "",
        "---",
        "Numbers are generated directly from your restaurant's data — no estimates.",
    ]
    return "\n".join(lines)


@router.get("/{period}")
def report(period: str, db: Session = Depends(get_db), user=Depends(require_staff_role())):
    if period not in _PERIOD_SPANS:
        raise HTTPException(422, f"period must be one of {list(_PERIOD_SPANS)}")
    rid = user.active_restaurant_id
    if rid is None:
        row = db.query(models.Restaurant.id).filter(
            models.Restaurant.tenant_id == user.tenant_id).first()
        rid = row[0] if row else 0
    start, end = _range(period)
    core = _summarize(db, rid, start, end)
    top = _top_items(db, rid, start, end)
    now_eat = utcnow() + _EAT_OFFSET
    if period == "daily":
        label = now_eat.strftime("%d %b %Y")
    elif period == "weekly":
        label = f"{(now_eat - timedelta(days=7)).strftime('%d %b')} – {now_eat.strftime('%d %b %Y')}"
    elif period == "monthly":
        label = f"{(now_eat - timedelta(days=30)).strftime('%d %b')} – {now_eat.strftime('%d %b %Y')}"
    else:
        label = f"{(now_eat - timedelta(days=365)).strftime('%d %b %Y')} – {now_eat.strftime('%d %b %Y')}"
    return {
        "period": period,
        "range": label,
        "revenue": core["revenue"],
        "orders": core["orders"],
        "top_items": top,
        "report_text": _draft(period, label, core, top),
    }