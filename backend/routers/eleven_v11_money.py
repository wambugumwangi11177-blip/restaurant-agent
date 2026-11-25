"""Owner Money v11 — charts and monthly ledger."""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

import auth
import models
from ai.menu_engineer import get_menu_engineering
from ai.revenue_forecaster import get_revenue_forecast
from database import get_db
from routers.deps import get_or_create_restaurant
from routers.eleven_owner import _require_owner
from services.dish_cost import dish_cost_map
from services.owner_prefs import read_month_ledger, read_prefs, write_month_ledger
from time_utils import utcnow

router = APIRouter(prefix="/eleven/money", tags=["eleven-money-v11"])


def _orders(db, rid, days=90):
    since = utcnow() - timedelta(days=days)
    return (
        db.query(models.Order)
        .filter(
            models.Order.restaurant_id == rid,
            models.Order.created_at >= since,
            models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .all()
    )


@router.get("/forecast")
def money_forecast(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    data = get_revenue_forecast(db, restaurant.id)
    days = data.get("forecast") or []
    points = [
        {
            "day": row.get("date"),
            "low_kes": (row.get("low") or row.get("confidence_low") or 0) / 100.0,
            "high_kes": (row.get("high") or row.get("confidence_high") or 0) / 100.0,
            "mid_kes": (row.get("predicted_revenue") or row.get("revenue") or 0) / 100.0,
        }
        for row in days
    ]
    plates = (data.get("category_breakdown") or [])[:8]
    return {
        "has_sales": bool(points),
        "points": points,
        "plates_by_dish": [
            {"name": p.get("category") or p.get("name"), "plates": p.get("qty", 0)} for p in plates
        ],
        "empty": "Need about a week of till sales first.",
    }


@router.get("/waterfall")
def money_waterfall(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    pnl = owner_pnl_sync(db, current_user)
    if not pnl.get("has_sales"):
        return {"has_sales": False, "steps": [], "empty": "Starts when the till connects."}
    steps = [
        {"label": "Sales", "kes": pnl["revenue_cents"] / 100.0},
        {"label": "Food cost", "kes": -(pnl["food_cost_cents"] / 100.0)},
        {"label": "Gross profit", "kes": pnl["gross_margin_cents"] / 100.0},
        {"label": "Bills", "kes": -(pnl["bills_cents"] / 100.0)},
        {"label": "Pay", "kes": -(pnl["labor_cents"] / 100.0)},
        {"label": "Net", "kes": pnl["net_cents"] / 100.0},
    ]
    return {"has_sales": True, "steps": steps, "empty": None}


def owner_pnl_sync(db, current_user):
    restaurant = get_or_create_restaurant(db, current_user)
    since = utcnow() - timedelta(days=30)
    revenue_cents = int(
        db.query(func.coalesce(func.sum(models.Order.total), 0))
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= since,
        )
        .scalar()
        or 0
    )
    food_cost_cents = 0
    cost_map = dish_cost_map(db, restaurant.id)
    orders = (
        db.query(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.created_at >= since,
            models.Order.is_paid.is_(True),
        )
        .all()
    )
    for o in orders:
        for line in o.items:
            food_cost_cents += int(cost_map.get(line.menu_item_id, 0) * line.quantity)
    bills_cents = int(
        db.query(func.coalesce(func.sum(models.RunningCost.amount_cents), 0))
        .filter(models.RunningCost.restaurant_id == restaurant.id, models.RunningCost.status == "approved")
        .scalar()
        or 0
    )
    labor_cents = int(
        db.query(func.coalesce(func.sum(models.LaborShift.labor_cost), 0))
        .filter(models.LaborShift.restaurant_id == restaurant.id, models.LaborShift.shift_date >= since.date())
        .scalar()
        or 0
    )
    gross = revenue_cents - food_cost_cents
    net = gross - bills_cents - labor_cents
    return {
        "has_sales": revenue_cents > 0,
        "revenue_cents": revenue_cents,
        "food_cost_cents": food_cost_cents,
        "bills_cents": bills_cents,
        "labor_cents": labor_cents,
        "gross_margin_cents": gross,
        "net_cents": net,
    }


@router.get("/pnl/monthly/{period}")
def monthly_pnl(period: str, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    if len(period) != 7 or period[4] != "-":
        raise HTTPException(status_code=422, detail="period YYYY-MM")
    y, m = int(period[:4]), int(period[5:])
    start = utcnow().replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)
    if m == 12:
        end = start.replace(year=y + 1, month=1)
    else:
        end = start.replace(month=m + 1)
    orders = (
        db.query(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.created_at >= start,
            models.Order.created_at < end,
            models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .all()
    )
    revenue = sum(int(o.total or 0) for o in orders)
    food = 0
    cost_map = dish_cost_map(db, restaurant.id)
    for o in orders:
        for line in o.items:
            unit = cost_map.get(line.menu_item_id, 0)
            food += int(unit * line.quantity)
    bills = (
        db.query(func.coalesce(func.sum(models.RunningCost.amount_cents), 0))
        .filter(
            models.RunningCost.restaurant_id == restaurant.id,
            models.RunningCost.status == "approved",
            models.RunningCost.amount_cents > 0,
        )
        .scalar()
        or 0
    )
    pay = (
        db.query(func.coalesce(func.sum(models.LaborShift.labor_cost), 0))
        .filter(
            models.LaborShift.restaurant_id == restaurant.id,
            models.LaborShift.shift_date >= start.date(),
            models.LaborShift.shift_date < end.date(),
        )
        .scalar()
        or 0
    )
    gross = revenue - food
    net = gross - int(bills) - int(pay)
    prefs = read_prefs(restaurant)
    target = float(prefs.get("monthly_sales_target_kes") or 0) * 100
    lines = [
        {"line": "Sales", "kes": revenue / 100, "pct_sales": 100.0 if revenue else None},
        {"line": "Food cost", "kes": food / 100, "pct_sales": round(100 * food / revenue, 1) if revenue else None},
        {"line": "Gross profit", "kes": gross / 100, "pct_sales": round(100 * gross / revenue, 1) if revenue else None},
        {"line": "Bills", "kes": bills / 100, "pct_sales": round(100 * bills / revenue, 1) if revenue else None},
        {"line": "Pay", "kes": pay / 100, "pct_sales": round(100 * pay / revenue, 1) if revenue else None},
        {"line": "Net", "kes": net / 100, "pct_sales": round(100 * net / revenue, 1) if revenue else None},
    ]
    ledger = read_month_ledger(restaurant, period)
    locked = bool(ledger and ledger.get("locked_at"))
    summary = (
        ledger.get("summary")
        if ledger
        else (f"Net {net/100:,.0f} KES on sales {revenue/100:,.0f} KES this month." if revenue else None)
    )
    return {
        "period": period,
        "has_sales": revenue > 0,
        "lines": lines,
        "locked": locked,
        "vs_target_pct": round(100 * revenue / target, 1) if target and revenue else None,
        "summary": summary,
        "empty": "Starts when the till connects.",
    }


@router.post("/pnl/monthly/{period}/lock")
def lock_month(period: str, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    payload = monthly_pnl(period, db, current_user)
    if not payload.get("has_sales"):
        raise HTTPException(status_code=400, detail="No sales to lock")
    ledger = {
        "locked_at": utcnow().isoformat(),
        "lines": payload["lines"],
        "summary": payload.get("summary"),
    }
    write_month_ledger(db, restaurant, period, ledger)
    db.commit()
    return {"period": period, "locked": True}


@router.get("/export/monthly/{period}.xlsx")
def export_xlsx(period: str, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    data = monthly_pnl(period, db, current_user)
    wb = Workbook()
    ws = wb.active
    ws.title = period
    ws.append(["Line", "KES", "% of sales"])
    for row in data.get("lines") or []:
        ws.append([row["line"], row["kes"], row.get("pct_sales")])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="pnl-{period}.xlsx"'},
    )


@router.get("/export/monthly/{period}.pdf")
def export_pdf(period: str, db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    data = monthly_pnl(period, db, current_user)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 800, f"Monthly P&L — {period}")
    y = 770
    for row in data.get("lines") or []:
        c.drawString(72, y, f"{row['line']}: {row['kes']:,.0f} KES")
        y -= 18
    if data.get("summary"):
        c.drawString(72, y - 10, str(data["summary"])[:120])
    c.showPage()
    c.save()
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="application/pdf")


@router.get("/where")
def where_money(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    pnl = owner_pnl_sync(db, current_user)
    if not pnl.get("has_sales"):
        return {"has_sales": False, "slices": [], "empty": "Starts when the till connects."}
    rev = pnl["revenue_cents"]
    slices = [
        {"name": "Food", "kes": pnl["food_cost_cents"] / 100},
        {"name": "Bills", "kes": pnl["bills_cents"] / 100},
        {"name": "Pay", "kes": pnl["labor_cents"] / 100},
        {"name": "Left over", "kes": max(0, pnl["net_cents"]) / 100},
    ]
    return {"has_sales": True, "slices": slices, "revenue_kes": rev / 100, "empty": None}


@router.get("/food-cost-series")
def food_cost_series(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    prefs = read_prefs(restaurant)
    target = float(prefs.get("food_cost_target_pct") or 32)
    points = []
    for w in range(8):
        since = utcnow() - timedelta(days=(w + 1) * 7)
        until = utcnow() - timedelta(days=w * 7)
        orders = _orders(db, restaurant.id, 90)
        week_orders = [o for o in orders if o.created_at and since <= o.created_at < until]
        rev = sum(int(o.total or 0) for o in week_orders)
        cost_map = dish_cost_map(db, restaurant.id)
        food = 0
        for o in week_orders:
            for line in o.items:
                food += int(cost_map.get(line.menu_item_id, 0) * line.quantity)
        pct = round(100 * food / rev, 1) if rev else None
        points.append({"week": f"-{w + 1}w", "pct": pct, "over_target": pct is not None and pct > target})
    has = any(p["pct"] is not None for p in points)
    return {"has_sales": has, "points": list(reversed(points)), "target_pct": target, "empty": "Starts when recipes and sales exist."}


@router.get("/payments")
def payments_split(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    orders = _orders(db, restaurant.id, 30)
    cash = mpesa = card = 0
    for o in orders:
        amt = int(o.total or 0)
        if o.payment_method == models.PaymentMethod.CASH:
            cash += amt
        elif o.payment_method == models.PaymentMethod.MPESA:
            mpesa += amt
        elif o.payment_method == models.PaymentMethod.CARD:
            card += amt
    total = cash + mpesa + card
    return {
        "has_sales": total > 0,
        "slices": [
            {"name": "Cash", "kes": cash / 100},
            {"name": "M-Pesa", "kes": mpesa / 100},
            {"name": "Card", "kes": card / 100},
        ],
        "drawer_expected_kes": cash / 100,
        "empty": "Starts when the till records payment type.",
    }


@router.get("/bills")
def money_bills(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.RunningCost)
        .filter(models.RunningCost.restaurant_id == restaurant.id)
        .order_by(models.RunningCost.id.desc())
        .limit(40)
        .all()
    )
    paid = due = unknown = 0
    for r in rows:
        if r.status == "unknown" or r.amount_cents == 0:
            unknown += 1
        elif r.payment_state == "paid":
            paid += 1
        else:
            due += 1
    orders = _orders(db, restaurant.id, 30)
    sales = sum(int(o.total or 0) for o in orders)
    bills_sum = sum(int(r.amount_cents or 0) for r in rows if r.status == "approved")
    series = [{"day": f"-{d}d", "after_bills_kes": (sales - bills_sum) / 100 / 30} for d in range(30, 0, -3)]
    has = bool(rows)
    return {
        "has_sales": has,
        "paid": paid,
        "due": due,
        "unknown": unknown,
        "cash_after_bills": series,
        "empty": "Starts when bills are added in Settings.",
    }


@router.get("/goals")
def money_goals(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    prefs = read_prefs(restaurant)
    since = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sales = (
        db.query(func.coalesce(func.sum(models.Order.total), 0))
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.created_at >= since,
            models.Order.is_paid.is_(True),
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        .scalar()
        or 0
    )
    target_kes = float(prefs.get("monthly_sales_target_kes") or 0)
    return {
        "has_sales": sales > 0,
        "sales_kes": sales / 100,
        "target_kes": target_kes,
        "progress_pct": round(100 * (sales / 100) / target_kes, 1) if target_kes and sales else None,
        "food_cost_target_pct": prefs.get("food_cost_target_pct"),
        "empty": "Set targets in Settings.",
    }


@router.get("/dishes/summary")
def dishes_summary(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    eng = get_menu_engineering(db, restaurant.id)
    items = eng.get("items") or []
    if not items:
        return {"has_sales": False, "empty": "Starts when dishes sell on the till."}
    quad = [{"name": i.get("name"), "x": i.get("popularity_score", 0), "y": i.get("margin_pct", 0), "class": i.get("classification")} for i in items[:20]]
    return {
        "has_sales": True,
        "quadrant": quad,
        "pareto": eng.get("pareto") or [],
        "suggestions": (eng.get("recommendations") or [])[:5],
        "delivery_vs_dine": eng.get("order_type_split") or [],
        "empty": None,
    }


@router.get("/heatmap")
def sales_heatmap(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    orders = _orders(db, restaurant.id, 30)
    grid: dict[tuple[int, int], int] = defaultdict(int)
    for o in orders:
        if not o.created_at:
            continue
        dow = o.created_at.weekday()
        hour = o.created_at.hour
        grid[(dow, hour)] += int(o.total or 0)
    cells = [{"dow": d, "hour": h, "kes": v / 100} for (d, h), v in grid.items()]
    return {"has_sales": bool(cells), "cells": cells, "empty": "Starts when the till connects."}


@router.get("/three-month")
def three_month(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    bars = []
    for m in range(3):
        start = (utcnow().replace(day=1) - timedelta(days=32 * m)).replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        total = (
            db.query(func.coalesce(func.sum(models.Order.total), 0))
            .filter(
                models.Order.restaurant_id == restaurant.id,
                models.Order.created_at >= start,
                models.Order.created_at < end,
                models.Order.is_paid.is_(True),
            )
            .scalar()
            or 0
        )
        bars.append({"month": start.strftime("%Y-%m"), "kes": total / 100})
    avg = sum(b["kes"] for b in bars) / len(bars) if bars else 0
    return {"has_sales": any(b["kes"] for b in bars), "bars": list(reversed(bars)), "average_kes": avg, "empty": "Starts when the till connects."}


@router.get("/waste")
def money_waste(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    rows = (
        db.query(models.SpoilageRecord)
        .filter(models.SpoilageRecord.restaurant_id == restaurant.id)
        .order_by(models.SpoilageRecord.id.desc())
        .limit(50)
        .all()
    )
    missing = (
        db.query(models.StockMovement)
        .join(models.InventoryItem)
        .filter(
            models.InventoryItem.restaurant_id == restaurant.id,
            models.StockMovement.reason.contains("variance"),
        )
        .count()
    )
    bars = []
    for r in rows[:12]:
        item = db.query(models.InventoryItem).filter(models.InventoryItem.id == r.inventory_item_id).first()
        cost = int((item.cost_per_unit or 0) * r.quantity) if item else 0
        bars.append({"label": r.item_name, "kes": cost / 100, "reason": r.reason_code or "waste"})
    if missing:
        bars.append({"label": "Missing stock", "kes": missing * 500, "reason": "shrink"})
    return {"has_sales": bool(bars), "bars": bars, "empty": "Shows up when waste or shrink is recorded."}


@router.get("/weekday-profit")
def weekday_profit(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    orders = _orders(db, restaurant.id, 60)
    by_dow: dict[int, int] = defaultdict(int)
    for o in orders:
        if o.created_at:
            by_dow[o.created_at.weekday()] += int(o.total or 0)
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    bars = [{"day": names[d], "kes": by_dow[d] / 100} for d in range(7)]
    return {"has_sales": sum(by_dow.values()) > 0, "bars": bars, "empty": "Starts when the till connects."}


@router.get("/avg-spend")
def avg_spend(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    orders = _orders(db, restaurant.id, 90)
    by_week: dict[str, list[int]] = defaultdict(list)
    for o in orders:
        if o.created_at:
            key = o.created_at.date().isocalendar()[:2]
            by_week[str(key)].append(int(o.total or 0))
    points = [{"week": k, "kes": sum(v) / len(v) / 100} for k, v in sorted(by_week.items())[-12:]]
    return {"has_sales": bool(points), "points": points, "empty": "Starts when the till connects."}


@router.get("/voids")
def voids_by_staff(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    since = utcnow() - timedelta(days=30)
    voids = (
        db.query(models.Order)
        .filter(
            models.Order.restaurant_id == restaurant.id,
            models.Order.status == models.OrderStatus.CANCELLED,
            models.Order.created_at >= since,
        )
        .all()
    )
    bars = [{"label": "Voided tickets", "count": len(voids), "kes": sum(int(o.total or 0) for o in voids) / 100}]
    return {"has_sales": bool(voids), "bars": bars, "empty": "Shows when voids are recorded."}


@router.get("/supplier-prices")
def supplier_prices(db: Session = Depends(get_db), current_user=Depends(auth.get_current_user)):
    _require_owner(current_user)
    restaurant = get_or_create_restaurant(db, current_user)
    items = db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == restaurant.id).limit(8).all()
    lines = [{"name": i.item_name, "kes_per_unit": (i.cost_per_unit or 0) / 100} for i in items if i.cost_per_unit]
    return {"has_sales": bool(lines), "lines": lines, "empty": "Starts when invoice prices are confirmed."}